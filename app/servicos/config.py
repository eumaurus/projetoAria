"""Singleton de configuração carregada via variáveis de ambiente."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


class Config:
    """Gerencia caminhos do projeto e parâmetros da LLM."""

    _instancia: Config | None = None

    def __new__(cls) -> Config:
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            cls._instancia._inicializado = False
        return cls._instancia

    def __init__(self) -> None:
        if self._inicializado:
            return

        raiz = Path(__file__).resolve().parents[2]
        load_dotenv(raiz / ".env")

        self.raiz_projeto: Path = raiz
        self.pasta_dados: Path = raiz / os.getenv("PASTA_DADOS", "dados")
        self.pasta_logs: Path = raiz / os.getenv("PASTA_LOGS", "logs")
        self.pasta_prompts: Path = raiz / os.getenv("PASTA_PROMPTS", "app/prompts")
        self.pasta_conhecimento: Path = raiz / os.getenv("PASTA_CONHECIMENTO", "dados/conhecimento")
        self.pasta_vetores: Path = raiz / os.getenv("PASTA_VETORES", "dados/vetores")

        self.google_cloud_project: str = os.getenv("GOOGLE_CLOUD_PROJECT", "")
        self.google_cloud_location: str = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        self.google_api_key: str = (
            os.getenv("GEMINI_API_KEY", "").strip()
            or os.getenv("GOOGLE_API_KEY", "").strip()
        )
        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
        self.openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
        self.openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
        self.nivel_log: str = os.getenv("NIVEL_LOG", "INFO")

        llm_provider_bruto = os.getenv("LLM_PROVIDER", "").strip().lower()
        if llm_provider_bruto in ("mock", "gemini", "openai"):
            self.llm_provider: str = llm_provider_bruto
        elif self.openai_api_key:
            self.llm_provider = "openai"
        elif self.google_api_key or self.google_cloud_project:
            self.llm_provider = "gemini"
        else:
            self.llm_provider = "mock"

        modo_bruto = os.getenv("GEMINI_MODO", "").strip().lower()
        if modo_bruto in ("mock", "vertex", "api"):
            self.gemini_modo: str = modo_bruto
        elif self.llm_provider == "openai":
            self.gemini_modo = "mock"
        elif self.google_api_key:
            self.gemini_modo = "api"
        elif not self.google_cloud_project:
            self.gemini_modo = "mock"
        else:
            self.gemini_modo = "vertex"

        self.azure_sql_server: str = os.getenv("AZURE_SQL_SERVER", "").strip()
        self.azure_sql_database: str = os.getenv("AZURE_SQL_DATABASE", "").strip()
        self.azure_sql_usuario: str = os.getenv("AZURE_SQL_USUARIO", "").strip()
        self.azure_sql_senha: str = os.getenv("AZURE_SQL_SENHA", "")
        self.azure_sql_driver: str = os.getenv(
            "AZURE_SQL_DRIVER",
            "ODBC Driver 18 for SQL Server",
        )
        self.azure_sql_schema: str = os.getenv("AZURE_SQL_SCHEMA", "dbo").strip() or "dbo"
        tabelas_env = os.getenv("AZURE_SQL_TABELAS", os.getenv("AZURE_SQL_TABELA", "base_tratada,previsao_kpi"))
        self.azure_sql_tabelas: list[str] = [
            t.strip() for t in tabelas_env.split(",") if t.strip()
        ]
        if self.azure_sql_tabelas == ["base_final"]:
            base_incidentes = self.pasta_dados / "base_tratada.xlsx"
            base_previsao = self.pasta_dados / "previsao_kpi.xlsx"
            if base_incidentes.exists() and base_previsao.exists():
                self.azure_sql_tabelas = ["base_tratada", "previsao_kpi"]

        fonte_bruta = os.getenv("FONTE_DADOS", "").strip().lower()
        if fonte_bruta in ("azure", "duckdb"):
            self.fonte_dados: str = fonte_bruta
        elif self.azure_sql_server and self.azure_sql_database:
            self.fonte_dados = "azure"
        else:
            self.fonte_dados = "duckdb"

        self.chunk_tamanho: int = int(os.getenv("CHUNK_TAMANHO", "800"))
        self.chunk_sobreposicao: int = int(os.getenv("CHUNK_SOBREPOSICAO", "120"))
        self.rag_k: int = int(os.getenv("RAG_K", "5"))

        self.azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip().rstrip("/")
        self.azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
        self.azure_openai_api_version: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01").strip()
        self.azure_openai_embedding_deployment: str = os.getenv(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
            "text-embedding-3-small",
        ).strip()
        self.azure_search_endpoint: str = os.getenv("AZURE_SEARCH_ENDPOINT", "").strip().rstrip("/")
        self.azure_search_api_key: str = os.getenv("AZURE_SEARCH_API_KEY", "").strip()
        self.azure_search_index: str = os.getenv("AZURE_SEARCH_INDEX", "iakam-rag-index").strip()

        vetor_bruto = os.getenv("VECTOR_STORE_PROVIDER", "").strip().lower()
        if vetor_bruto in ("local", "azure_search"):
            self.vector_store_provider = vetor_bruto
        elif self.azure_search_endpoint and self.azure_search_api_key:
            self.vector_store_provider = "azure_search"
        else:
            self.vector_store_provider = "local"

        embedding_bruto = os.getenv("EMBEDDING_MODO", "").strip().lower()
        if embedding_bruto in ("local", "vertex", "fake", "azure_openai"):
            self.embedding_modo: str = embedding_bruto
        elif self.azure_openai_endpoint and self.azure_openai_api_key:
            self.embedding_modo = "azure_openai"
        elif self.gemini_modo == "vertex":
            self.embedding_modo = "vertex"
        else:
            self.embedding_modo = "local"

        self.pasta_dados.mkdir(parents=True, exist_ok=True)
        self.pasta_logs.mkdir(parents=True, exist_ok=True)
        self.pasta_conhecimento.mkdir(parents=True, exist_ok=True)
        self.pasta_vetores.mkdir(parents=True, exist_ok=True)

        self._inicializado = True

    def tabela_azure_padrao(self) -> str:
        """Retorna a tabela Azure padrão com schema."""
        if not self.azure_sql_tabelas:
            return "dbo.base_tratada"
        primeira = self.azure_sql_tabelas[0]
        if "." in primeira:
            return primeira
        return f"{self.azure_sql_schema}.{primeira}"

    @classmethod
    def obter(cls) -> Config:
        """Retorna a instância singleton."""
        return cls()
