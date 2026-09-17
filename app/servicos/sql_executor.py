"""Execução de SQL: Azure SQL (produção) ou DuckDB local (fallback)."""

from __future__ import annotations

import logging
import re

import duckdb
import pandas as pd

from app.servicos.azure_sql_service import AzureSqlService
from app.servicos.base_service import BaseService
from app.servicos.config import Config
from app.servicos.data_service import DataService


class SqlExecutor(BaseService):
    """Roteia a execução SQL para Azure SQL ou DuckDB conforme a fonte configurada."""

    TABELAS_SUPORTE = {"rls", "dicionario_dados"}

    def __init__(
        self,
        config: Config,
        logger: logging.Logger,
        data_service: DataService,
        azure_sql_service: AzureSqlService | None = None,
    ) -> None:
        super().__init__(config, logger)
        self._data_service = data_service
        self._azure_sql_service = azure_sql_service

    def executar(self, sql: str, tabelas: tuple[str, ...] | None = None) -> pd.DataFrame:
        """Executa SQL na fonte de dados ativa."""
        if self.config.fonte_dados == "azure":
            if not self._azure_sql_service:
                raise RuntimeError("Fonte Azure configurada, mas AzureSqlService não foi injetado.")
            return self._azure_sql_service.executar(sql)
        return self._executar_duckdb(sql, tabelas)

    def _executar_duckdb(self, sql: str, tabelas: tuple[str, ...] | None) -> pd.DataFrame:
        nomes = tabelas or self._tabelas_duckdb()
        conexao = duckdb.connect(database=":memory:")

        try:
            for nome in nomes:
                df = self._data_service.obter(nome)
                conexao.register(nome, df)
                self.logger.debug("Tabela registrada no DuckDB: %s", nome)

            sql_duckdb = self._adaptar_sql_duckdb(sql)
            resultado = conexao.execute(sql_duckdb).fetchdf()
            self.logger.info("SQL DuckDB executado com sucesso (%d linhas).", len(resultado))
            return resultado
        except Exception as exc:
            self.logger.error("Erro ao executar SQL DuckDB: %s", exc)
            raise
        finally:
            conexao.close()

    def _tabelas_duckdb(self) -> tuple[str, ...]:
        configuradas = tuple(
            tabela.split(".")[-1].strip("[]")
            for tabela in self.config.azure_sql_tabelas
            if tabela.split(".")[-1].strip("[]") in self._data_service.listar()
        )
        if configuradas:
            return configuradas

        return tuple(
            nome for nome in self._data_service.listar()
            if nome not in self.TABELAS_SUPORTE
        )

    @staticmethod
    def _adaptar_sql_duckdb(sql: str) -> str:
        sql_limpo = sql.strip().rstrip(";")
        sql_limpo = re.sub(r"\[([^\]]+)\]", r'"\1"', sql_limpo)

        match_top = re.match(r"(?is)^\s*select\s+top\s+(\d+)\s+", sql_limpo)
        if not match_top:
            return sql_limpo

        limite = match_top.group(1)
        sql_sem_top = re.sub(r"(?is)^\s*select\s+top\s+\d+\s+", "SELECT ", sql_limpo, count=1)
        if re.search(r"(?is)\blimit\s+\d+\s*$", sql_sem_top):
            return sql_sem_top
        return f"{sql_sem_top} LIMIT {limite}"
