"""Agente especialista em recuperação e explicação de conceitos (RAG)."""

from __future__ import annotations

import logging

from app.modelos.estado import Estado
from app.servicos.base_service import BaseService
from app.servicos.config import Config
from app.orquestrador.grafo_rag import GrafoRag


class RagAgent(BaseService):
    """Recupera contexto do dicionário e gera resposta explicativa."""

    def __init__(
        self,
        config: Config,
        logger: logging.Logger,
        grafo_rag: GrafoRag,
    ) -> None:
        super().__init__(config, logger)
        self._grafo_rag = grafo_rag

    def executar(self, estado: Estado) -> Estado:
        """Executa pipeline RAG: busca contexto -> prompt -> resposta."""
        try:
            resultado = self._grafo_rag.executar(
                pergunta=estado.get("pergunta", ""),
                nivel=estado.get("nivel", "B"),
            )
            estado["contexto"] = resultado.get("contexto", "")
            estado["resposta"] = resultado.get("resposta", "")
            return estado

        except Exception as exc:
            self.logger.exception("Erro no RagAgent: %s", exc)
            estado["erro"] = str(exc)
            estado["resposta"] = f"Erro ao processar pergunta conceitual: {exc}"
            return estado

