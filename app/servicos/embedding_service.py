"""Geração de embeddings via LangChain (local ONNX, Vertex ou fake)."""

from __future__ import annotations

import logging
import hashlib
import json
import re
import unicodedata
from urllib import error, request

from langchain_core.embeddings import Embeddings, FakeEmbeddings

from app.servicos.base_service import BaseService
from app.servicos.config import Config


class EmbeddingChromaOnnx(Embeddings):
    """Embeddings locais do Chroma (all-MiniLM via ONNX), sem PyTorch."""

    def __init__(self) -> None:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        self._funcao = DefaultEmbeddingFunction()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return list(self._funcao(texts))

    def embed_query(self, text: str) -> list[float]:
        return list(self._funcao([text])[0])


class EmbeddingHashLocal(Embeddings):
    """Embedding local determinístico, sem download de modelo externo.

    É adequado ao modo offline e mantém o mesmo vetor para um texto entre
    reinicializações, o que é essencial para um índice Chroma persistido.
    """

    def __init__(self, tamanho: int = 384) -> None:
        self._tamanho = tamanho

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vetor(texto) for texto in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vetor(text)

    def _vetor(self, texto: str) -> list[float]:
        normalizado = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
        tokens = re.findall(r"[a-z0-9_]+", normalizado.lower())
        vetor = [0.0] * self._tamanho
        for token in tokens:
            indice = int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:4], "big") % self._tamanho
            vetor[indice] += 1.0
        norma = sum(valor * valor for valor in vetor) ** 0.5
        return [valor / norma for valor in vetor] if norma else vetor


class EmbeddingService(BaseService):
    """Fornece a implementação de embeddings conforme EMBEDDING_MODO."""

    def __init__(self, config: Config, logger: logging.Logger) -> None:
        super().__init__(config, logger)
        self._embeddings: Embeddings | None = None

    def obter(self) -> Embeddings:
        if self._embeddings is None:
            self._embeddings = self._criar()
        return self._embeddings

    def _criar(self) -> Embeddings:
        modo = self.config.embedding_modo
        if modo == "fake":
            self.logger.info("Embeddings em modo FAKE (vetores sintéticos).")
            return FakeEmbeddings(size=384)

        if modo == "vertex":
            try:
                from langchain_google_vertexai import VertexAIEmbeddings

                self.logger.info("Embeddings Vertex AI: text-embedding-004")
                return VertexAIEmbeddings(
                    model_name="text-embedding-004",
                    project=self.config.google_cloud_project or None,
                    location=self.config.google_cloud_location,
                )
            except Exception as exc:
                self.logger.warning("Falha ao iniciar Vertex embeddings (%s). Usando local.", exc)

        if modo == "azure_openai":
            self.logger.info(
                "Embeddings Azure OpenAI: deployment=%s",
                self.config.azure_openai_embedding_deployment,
            )
            return AzureOpenAIEmbeddingFunction(self.config, self.logger)

        self.logger.info("Embeddings locais determinísticos (hashing, sem download de modelo).")
        return EmbeddingHashLocal()


class AzureOpenAIEmbeddingFunction(Embeddings):
    """Embeddings via Azure OpenAI REST API."""

    def __init__(self, config: Config, logger: logging.Logger) -> None:
        if not config.azure_openai_endpoint or not config.azure_openai_api_key:
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT/AZURE_OPENAI_API_KEY não configurados."
            )
        self._config = config
        self._logger = logger

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        textos = [texto if texto is not None else "" for texto in texts]
        if not textos:
            return []
        vetores: list[list[float]] = []
        for inicio in range(0, len(textos), 16):
            lote = textos[inicio:inicio + 16]
            vetores.extend(self._chamar_api(lote))
        return vetores

    def embed_query(self, text: str) -> list[float]:
        return self._chamar_api([text])[0]

    def _chamar_api(self, textos: list[str]) -> list[list[float]]:
        endpoint = (
            f"{self._config.azure_openai_endpoint}/openai/deployments/"
            f"{self._config.azure_openai_embedding_deployment}/embeddings"
            f"?api-version={self._config.azure_openai_api_version}"
        )
        payload = {"input": textos}
        req = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "api-key": self._config.azure_openai_api_key,
            },
        )
        try:
            with request.urlopen(req, timeout=120) as resposta:
                dados = json.loads(resposta.read().decode("utf-8"))
        except error.HTTPError as exc:
            corpo = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Erro Azure OpenAI embeddings ({exc.code}): {corpo}") from exc

        itens = dados.get("data") or []
        if len(itens) != len(textos):
            raise RuntimeError(f"Resposta inesperada de embeddings Azure OpenAI: {dados}")
        return [item["embedding"] for item in itens]
