"""Fábrica de dependências — injeção centralizada de serviços e agentes."""

from __future__ import annotations

from dataclasses import dataclass

from app.agentes.analytics_agent import AnalyticsAgent
from app.agentes.consulta_agent import ConsultaAgent
from app.agentes.rag_agent import RagAgent
from app.orquestrador.orquestrador import Orquestrador
from app.orquestrador.roteador import Roteador
from app.orquestrador.grafo_rag import GrafoRag
from app.servicos.analytics_service import AnalyticsService
from app.servicos.azure_sql_service import AzureSqlService
from app.servicos.config import Config
from app.servicos.controle_acesso import ControleAcesso
from app.servicos.chunk_service import ChunkService
from app.servicos.data_service import DataService
from app.servicos.embedding_service import EmbeddingService
from app.servicos.gemini_service import criar_gemini_service
from app.servicos.governanca_service import GovernancaService
from app.servicos.logger_service import LoggerService
from app.servicos.metadata_service import MetadataService
from app.servicos.prompt_service import PromptService
from app.servicos.sql_executor import SqlExecutor
from app.servicos.vetor_service import VetorService


@dataclass
class ContainerLux:
    """Agrupa instâncias prontas para uso pela aplicação."""

    config: Config
    data_service: DataService
    orquestrador: Orquestrador
    controle_acesso: ControleAcesso
    governanca_service: GovernancaService
    azure_sql_service: AzureSqlService | None = None


def construir_controle_acesso() -> ControleAcesso:
    """Monta somente as dependências necessárias para validar o login."""
    config = Config.obter()
    logger_service = LoggerService(config)
    return ControleAcesso(config, logger_service.obter("acesso"))


def construir_container() -> ContainerLux:
    """Monta grafo de dependências do Projeto LUX."""
    config = Config.obter()
    logger_service = LoggerService(config)

    data_service = DataService(config, logger_service.obter("data"))
    azure_sql_service = AzureSqlService(config, logger_service.obter("azure_sql"))
    metadata_service = MetadataService(
        config,
        logger_service.obter("metadata"),
        data_service,
        azure_sql_service,
    )
    prompt_service = PromptService(config, logger_service.obter("prompt"))
    gemini_service = criar_gemini_service(config, logger_service.obter("gemini"))
    sql_executor = SqlExecutor(
        config,
        logger_service.obter("sql"),
        data_service,
        azure_sql_service,
    )
    controle_acesso = ControleAcesso(config, logger_service.obter("acesso"), data_service)
    governanca_service = GovernancaService(config, logger_service.obter("governanca"))
    roteador = Roteador(config, logger_service.obter("roteador"))
    chunk_service = ChunkService(config, logger_service.obter("chunks"), data_service)
    embedding_service = EmbeddingService(config, logger_service.obter("embeddings"))
    vetor_service = VetorService(
        config,
        logger_service.obter("vetor"),
        embedding_service,
        chunk_service,
    )
    grafo_rag = GrafoRag(
        config,
        logger_service.obter("grafo_rag"),
        vetor_service,
        prompt_service,
        gemini_service,
    )
    analytics_service = AnalyticsService(
        config,
        logger_service.obter("analytics"),
        data_service,
        azure_sql_service,
    )

    consulta_agent = ConsultaAgent(
        config,
        logger_service.obter("consulta_agent"),
        prompt_service,
        metadata_service,
        gemini_service,
        sql_executor,
    )
    rag_agent = RagAgent(
        config,
        logger_service.obter("rag_agent"),
        grafo_rag,
    )
    analytics_agent = AnalyticsAgent(
        config,
        logger_service.obter("analytics_agent"),
        prompt_service,
        analytics_service,
        gemini_service,
    )

    orquestrador = Orquestrador(
        config,
        logger_service.obter("orquestrador"),
        controle_acesso,
        roteador,
        consulta_agent,
        rag_agent,
        analytics_agent,
    )

    return ContainerLux(
        config=config,
        data_service=data_service,
        orquestrador=orquestrador,
        controle_acesso=controle_acesso,
        governanca_service=governanca_service,
        azure_sql_service=azure_sql_service,
    )
