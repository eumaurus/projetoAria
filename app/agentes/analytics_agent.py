"""Agente especialista em análises estatísticas e tendências."""

from __future__ import annotations

import logging

from app.modelos.estado import Estado
from app.servicos.analytics_service import AnalyticsService
from app.servicos.base_service import BaseService
from app.servicos.config import Config
from app.servicos.gemini_service import GeminiService
from app.servicos.prompt_service import PromptService


class AnalyticsAgent(BaseService):
    """Calcula métricas locais e interpreta resultados via LLM."""

    SYSTEM_PROMPT = (
        "Você interpreta métricas de negócio. "
        "Baseie-se apenas nos números fornecidos e seja conciso."
    )

    def __init__(
        self,
        config: Config,
        logger: logging.Logger,
        prompt_service: PromptService,
        analytics_service: AnalyticsService,
        gemini_service: GeminiService,
    ) -> None:
        super().__init__(config, logger)
        self._prompt_service = prompt_service
        self._analytics_service = analytics_service
        self._gemini_service = gemini_service

    def executar(self, estado: Estado) -> Estado:
        """Executa pipeline analítico: métricas -> prompt -> interpretação."""
        try:
            metricas = self._calcular_metricas(estado)
            estado["contexto"] = metricas

            prompt = self._montar_prompt(estado, metricas)
            estado["resposta"] = self._gemini_service.gerar(prompt, self.SYSTEM_PROMPT)
            return estado

        except Exception as exc:
            self.logger.exception("Erro no AnalyticsAgent: %s", exc)
            estado["erro"] = str(exc)
            estado["resposta"] = f"Erro ao processar análise: {exc}"
            return estado

    def _calcular_metricas(self, estado: Estado) -> str:
        return self._analytics_service.calcular_metricas(estado.get("pergunta", ""))

    def _montar_prompt(self, estado: Estado, metricas: str) -> str:
        return self._prompt_service.preencher(
            "analytics",
            pergunta=estado.get("pergunta", ""),
            metricas=metricas,
            nivel=estado.get("nivel", "B"),
        )
