# IA KAM

Copiloto de análise operacional para incidentes e KPI, com interface em `Streamlit`, consulta estruturada sobre bases tabulares, recuperação contextual via RAG e suporte a múltiplos provedores de LLM.

O projeto foi desenhado para responder perguntas sobre duas bases principais:

- `base_tratada`
- `previsao_kpi`

No fluxo atual, a aplicação pode operar de duas formas:

- modo local, lendo arquivos `.xlsx` da pasta `dados`
- modo híbrido/cloud, usando `Azure SQL`, `Azure AI Search` e `Azure OpenAI` para embeddings

O provedor de LLM pode ser:

- `OpenAI`
- `Gemini`
- `mock`, para testes rápidos sem chamada externa

## O que a aplicação faz

O sistema recebe uma pergunta em linguagem natural, identifica a intenção e escolhe um dos fluxos principais:

- `consulta`: gera SQL somente de leitura para responder perguntas sobre as bases
- `rag`: recupera contexto indexado e produz resposta baseada em conhecimento textual
- `analytics`: calcula indicadores e análises agregadas

Além disso, o projeto inclui:

- autenticação por e-mail com controle de acesso
- painel de governança e auditoria
- histórico de interações
- suporte a deploy containerizado no Azure App Service

## Arquitetura

### Visão geral

```text
Usuário
  │
  ▼
Streamlit / CLI
  │
  ▼
Orquestrador
  ├─ ConsultaAgent  ──> Prompt + Metadata + LLM + SQL Executor
  ├─ RagAgent       ──> Grafo RAG + VetorService + LLM
  └─ AnalyticsAgent ──> AnalyticsService + LLM
  │
  ▼
Resposta final
```

### Componentes principais

- `streamlit_app.py`: interface web, login, chat, histórico e painel de governança
- `main.py`: ponto de entrada CLI para executar perguntas sem abrir a interface
- `app/container.py`: composição das dependências do projeto
- `app/orquestrador/`: roteamento da intenção e coordenação dos agentes
- `app/agentes/`: agentes de consulta, RAG e analytics
- `app/servicos/data_service.py`: leitura de planilhas `.xlsx`
- `app/servicos/sql_executor.py`: execução de SQL sobre os dados
- `app/servicos/vetor_service.py`: índice vetorial local ou no `Azure AI Search`
- `app/servicos/embedding_service.py`: embeddings locais, Vertex ou `Azure OpenAI`
- `app/servicos/gemini_service.py`: camada de LLM para `OpenAI`, `Gemini` ou `mock`
- `app/servicos/controle_acesso.py`: validação de e-mail autorizado
- `app/servicos/governanca_service.py`: trilha de auditoria, métricas e feedback

### Fontes de dados

O projeto foi estruturado para trabalhar prioritariamente com:

- `dados/base_tratada.xlsx`
- `dados/previsao_kpi.xlsx`

Arquivos auxiliares, como regras de acesso ou conhecimento complementar, também podem existir na pasta `dados`, mas o escopo analítico principal está nessas duas bases.

## Estrutura do repositório

```text
IA KAM/
├─ app/
│  ├─ agentes/
│  ├─ orquestrador/
│  ├─ prompts/
│  └─ servicos/
├─ dados/
├─ scripts/
├─ .dockerignore
├─ .env.example
├─ .gitignore
├─ AZURE_APP_SERVICE.md
├─ deploy-azure-appservice.ps1
├─ Dockerfile
├─ main.py
├─ requirements.txt
├─ streamlit_app.py
└─ README.md
```

## Requisitos

### Para rodar localmente

- `Python 3.12` recomendado
- `pip`
- acesso aos arquivos da pasta `dados`

### Para o caminho completo com cloud

- `Docker Desktop`
- `Azure CLI`
- conta com acesso aos recursos Azure necessários

## Instalação local

### 1. Clonar o repositório

```powershell
git clone https://github.com/Enoscruz/ia-kam.git
cd 'ia-kam'
```

### 2. Criar ambiente virtual

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Se o PowerShell bloquear a ativação, use:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

### 3. Instalar dependências

```powershell
pip install -r requirements.txt
```

### 4. Criar o arquivo `.env`

Copie o modelo:

```powershell
Copy-Item '.env.example' '.env'
```

Depois ajuste o `.env` conforme o modo de uso escolhido.

## Como configurar o `.env`

O arquivo `.env.example` já lista as variáveis suportadas. As mais importantes são:

