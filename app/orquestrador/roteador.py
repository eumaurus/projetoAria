"""Classificação de intenção do usuário."""

from __future__ import annotations

import logging
import re
import unicodedata

from app.modelos.estado import Intencao
from app.servicos.base_service import BaseService
from app.servicos.config import Config


class Roteador(BaseService):
    """Roteia perguntas para CONSULTA, RAG ou ANALYTICS via palavras-chave."""

    PALAVRAS_CONSULTA = (
        "quanto", "qual", "quais", "total", "soma", "média", "media",
        "incidente", "incidentes", "chamado", "chamados", "ticket",
        "prioridade", "status", "grupo", "equipe", "time", "duração", "duracao",
        "kpi", "violado", "listar", "mostrar", "top", "quantos",
    )
    PALAVRAS_RAG = (
        "o que é", "o que e", "como funciona", "definição", "definicao",
        "documentação", "documentacao", "significado", "explicar", "glossário",
        "glossario", "o que significa", "conceito", "campo", "coluna",
    )
    PALAVRAS_ANALYTICS = (
        "tendência", "tendencia", "previsão", "previsao", "forecast",
        "projeção", "projecao", "análise avançada", "analise avancada",
        "correlação", "correlacao", "cluster", "anomalia", "volume",
        "atingimento", "dia da semana", "fim de semana", "evolução", "evolucao",
    )

    def __init__(self, config: Config, logger: logging.Logger) -> None:
        super().__init__(config, logger)

    def classificar(self, pergunta: str) -> Intencao:
        """Classifica a intenção com base em palavras-chave (MVP)."""
        texto = self._normalizar(pergunta)

        score_rag = self._contar_matches(texto, self.PALAVRAS_RAG)
        score_analytics = self._contar_matches(texto, self.PALAVRAS_ANALYTICS)
        score_consulta = self._contar_matches(texto, self.PALAVRAS_CONSULTA)

        if score_rag > 0 and score_rag >= score_analytics:
            melhor = Intencao.RAG
        elif score_analytics > 0:
            melhor = Intencao.ANALYTICS
        elif score_consulta > 0:
            melhor = Intencao.CONSULTA
        else:
            melhor = Intencao.CONSULTA

        pontuacao = {
            Intencao.RAG: score_rag,
            Intencao.ANALYTICS: score_analytics,
            Intencao.CONSULTA: score_consulta,
        }
        self.logger.info("Intenção classificada: %s (scores=%s)", melhor, pontuacao)
        return melhor

    @staticmethod
    def _normalizar(texto: str) -> str:
        texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
        return re.sub(r"\s+", " ", texto.lower().strip())

    @staticmethod
    def _contar_matches(texto: str, palavras: tuple[str, ...]) -> int:
        return sum(1 for palavra in palavras if palavra in texto)
