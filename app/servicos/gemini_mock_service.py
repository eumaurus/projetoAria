"""Implementação offline do Gemini para desenvolvimento local."""

from __future__ import annotations

import logging
import re

from app.servicos.base_service import BaseService
from app.servicos.config import Config


class GeminiMockService(BaseService):
    """Simula respostas do Gemini sem chamadas ao Vertex AI."""

    def __init__(self, config: Config, logger: logging.Logger) -> None:
        super().__init__(config, logger)
        self.logger.info("Gemini em modo MOCK — respostas simuladas localmente.")

    def gerar(self, prompt: str, system_prompt: str = "") -> str:
        """Gera texto simulado conforme o tipo de prompt detectado."""
        if "Contexto recuperado" in prompt or "## Contexto" in prompt:
            return self._responder_rag(prompt)

        if "Métricas calculadas" in prompt or "## Métricas" in prompt:
            return self._responder_analytics(prompt)

        if "Resultado da consulta" in prompt:
            return self._formatar_resultado_consulta(prompt)

        pergunta = self._extrair_campo(prompt, "Pergunta")
        return (
            f"[MOCK] Resposta simulada para: {pergunta or 'solicitação não identificada'}. "
            "Configure a integração real do Gemini para respostas em produção."
        )

    def gerar_sql(self, prompt: str, system_prompt: str = "") -> str:
        """Gera SQL T-SQL heurístico a partir da pergunta."""
        pergunta = self._extrair_campo(prompt, "Pergunta do usuário") or prompt
        pergunta_lower = pergunta.lower()
        tabela_incidentes = "base_tratada"
        tabela_previsao = "previsao_kpi"

        if any(p in pergunta_lower for p in ("previs", "previsto", "d1", "d7", "volume", "atingimento")):
            if "d7" in pergunta_lower:
                sql = (
                    f'SELECT "data", "volume_total_real", "volume_total_previsto_d7", '
                    f'"taxa_atingimento_kpi_real", "taxa_atingimento_kpi_previsto_d7" '
                    f'FROM {tabela_previsao} ORDER BY "data" DESC LIMIT 30'
                )
            elif "d1" in pergunta_lower:
                sql = (
                    f'SELECT "data", "volume_total_real", "volume_total_previsto_d1", '
                    f'"taxa_atingimento_kpi_real", "taxa_atingimento_kpi_previsto_d1" '
                    f'FROM {tabela_previsao} ORDER BY "data" DESC LIMIT 30'
                )
            else:
                sql = (
                    f'SELECT "dia_semana", AVG("volume_total_real") AS volume_medio_real, '
                    f'AVG("taxa_atingimento_kpi_real") AS taxa_media_kpi '
                    f'FROM {tabela_previsao} GROUP BY "dia_semana" ORDER BY volume_medio_real DESC'
                )
        elif any(p in pergunta_lower for p in ("prioridade", "criticidade", "severidade")):
            sql = (
                f'SELECT "Prioridade", COUNT(*) AS total_incidentes '
                f'FROM {tabela_incidentes} GROUP BY "Prioridade" ORDER BY total_incidentes DESC'
            )
        elif any(p in pergunta_lower for p in ("status", "situação", "situacao")):
            sql = (
                f'SELECT "Status", COUNT(*) AS total_incidentes '
                f'FROM {tabela_incidentes} GROUP BY "Status" ORDER BY total_incidentes DESC'
            )
        elif any(p in pergunta_lower for p in ("grupo", "time", "equipe")):
            sql = (
                f'SELECT "Grupo designado", COUNT(*) AS total_incidentes '
                f'FROM {tabela_incidentes} GROUP BY "Grupo designado" ORDER BY total_incidentes DESC LIMIT 20'
            )
        elif any(p in pergunta_lower for p in ("kpi violado", "violação", "violacao")):
            sql = (
                f'SELECT "KPI Violado?", COUNT(*) AS total_incidentes '
                f'FROM {tabela_incidentes} GROUP BY "KPI Violado?" ORDER BY total_incidentes DESC'
            )
        elif any(p in pergunta_lower for p in ("duração", "duracao", "tempo")):
            sql = (
                f'SELECT AVG("Duração") AS duracao_media, MEDIAN("Duração") AS duracao_mediana, '
                f'MAX("Duração") AS duracao_maxima FROM {tabela_incidentes}'
            )
        elif any(p in pergunta_lower for p in ("listar", "mostrar", "quais", "ultimos", "últimos", "recentes")):
            sql = (
                f'SELECT "Número", "Prioridade", "Grupo designado", "Status", "Duração", "Data" '
                f'FROM {tabela_incidentes} ORDER BY "Data" DESC LIMIT 100'
            )
        else:
            sql = (
                f'SELECT "Número", "Prioridade", "Status", "Grupo designado", "Entrou para KPI?", "KPI Violado?" '
                f'FROM {tabela_incidentes} ORDER BY "Data" DESC LIMIT 20'
            )

        self.logger.info("SQL mock gerado: %s", sql)
        return sql

    def _responder_rag(self, prompt: str) -> str:
        contexto = self._extrair_campo(prompt, "Contexto recuperado") or self._extrair_bloco(
            prompt, "## Contexto recuperado"
        )
        pergunta = self._extrair_campo(prompt, "Pergunta do usuário") or self._extrair_bloco(
            prompt, "## Pergunta"
        )

        if not contexto or "Nenhum contexto" in contexto:
            return (
                "Não encontrei contexto suficiente nas bases de incidentes e previsão para responder isso. "
                "Tente mencionar colunas, KPIs, prioridades, grupos ou previsões disponíveis."
            )

        return (
            f"Com base no contexto indexado das bases, segue a explicação sobre "
            f"\"{pergunta.strip()}\":\n\n{contexto.strip()}"
        )

    def _responder_analytics(self, prompt: str) -> str:
        metricas = self._extrair_campo(prompt, "Métricas calculadas") or self._extrair_bloco(
            prompt, "## Métricas calculadas"
        )
        pergunta = self._extrair_campo(prompt, "Pergunta do usuário") or self._extrair_bloco(
            prompt, "## Pergunta"
        )

        if not metricas:
            return "Não foi possível calcular métricas analíticas para essa pergunta."

        return (
            f"Análise simulada (modo offline) para: {pergunta.strip()}\n\n"
            f"{metricas.strip()}\n\n"
            "Interpretação: os valores acima refletem agregações sobre base_tratada e previsao_kpi. "
            "Ative a integração real do Gemini para interpretações mais profundas."
        )

    def _formatar_resultado_consulta(self, prompt: str) -> str:
        pergunta = self._extrair_campo(prompt, "Pergunta original") or ""
        bloco_dados = self._extrair_campo(prompt, "Resultado da consulta") or ""

        if not bloco_dados.strip():
            return "Não encontrei registros para a sua pergunta com os filtros aplicados."

        linhas = [l for l in bloco_dados.strip().splitlines() if l.strip()]
        if len(linhas) <= 1:
            return f"Resultado para \"{pergunta}\": {bloco_dados.strip()}"

        return (
            f"Com base nos dados consultados para \"{pergunta}\", "
            f"encontrei {max(len(linhas) - 1, 1)} registro(s). "
            f"Principais valores:\n\n{bloco_dados.strip()}"
        )

    @staticmethod
    def _extrair_campo(prompt: str, rotulo: str) -> str:
        padrao = rf"##\s*{re.escape(rotulo)}\s*\n(.*?)(?:\n##|\Z)"
        match = re.search(padrao, prompt, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()

        padrao_simples = rf"{re.escape(rotulo)}\s*\n(.*?)(?:\n##|\Z)"
        match = re.search(padrao_simples, prompt, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _extrair_bloco(prompt: str, marcador: str) -> str:
        if marcador not in prompt:
            return ""
        return prompt.split(marcador, 1)[1].split("\n##", 1)[0].strip()