### LLM

- `LLM_PROVIDER`: `openai`, `gemini` ou `mock`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_BASE_URL`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `GEMINI_MODO`

### Dados

- `FONTE_DADOS`: `duckdb` ou `azure`
- `PASTA_DADOS`
- `PASTA_LOGS`
- `PASTA_PROMPTS`

### Busca vetorial

- `VECTOR_STORE_PROVIDER`: `local` ou `azure_search`
- `EMBEDDING_MODO`: `local`, `vertex`, `fake` ou `azure_openai`
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_API_KEY`
- `AZURE_SEARCH_INDEX`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`

### Banco relacional no Azure

- `AZURE_SQL_SERVER`
- `AZURE_SQL_DATABASE`
- `AZURE_SQL_USUARIO`
- `AZURE_SQL_SENHA`
- `AZURE_SQL_SCHEMA`
- `AZURE_SQL_TABELAS`

## Modos recomendados de execução local

### Opção 1: teste rápido sem serviços externos

Esse é o melhor caminho para validar a interface, o fluxo dos agentes e a estrutura do projeto sem depender de cloud.

Use no `.env`:

```env
LLM_PROVIDER=mock
FONTE_DADOS=duckdb
VECTOR_STORE_PROVIDER=local
EMBEDDING_MODO=local
```

Esse modo é útil para:

- verificar se o projeto sobe
- validar login
- inspecionar a interface
- testar o fluxo básico sem custo externo

### Opção 2: local com OpenAI para LLM

Se você quiser uma resposta real da LLM sem subir toda a stack Azure, use:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sua-chave
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
FONTE_DADOS=duckdb
VECTOR_STORE_PROVIDER=local
EMBEDDING_MODO=local
```

### Opção 3: local com arquitetura próxima da produção

Se quiser rodar localmente, mas com serviços Azure de embeddings, busca vetorial e banco:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sua-chave
FONTE_DADOS=azure
VECTOR_STORE_PROVIDER=azure_search
EMBEDDING_MODO=azure_openai
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
AZURE_SEARCH_ENDPOINT=...
AZURE_SEARCH_API_KEY=...
AZURE_SEARCH_INDEX=iakam-rag-index
AZURE_SQL_SERVER=...
AZURE_SQL_DATABASE=...
AZURE_SQL_USUARIO=...
AZURE_SQL_SENHA=...
AZURE_SQL_TABELAS=base_tratada,previsao_kpi
```

## Como testar localmente

### Teste 1: subir a interface Streamlit

Com o ambiente virtual ativo e o `.env` configurado:

```powershell
streamlit run .\streamlit_app.py
```

Se tudo estiver certo, o Streamlit abrirá uma URL local no navegador.

O que validar nessa etapa:

- a tela de login abre normalmente
- a aplicação não fica travada no carregamento inicial
- o e-mail é validado
- a conversa abre após o login

### Teste 2: validar o login

O login usa o controle de acesso definido no projeto. Para entrar, use um e-mail autorizado no arquivo de regras de acesso do ambiente de dados.

Se o login falhar:

- confirme que o arquivo de controle de acesso existe na pasta `dados`
- confirme que o e-mail informado está cadastrado
- verifique mensagens no Streamlit e nos logs

### Teste 3: executar pela CLI

Também é possível rodar uma pergunta sem abrir a interface:

```powershell
python .\main.py --pergunta "Quantos incidentes tivemos por prioridade?" --email "voce@empresa.com"
```

Para saída em JSON:

```powershell
python .\main.py --pergunta "Compare o volume real com a previsão D1 e D7." --email "voce@empresa.com" --json
```

Esse teste é útil para:

- validar o orquestrador
- checar erros de configuração de LLM
- inspecionar o SQL gerado
- testar integração com dados sem depender da UI

### Teste 4: validar o fluxo de consulta

Perguntas boas para o primeiro teste:

- `Quantos incidentes tivemos por prioridade?`
- `Qual a taxa média de KPI violado por grupo designado?`
- `Compare o volume real com a previsão D1 e D7.`

O comportamento esperado é:

- o sistema identificar a intenção
- gerar SQL apenas de leitura quando necessário
- retornar uma resposta em linguagem natural
- exibir dados ou contexto adicional quando aplicável

### Teste 5: validar governança

Depois de fazer algumas perguntas:

- acesse a lateral da aplicação
- entre em `Governança & dados`, se seu usuário tiver nível `GOD`

Você deverá ver:

- volume de consultas
- taxa de sucesso
- latência p95
- tokens estimados
- trilha de auditoria
- feedback por interação

## Logs e diagnóstico local

Os logs são gravados na pasta configurada por `PASTA_LOGS`, que por padrão é `logs/`.

Quando algo falhar, verifique:

- mensagens no terminal onde o Streamlit foi iniciado
- arquivos em `logs/`
- valores do `.env`
- disponibilidade das chaves e endpoints externos

Problemas comuns:

- `OPENAI_API_KEY` ou `GEMINI_API_KEY` inválida
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` incorreto
- `AZURE_SEARCH_ENDPOINT` ou `AZURE_SEARCH_API_KEY` ausentes
- `AZURE_SQL_*` inválidos
- e-mail não autorizado no controle de acesso

