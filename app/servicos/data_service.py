"""Carregamento e disponibilização de arquivos Excel da pasta dados/."""

from __future__ import annotations

import logging

import pandas as pd

from app.servicos.base_service import BaseService
from app.servicos.config import Config


class DataService(BaseService):
    """Escaneia a pasta de dados e mantém DataFrames em memória."""

    def __init__(self, config: Config, logger: logging.Logger) -> None:
        super().__init__(config, logger)
        self._cache: dict[str, pd.DataFrame] = {}
        self._carregar_arquivos()

    def _carregar_arquivos(self) -> None:
        pasta = self.config.pasta_dados
        if not pasta.exists():
            self.logger.warning("Pasta de dados não encontrada: %s", pasta)
            return

        for arquivo in pasta.glob("*.xlsx"):
            nome_base = arquivo.stem
            try:
                self._cache[nome_base] = pd.read_excel(arquivo)
                self.logger.info("Arquivo carregado: %s (%d linhas)", nome_base, len(self._cache[nome_base]))
            except Exception as exc:
                self.logger.error("Falha ao carregar %s: %s", arquivo.name, exc)

    def obter(self, nome_base: str) -> pd.DataFrame:
        """Retorna DataFrame pelo nome base do arquivo (sem extensão)."""
        if nome_base not in self._cache:
            raise KeyError(f"Dataset '{nome_base}' não encontrado em {self.config.pasta_dados}")
        return self._cache[nome_base].copy()

    def obter_todos(self) -> dict[str, pd.DataFrame]:
        """Retorna cópia de todos os datasets carregados."""
        return {nome: df.copy() for nome, df in self._cache.items()}

    def listar(self) -> list[str]:
        """Lista nomes base disponíveis."""
        return list(self._cache.keys())

    def recarregar(self) -> None:
        """Recarrega todos os arquivos Excel da pasta de dados."""
        self._cache.clear()
        self._carregar_arquivos()
