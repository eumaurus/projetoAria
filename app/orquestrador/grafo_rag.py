"""Grafo RAG com LangGraph: recuperar chunks -> gerar resposta."""

from __future__ import annotations

import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.servicos.base_service import BaseService
from app.servicos.config import Config
from app.servicos.gemini_service import GeminiService
from app.servicos.prompt_service import PromptService
from app.servicos.vetor_service import VetorService


class EstadoRag(TypedDict, total=False):
    """Estado interno do subgrafo RAG."""

    pergunta: str
    nivel: str
    chunks: list[str]
    contexto: str
    resposta: str


class GrafoRag(BaseService):
    """Orquestra recuperação vetorial e geração de resposta."""

    SYSTEM_PROMPT = (
        "Você explica conceitos de dados comerciais com base no contexto fornecido. "
        "Não invente definições fora do contexto."
    )

    def __init__(
        self,
        config: Config,
        logger: logging.Logger,
        vetor_service: VetorService,
        prompt_service: PromptService,
        gemini_service: GeminiService,
    ) -> None:
        super().__init__(config, logger)
        self._vetor_service = vetor_service
        self._prompt_service = prompt_service
        self._gemini_service = gemini_service
        self._app = self._compilar()

    def executar(self, pergunta: str, nivel: str = "B") -> EstadoRag:
        """Dispara o grafo LangGraph e devolve o estado final."""
        inicial: EstadoRag = {
            "pergunta": pergunta,
            "nivel": nivel,
            "chunks": [],
            "contexto": "",
            "resposta": "",
        }
        saida = self._app.invoke(inicial)
        return saida  # type: ignore[return-value]

    def _compilar(self):
        grafo = StateGraph(EstadoRag)
        grafo.add_node("recuperar", self._recuperar)
        grafo.add_node("gerar", self._gerar)
        grafo.add_edge(START, "recuperar")
        grafo.add_edge("recuperar", "gerar")
        grafo.add_edge("gerar", END)
        return grafo.compile()

    def _recuperar(self, estado: EstadoRag) -> dict:
        documentos = self._vetor_service.buscar(estado.get("pergunta", ""))
        chunks = [doc.page_content for doc in documentos]
        if not chunks:
            contexto = "Nenhum contexto relevante encontrado no índice vetorial."
        else:
            partes: list[str] = []
            for indice, doc in enumerate(documentos, start=1):
                fonte = doc.metadata.get("fonte", "desconhecida")
                partes.append(f"[Chunk {indice} | fonte: {fonte}]\n{doc.page_content}")
            contexto = "\n\n".join(partes)
        self.logger.info("Nó recuperar: %d chunk(s).", len(chunks))
        return {"chunks": chunks, "contexto": contexto}

    def _gerar(self, estado: EstadoRag) -> dict:
        prompt = self._prompt_service.preencher(
            "rag",
            pergunta=estado.get("pergunta", ""),
            contexto=estado.get("contexto", ""),
            nivel=estado.get("nivel", "B"),
        )
        resposta = self._gemini_service.gerar(prompt, self.SYSTEM_PROMPT)
        return {"resposta": resposta}
