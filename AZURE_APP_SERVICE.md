# Publicação no Azure App Service

Este projeto já está preparado para subir no Azure usando:

- `Docker` para build da imagem
- `Azure Container Registry` para armazenar a imagem
- `Azure App Service (Linux)` para publicar o container

## Pré-requisitos

- `Docker Desktop` instalado e aberto
- `Azure CLI` instalado
- login feito com:

```powershell
az login
```

## Arquivos usados

- `Dockerfile`
- `.dockerignore`
- `deploy-azure-appservice.ps1`

## O que o script faz

O script:

1. cria o `Resource Group`
2. cria o `Azure Container Registry`
3. builda a imagem `iakam-app`
4. envia a imagem para o `ACR`
5. cria o `App Service Plan`
6. cria o `Web App`
7. aplica as variáveis do arquivo `.env` como `App Settings`
8. configura `WEBSITES_PORT=8501`

## Comando para publicar

Na raiz do projeto, rode:

```powershell
.\deploy-azure-appservice.ps1 `
  -ResourceGroup 'rg-iakam-prod' `
  -AcrName 'iakamacrprod123' `
  -PlanName 'plan-iakam-prod' `
  -WebAppName 'iakam-prod-app' `
  -Location 'eastus'
```

## Regras importantes

- `AcrName` precisa ser globalmente único no Azure
- o nome do `ACR` deve ter apenas letras e números
- o script lê as variáveis diretamente do `.env`
- o app será publicado como container Linux

## Depois do deploy

Para ver a URL publicada:

```powershell
az webapp show `
  --resource-group 'rg-iakam-prod' `
  --name 'iakam-prod-app' `
  --query defaultHostName `
  --output tsv
```

Para ver logs:

```powershell
az webapp log tail `
  --resource-group 'rg-iakam-prod' `
  --name 'iakam-prod-app'
```

## Observações

- o diretório `dados/vetores/` não entra na imagem; ele é recriado no ambiente publicado
- os arquivos de dados base continuam indo na imagem
- o `SQLite` de governança no App Service funciona para teste, mas para produção o ideal é migrar isso para um banco gerenciado