## Como o SQL é tratado

O projeto foi pensado para geração de consulta analítica, não para escrita operacional. Na prática, o fluxo deve ser mantido como somente leitura.

Na validação funcional, espere consultas como:

- `SELECT ...`
- `WITH ... SELECT ...`

Não use o projeto para permitir comandos destrutivos em bases reais.

## Como o RAG funciona

O serviço vetorial pode operar em dois modos:

- `local`, com `Chroma`
- `azure_search`, com `Azure AI Search`

O índice é alimentado a partir de:

- arquivos Excel de contexto da pasta `dados`
- arquivos adicionais de conhecimento em `dados/conhecimento`

O serviço evita reindexação desnecessária comparando um manifesto dos arquivos-fonte com o estado salvo do índice.

## Deploy com Docker

O projeto já inclui:

- `Dockerfile`
- `.dockerignore`

Build local da imagem:

```powershell
docker build -t iakam-app .
```

Executar localmente com `.env`:

```powershell
docker run -p 8501:8501 --env-file .env iakam-app
```

## Deploy no Azure App Service

O script `deploy-azure-appservice.ps1` automatiza:

- criação de `Resource Group`
- criação de `Azure Container Registry`
- build e push da imagem Docker
- criação de `App Service Plan`
- criação do `Web App`
- aplicação dos `App Settings`

Exemplo de uso:

```powershell
.\deploy-azure-appservice.ps1 `
  -ResourceGroup 'rg-iakam-prod' `
  -AcrName 'iakamacrprod123' `
  -PlanName 'plan-iakam-prod' `
  -WebAppName 'iakam-prod-app' `
  -Location 'eastus'
```

Mais detalhes estão em `AZURE_APP_SERVICE.md`.

## Fluxo recomendado para desenvolvimento

### Alterar código e testar localmente

1. ajustar o código
2. validar pela CLI
3. validar no `Streamlit`
4. revisar logs

### Publicar nova versão

1. garantir que o `.env` de produção está correto
2. buildar a imagem
3. publicar com o script de deploy
4. validar logs e URL publicada

## Arquivos importantes para manutenção

- `streamlit_app.py`: experiência do usuário
- `main.py`: execução via terminal
- `app/container.py`: composição dos serviços
- `app/servicos/config.py`: leitura e decisão das variáveis de ambiente
- `app/servicos/gemini_service.py`: integração com `OpenAI`, `Gemini` e `mock`
- `app/servicos/vetor_service.py`: indexação e busca vetorial
- `deploy-azure-appservice.ps1`: automação de publicação
- `.env.example`: modelo de configuração

## Boas práticas

- nunca commitar o `.env`
- manter segredos fora do repositório
- testar primeiro com `mock` ou com dados locais antes de ativar recursos cloud
- revisar o comportamento do login antes de validar consultas complexas
- verificar logs sempre que houver lentidão no carregamento inicial

## Status atual do repositório

Este repositório já está preparado para:

- desenvolvimento local
- teste via CLI
- teste via `Streamlit`
- empacotamento com Docker
- publicação no Azure

O melhor ponto de partida para uma nova máquina é:

1. clonar o repositório
2. criar `.venv`
3. instalar `requirements.txt`
4. copiar `.env.example` para `.env`
5. configurar o modo mínimo local
6. rodar `streamlit run .\streamlit_app.py`

## Próximos passos sugeridos

- adicionar um `README` com imagens da interface, se quiser documentação mais visual
- documentar exemplos reais de perguntas por perfil operacional e executivo
- separar futuramente a camada de LLM em um nome mais neutro que `gemini_service.py`
