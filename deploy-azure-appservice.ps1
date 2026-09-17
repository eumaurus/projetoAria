param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string]$AcrName,

    [Parameter(Mandatory = $true)]
    [string]$PlanName,

    [Parameter(Mandatory = $true)]
    [string]$WebAppName,

    [string]$Location = "eastus",
    [string]$ImageName = "iakam-app",
    [string]$ImageTag = "latest",
    [string]$Sku = "B1",
    [string]$SubscriptionId = "",
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"

function Require-Command {
    param([string]$CommandName)

    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "Comando obrigatório não encontrado: $CommandName"
    }
}

function Parse-DotEnv {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        throw "Arquivo de ambiente não encontrado: $Path"
    }

    $settings = @()
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }

        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) {
            return
        }

        $key = $parts[0].Trim()
        $value = $parts[1].Trim()

        if (-not $key) {
            return
        }

        $settings += "$key=$value"
    }

    return $settings
}

Require-Command "az"
Require-Command "docker"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$dockerImageLocal = "${ImageName}:${ImageTag}"

Write-Host "Validando login no Azure..."
az account show --only-show-errors 1>$null

if ($SubscriptionId) {
    Write-Host "Selecionando subscription $SubscriptionId..."
    az account set --subscription $SubscriptionId --only-show-errors
}

Write-Host "Criando resource group..."
az group create `
    --name $ResourceGroup `
    --location $Location `
    --only-show-errors | Out-Null

Write-Host "Criando Azure Container Registry..."
az acr create `
    --resource-group $ResourceGroup `
    --name $AcrName `
    --sku Basic `
    --admin-enabled true `
    --only-show-errors | Out-Null

$loginServer = az acr show `
    --resource-group $ResourceGroup `
    --name $AcrName `
    --query loginServer `
    --only-show-errors `
    --output tsv

Write-Host "Buildando imagem Docker local..."
docker build -t $dockerImageLocal .

Write-Host "Autenticando no ACR..."
az acr login --name $AcrName

$dockerImageRemote = "${loginServer}/${ImageName}:${ImageTag}"

Write-Host "Enviando imagem para o ACR..."
docker tag $dockerImageLocal $dockerImageRemote
docker push $dockerImageRemote

Write-Host "Criando App Service Plan Linux..."
az appservice plan create `
    --name $PlanName `
    --resource-group $ResourceGroup `
    --is-linux `
    --sku $Sku `
    --only-show-errors | Out-Null

$webAppExists = az webapp list `
    --resource-group $ResourceGroup `
    --query "[?name=='$WebAppName'].name | [0]" `
    --only-show-errors `
    --output tsv

if (-not $webAppExists) {
    Write-Host "Criando Web App..."
    az webapp create `
        --resource-group $ResourceGroup `
        --plan $PlanName `
        --name $WebAppName `
        --container-image-name $dockerImageRemote `
        --only-show-errors | Out-Null
}

$acrUser = az acr credential show `
    --name $AcrName `
    --query username `
    --only-show-errors `
    --output tsv

$acrPassword = az acr credential show `
    --name $AcrName `
    --query "passwords[0].value" `
    --only-show-errors `
    --output tsv

Write-Host "Configurando imagem do container no Web App..."
az webapp config container set `
    --name $WebAppName `
    --resource-group $ResourceGroup `
    --container-image-name $dockerImageRemote `
    --container-registry-url "https://$loginServer" `
    --container-registry-user $acrUser `
    --container-registry-password $acrPassword `
    --only-show-errors | Out-Null

$appSettings = Parse-DotEnv -Path (Join-Path $projectRoot $EnvFile)
$appSettings += "WEBSITES_PORT=8501"
$appSettings += "PORT=8501"
$appSettings += "WEBSITES_CONTAINER_START_TIME_LIMIT=1800"

Write-Host "Aplicando app settings..."
az webapp config appsettings set `
    --name $WebAppName `
    --resource-group $ResourceGroup `
    --settings $appSettings `
    --only-show-errors | Out-Null

Write-Host "Habilitando logs do container..."
az webapp log config `
    --name $WebAppName `
    --resource-group $ResourceGroup `
    --docker-container-logging filesystem `
    --only-show-errors | Out-Null

$defaultHostName = az webapp show `
    --name $WebAppName `
    --resource-group $ResourceGroup `
    --query defaultHostName `
    --only-show-errors `
    --output tsv

Write-Host ""
Write-Host "Publicação concluída."
Write-Host "URL: https://$defaultHostName"
