"""Recuperação de contexto a partir do dicionário de dados."""

from __future__ import annotations

import logging
import re
import unicodedata

import pandas as pd

from app.servicos.base_service import BaseService
from app.servicos.config import Config
from app.servicos.data_service import DataService


class RagService(BaseService):
    """Busca semântica simples no catálogo de metadados (MVP RAG)."""

    NOME_DICIONARIO = "dicionario_dados"

    def __init__(
        self,
        config: Config,
        logger: logging.Logger,
        data_service: DataService,
    ) -> None:
        super().__init__(config, logger)
        self._data_service = data_service

    def buscar_contexto(self, pergunta: str, limite: int = 5) -> str:
        """Recupera trechos relevantes do dicionário para a pergunta."""
        try:
            df = self._data_service.obter(self.NOME_DICIONARIO)
        except KeyError:
            return "Nenhum contexto disponível — dicionario_dados.xlsx não encontrado."

        colunas = {self._normalizar(c): c for c in df.columns}
        col_tecnica = self._resolver_coluna(colunas, ["coluna_tecnica", "coluna", "campo"])
        col_sinonimo = self._resolver_coluna(colunas, ["sinonimo", "sinonimos", "termo"])
        col_descricao = self._resolver_coluna(colunas, ["descricao", "description", "definicao"])

        if not col_tecnica:
            return "Dicionário de dados inválido para recuperação de contexto."

        tokens = self._tokenizar(pergunta)
        if not tokens:
            return "Nenhum contexto relevante encontrado para a pergunta."

        pontuados: list[tuple[int, str]] = []
        for _, linha in df.iterrows():
            tecnica = str(linha[col_tecnica]).strip()
            if not tecnica or tecnica.lower() == "nan":
                continue

            texto_linha = tecnica
            if col_sinonimo and pd.notna(linha[col_sinonimo]):
                texto_linha += " " + str(linha[col_sinonimo])
            if col_descricao and pd.notna(linha[col_descricao]):
                texto_linha += " " + str(linha[col_descricao])

            score = self._calcular_score(tokens, texto_linha)
            if score <= 0:
                continue

            descricao = ""
            if col_descricao and pd.notna(linha[col_descricao]):
                descricao = str(linha[col_descricao]).strip()

            sinonimos = ""
            if col_sinonimo and pd.notna(linha[col_sinonimo]):
                sinonimos = str(linha[col_sinonimo]).strip()

            trecho = (
                f"- **{tecnica}**: {descricao or 'Sem descrição.'}"
                + (f" (sinônimos: {sinonimos})" if sinonimos else "")
            )
            pontuados.append((score, trecho))

        if not pontuados:
            return "Nenhum contexto relevante encontrado no dicionário de dados."

        pontuados.sort(key=lambda x: x[0], reverse=True)
        selecionados = [trecho for _, trecho in pontuados[:limite]]
        self.logger.info("RAG recuperou %d trecho(s) de contexto.", len(selecionados))
        return "\n".join(selecionados)

    @staticmethod
    def _normalizar(texto: str) -> str:
        texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
        return re.sub(r"\s+", " ", texto.lower().strip())

    @staticmethod
    def _tokenizar(texto: str) -> set[str]:
        texto_norm = RagService._normalizar(texto)
        return {t for t in re.findall(r"[a-z0-9]+", texto_norm) if len(t) > 2}

    @staticmethod
    def _calcular_score(tokens: set[str], texto: str) -> int:
        texto_norm = RagService._normalizar(texto)
        return sum(1 for token in tokens if token in texto_norm)

    @staticmethod
    def _resolver_coluna(colunas: dict[str, str], candidatos: list[str]) -> str | None:
        for candidato in candidatos:
            if candidato in colunas:
                return colunas[candidato]
        return None
