"""Conector de leitura para Azure SQL Database."""

from __future__ import annotations

import logging
import re

import pandas as pd

from app.servicos.base_service import BaseService
from app.servicos.config import Config

_SQL_PERIGOSO = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|"
    r"EXEC|EXECUTE|MERGE|INTO|XP_|SP_|OPENROWSET|OPENDATASOURCE)\b",
    re.IGNORECASE,
)


class AzureSqlService(BaseService):
    """Executa consultas de leitura (SELECT) no Azure SQL."""

    LIMITE_LINHAS = 500

    def __init__(self, config: Config, logger: logging.Logger) -> None:
        super().__init__(config, logger)

    def conexao_pronta(self) -> bool:
        return bool(self.config.azure_sql_server and self.config.azure_sql_database)

    def _string_conexao(self) -> str:
        if not self.conexao_pronta():
            raise ValueError(
                "Azure SQL não configurado. Defina AZURE_SQL_SERVER e AZURE_SQL_DATABASE no .env."
            )
        if not self.config.azure_sql_usuario or not self.config.azure_sql_senha:
            raise ValueError(
                "Credenciais Azure SQL ausentes. Defina AZURE_SQL_USUARIO e AZURE_SQL_SENHA no .env."
            )

        return (
            f"DRIVER={{{self.config.azure_sql_driver}}};"
            f"SERVER=tcp:{self.config.azure_sql_server},1433;"
            f"DATABASE={self.config.azure_sql_database};"
            f"UID={self.config.azure_sql_usuario};"
            f"PWD={self.config.azure_sql_senha};"
            "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
        )

    def _conectar(self):
        try:
            import pyodbc
        except ImportError as exc:
            raise ImportError(
                "Pacote pyodbc não instalado. Execute: py -m pip install pyodbc"
            ) from exc

        return pyodbc.connect(self._string_conexao())

    def _ler_dataframe(self, sql: str, params: tuple | None = None) -> pd.DataFrame:
        conexao = self._conectar()
        try:
            cursor = conexao.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            colunas = [coluna[0] for coluna in cursor.description] if cursor.description else []
            linhas = cursor.fetchall()
            return pd.DataFrame.from_records(linhas, columns=colunas)
        finally:
            conexao.close()

    def executar(self, sql: str) -> pd.DataFrame:
        """Executa SQL de leitura e retorna DataFrame."""
        sql_limpo = self._validar_select(sql)
        self.logger.info("Executando SQL no Azure: %s", sql_limpo[:400])
        resultado = self._ler_dataframe(sql_limpo)
        if len(resultado) > self.LIMITE_LINHAS:
            resultado = resultado.head(self.LIMITE_LINHAS)
        self.logger.info("Azure SQL retornou %d linha(s).", len(resultado))
        return resultado

    def descrever_tabelas(self) -> str:
        """Monta catálogo de colunas das tabelas autorizadas."""
        nomes = self.config.azure_sql_tabelas
        if not nomes:
            return "Nenhuma tabela Azure configurada em AZURE_SQL_TABELAS."

        placeholders = ",".join("?" for _ in nomes)
        nomes_simples = [self._nome_tabela(n) for n in nomes]
        consulta = f"""
            SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME IN ({placeholders})
            ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
        """

        try:
            df = self._ler_dataframe(consulta, tuple(nomes_simples))
        except Exception as exc:
            self.logger.error("Falha ao ler INFORMATION_SCHEMA: %s", exc)
            return f"Não foi possível ler o schema Azure: {exc}"

        if df.empty:
            return (
                "Tabelas Azure não encontradas no INFORMATION_SCHEMA. "
                f"Verifique AZURE_SQL_TABELAS={', '.join(nomes)}."
            )

        blocos: list[str] = []
        for (schema, tabela), grupo in df.groupby(["TABLE_SCHEMA", "TABLE_NAME"]):
            colunas = ", ".join(
                f"{linha.COLUMN_NAME} ({linha.DATA_TYPE})" for linha in grupo.itertuples()
            )
            blocos.append(f"Tabela `{schema}.{tabela}`: colunas [{colunas}]")
        return "\n".join(blocos)

    def listar_tabelas(self) -> list[str]:
        return list(self.config.azure_sql_tabelas)

    def nome_tabela_padrao(self) -> str:
        primeira = self.config.azure_sql_tabelas[0] if self.config.azure_sql_tabelas else "base_tratada"
        if "." in primeira:
            return primeira
        return f"{self.config.azure_sql_schema}.{primeira}"

    def _validar_select(self, sql: str) -> str:
        sql_limpo = sql.strip().rstrip(";")
        sql_sem_comentario = re.sub(r"--.*?$", "", sql_limpo, flags=re.MULTILINE)
        sql_sem_comentario = re.sub(r"/\*.*?\*/", "", sql_sem_comentario, flags=re.DOTALL).strip()

        if ";" in sql_sem_comentario:
            raise ValueError("Apenas uma instrução SQL é permitida.")

        inicio = sql_sem_comentario.lstrip().upper()
        if not (inicio.startswith("SELECT") or inicio.startswith("WITH")):
            raise ValueError("Somente consultas SELECT (ou WITH ... SELECT) são permitidas no Azure SQL.")

        if _SQL_PERIGOSO.search(sql_sem_comentario):
            raise ValueError("A consulta contém comandos não permitidos.")

        return sql_sem_comentario

    @staticmethod
    def _nome_tabela(nome: str) -> str:
        return nome.split(".")[-1].strip("[]")
