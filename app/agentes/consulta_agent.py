"""Agente especialista em consultas analíticas (MVP)."""

from __future__ import annotations

import logging

import pandas as pd

from app.modelos.estado import Estado
from app.servicos.base_service import BaseService
from app.servicos.config import Config
from app.servicos.gemini_service import GeminiService
from app.servicos.metadata_service import MetadataService
from app.servicos.prompt_service import PromptService
from app.servicos.sql_executor import SqlExecutor


class ConsultaAgent(BaseService):
    """Coordena geração de SQL, execução na fonte de dados e formatação da resposta."""

    SYSTEM_PROMPT_SQL = (
        "Você gera SQL de leitura preciso e seguro. "
        "Responda somente com SQL dentro de bloco ```sql."
    )
    SYSTEM_PROMPT_RESPOSTA = (
        "Você é um copiloto de negócios. Responda em português claro e conciso."
    )

    def __init__(
        self,
        config: Config,
        logger: logging.Logger,
        prompt_service: PromptService,
        metadata_service: MetadataService,
        gemini_service: GeminiService,
        sql_executor: SqlExecutor,
    ) -> None:
        super().__init__(config, logger)
        self._prompt_service = prompt_service
        self._metadata_service = metadata_service
        self._gemini_service = gemini_service
        self._sql_executor = sql_executor

    def executar(self, estado: Estado) -> Estado:
        """Executa pipeline: prompt -> SQL -> Azure SQL/DuckDB -> resposta natural."""
        try:
            prompt_sql = self._montar_prompt(estado)
            sql = self._gerar_sql(prompt_sql)
            estado["sql"] = sql

            dados = self._sql_executor.executar(sql)
            estado["dados"] = dados

            estado["resposta"] = self._formatar_resposta(estado, dados)
            return estado

        except Exception as exc:
            self.logger.exception("Erro no ConsultaAgent: %s", exc)
            estado["erro"] = str(exc)
            estado["resposta"] = f"Erro ao processar consulta: {exc}"
            return estado

    def _montar_prompt(self, estado: Estado) -> str:
        """Monta prompt de geração SQL com metadados e dicionário semântico."""
        pergunta = estado.get("pergunta", "")
        colunas = self._metadata_service.localizar_coluna(pergunta)
        colunas_texto = ", ".join(colunas) if colunas else "Nenhuma coluna identificada automaticamente."

        return self._prompt_service.preencher(
            "consulta",
            pergunta=pergunta,
            colunas_identificadas=colunas_texto,
            catalogo=self._metadata_service.obter_catalogo_texto(),
            tabelas=self._metadata_service.obter_tabelas_disponiveis(
                self.config.azure_sql_tabelas if self.config.fonte_dados == "azure" else ["base_tratada", "previsao_kpi"]
            ),
            nivel=estado.get("nivel", "B"),
        )

    def _gerar_sql(self, prompt: str) -> str:
        """Solicita SQL à LLM configurada via serviço dedicado."""
        sql = self._gemini_service.gerar_sql(prompt, self.SYSTEM_PROMPT_SQL)
        if not sql:
            raise ValueError("A LLM não retornou SQL válido.")
        self.logger.info("SQL gerado: %s", sql)
        return sql

    def _formatar_resposta(self, estado: Estado, dados: pd.DataFrame) -> str:
        """Formata resultado tabular em linguagem natural."""
        if dados.empty:
            return "Não encontrei registros para a sua pergunta com os filtros aplicados."

        amostra = dados.head(20)
        prompt = self._prompt_service.preencher(
            "formatar_resposta",
            pergunta=estado.get("pergunta", ""),
            dados=amostra.to_string(index=False),
        )
        return self._gemini_service.gerar(prompt, self.SYSTEM_PROMPT_RESPOSTA)
