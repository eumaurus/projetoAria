"""Coordenação central do fluxo da State Machine."""

from __future__ import annotations

import logging

from app.agentes.analytics_agent import AnalyticsAgent
from app.agentes.consulta_agent import ConsultaAgent
from app.agentes.rag_agent import RagAgent
from app.modelos.estado import Estado, Intencao
from app.orquestrador.roteador import Roteador
from app.servicos.base_service import BaseService
from app.servicos.config import Config
from app.servicos.controle_acesso import ControleAcesso


class Orquestrador(BaseService):
    """Gerencia validação, roteamento e execução de agentes."""

    def __init__(
        self,
        config: Config,
        logger: logging.Logger,
        controle_acesso: ControleAcesso,
        roteador: Roteador,
        consulta_agent: ConsultaAgent,
        rag_agent: RagAgent,
        analytics_agent: AnalyticsAgent,
    ) -> None:
        super().__init__(config, logger)
        self._controle_acesso = controle_acesso
        self._roteador = roteador
        self._consulta_agent = consulta_agent
        self._rag_agent = rag_agent
        self._analytics_agent = analytics_agent

    def executar(self, pergunta: str, email: str) -> Estado:
        """Executa o fluxo completo e retorna o estado enriquecido."""
        estado: Estado = {
            "pergunta": pergunta.strip(),
            "email": email.strip(),
        }

        try:
            nivel = self._controle_acesso.validar(email)
            estado["nivel"] = nivel.value

            intencao = self._roteador.classificar(pergunta)
            estado["intencao"] = intencao.value

            if intencao == Intencao.CONSULTA:
                estado["agente"] = "ConsultaAgent"
                return self._consulta_agent.executar(estado)

            if intencao == Intencao.RAG:
                estado["agente"] = "RagAgent"
                return self._rag_agent.executar(estado)

            if intencao == Intencao.ANALYTICS:
                estado["agente"] = "AnalyticsAgent"
                return self._analytics_agent.executar(estado)

            estado["agente"] = "Nenhum"
            estado["resposta"] = f"Intenção '{intencao.value}' não reconhecida."
            return estado

        except Exception as exc:
            self.logger.exception("Erro no orquestrador: %s", exc)
            estado["erro"] = str(exc)
            estado["resposta"] = f"Não foi possível processar sua solicitação: {exc}"
            return estado
