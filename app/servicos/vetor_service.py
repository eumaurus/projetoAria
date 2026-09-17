"""Banco de dados vetorial (Chroma local ou Azure AI Search)."""

from __future__ import annotations

import logging
import json
import shutil
from hashlib import sha256
from urllib import error, request

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.servicos.base_service import BaseService
from app.servicos.chunk_service import ChunkService
from app.servicos.config import Config
from app.servicos.embedding_service import EmbeddingService


class VetorService(BaseService):
    """Indexa chunks e executa busca por similaridade."""

    COLECAO = "lux_rag"
    MANIFESTO = "source_manifest.json"
    SEARCH_API_VERSION = "2024-07-01"
    VECTOR_FIELD = "contentVector"

    def __init__(
        self,
        config: Config,
        logger: logging.Logger,
        embedding_service: EmbeddingService,
        chunk_service: ChunkService,
    ) -> None:
        super().__init__(config, logger)
        self._embedding_service = embedding_service
        self._chunk_service = chunk_service
        self._store: Chroma | None = None
        self._indice_pronto = False

    def embeddings(self) -> Embeddings:
        return self._embedding_service.obter()

    def garantir_indice(self, forcar: bool = False) -> None:
        """Cria ou reutiliza o índice persistido no disco."""
        if self.config.vector_store_provider == "azure_search":
            self._garantir_indice_azure(forcar=forcar)
            self._indice_pronto = True
            return

        pasta = self.config.pasta_vetores
        pasta.mkdir(parents=True, exist_ok=True)
        manifesto_atual = self._manifesto_atual()
        manifesto_salvo = self._manifesto_salvo()

        if forcar and pasta.exists():
            shutil.rmtree(pasta, ignore_errors=True)
            pasta.mkdir(parents=True, exist_ok=True)
            self._store = None

        store = self._abrir_store()
        quantidade = self._contar(store)
        if quantidade == 0 or forcar or manifesto_atual != manifesto_salvo:
            self.indexar(store)
            self._salvar_manifesto(manifesto_atual)
            # indexar recria a coleção para evitar chunks antigos; portanto o
            # objeto anterior não representa mais a coleção corrente.
            quantidade = self._contar(self._abrir_store())
        self.logger.info("Índice vetorial pronto (%d vetores) em %s", quantidade, pasta)
        self._indice_pronto = True

    def indexar(self, store: Chroma | None = None) -> int:
        """Gera chunks, embeddings e grava no Chroma."""
        if self.config.vector_store_provider == "azure_search":
            return self._indexar_azure()

        store = store or self._abrir_store()
        chunks = self._chunk_service.dividir()
        if not chunks:
            self.logger.warning("Nenhum chunk para indexar.")
            return 0

        # IDs determinísticos evitam duplicação e tornam a reindexação reprodutível.
        ids = [self._id_chunk(chunk) for chunk in chunks]
        try:
            store.delete_collection()
        except Exception:
            pass
        self._store = None
        store = self._abrir_store()
        store.add_documents(documents=chunks, ids=ids)
        self.logger.info("Indexados %d chunks no Chroma.", len(chunks))
        return len(chunks)

    def buscar(self, pergunta: str, k: int | None = None) -> list[Document]:
        """Recupera os k chunks mais similares à pergunta."""
        if not self._indice_pronto:
            self.garantir_indice()

        if self.config.vector_store_provider == "azure_search":
            return self._buscar_azure(pergunta, k=k)

        limite = k or self.config.rag_k
        store = self._abrir_store()
        if self._contar(store) == 0:
            return []
        documentos = store.similarity_search(pergunta, k=limite)
        self.logger.info("Busca vetorial retornou %d chunk(s).", len(documentos))
        return documentos

    def _abrir_store(self) -> Chroma:
        if self._store is None:
            self._store = Chroma(
                collection_name=self.COLECAO,
                embedding_function=self.embeddings(),
                persist_directory=str(self.config.pasta_vetores),
            )
        return self._store

    @staticmethod
    def _contar(store: Chroma) -> int:
        try:
            return int(store._collection.count())  # noqa: SLF001
        except Exception:
            return 0

    @staticmethod
    def _id_chunk(chunk: Document) -> str:
        origem = str(chunk.metadata.get("fonte", ""))
        conteudo = f"{origem}\n{chunk.page_content}".encode("utf-8")
        return f"chunk-{sha256(conteudo).hexdigest()}"

    def _manifesto_atual(self) -> dict:
        arquivos_contexto: list[dict[str, str | int]] = []
        for arquivo in sorted(self.config.pasta_dados.glob("*.xlsx")):
            if arquivo.stem in {"rls"}:
                continue
            stat = arquivo.stat()
            arquivos_contexto.append(
                {
                    "arquivo": arquivo.name,
                    "tamanho": int(stat.st_size),
                    "mtime_ns": int(stat.st_mtime_ns),
                }
            )

        for arquivo in sorted(self.config.pasta_conhecimento.rglob("*")):
            if not arquivo.is_file():
                continue
            stat = arquivo.stat()
            arquivos_contexto.append(
                {
                    "arquivo": str(arquivo.relative_to(self.config.raiz_projeto)),
                    "tamanho": int(stat.st_size),
                    "mtime_ns": int(stat.st_mtime_ns),
                }
            )

        return {
            "arquivos": arquivos_contexto,
            "chunk_tamanho": self.config.chunk_tamanho,
            "chunk_sobreposicao": self.config.chunk_sobreposicao,
            "rag_k": self.config.rag_k,
        }

    def _manifesto_salvo(self) -> dict | None:
        caminho = self.config.pasta_vetores / self.MANIFESTO
        if not caminho.exists():
            return None
        try:
            return json.loads(caminho.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _salvar_manifesto(self, manifesto: dict) -> None:
        caminho = self.config.pasta_vetores / self.MANIFESTO
        caminho.write_text(
            json.dumps(manifesto, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _garantir_indice_azure(self, forcar: bool = False) -> None:
        manifesto_atual = self._manifesto_atual()
        manifesto_salvo = self._manifesto_salvo()
        self._criar_indice_azure()
        quantidade = self._contar_azure()
        deve_reindexar = quantidade == 0 or forcar
        if not deve_reindexar and manifesto_salvo is not None:
            deve_reindexar = manifesto_atual != manifesto_salvo
        if deve_reindexar:
            quantidade = self._indexar_azure()
            self._salvar_manifesto(manifesto_atual)
        self.logger.info(
            "Índice vetorial Azure pronto (%d vetores) em %s",
            quantidade,
            self.config.azure_search_index,
        )

    def _indexar_azure(self) -> int:
        chunks = self._chunk_service.dividir()
        if not chunks:
            self.logger.warning("Nenhum chunk para indexar no Azure AI Search.")
            return 0

        self._criar_indice_azure()
        self._limpar_documentos_azure()

        ids = [self._id_chunk(chunk) for chunk in chunks]
        vetores = self.embeddings().embed_documents([chunk.page_content for chunk in chunks])
        documentos = []
        for identificador, chunk, vetor in zip(ids, chunks, vetores, strict=True):
            documentos.append(
                {
                    "@search.action": "upload",
                    "id": identificador,
                    "content": chunk.page_content,
                    "fonte": str(chunk.metadata.get("fonte", "")),
                    "metadata_json": json.dumps(chunk.metadata, ensure_ascii=False),
                    self.VECTOR_FIELD: vetor,
                }
            )

        for inicio in range(0, len(documentos), 100):
            lote = {"value": documentos[inicio:inicio + 100]}
            self._request_azure(
                "POST",
                f"/indexes/{self.config.azure_search_index}/docs/index",
                payload=lote,
            )

        self.logger.info("Indexados %d chunks no Azure AI Search.", len(documentos))
        return len(documentos)

    def _buscar_azure(self, pergunta: str, k: int | None = None) -> list[Document]:
        limite = k or self.config.rag_k
        if self._contar_azure() == 0:
            return []

        vetor = self.embeddings().embed_query(pergunta)
        resposta = self._request_azure(
            "POST",
            f"/indexes/{self.config.azure_search_index}/docs/search",
            payload={
                "top": limite,
                "select": "id,content,fonte,metadata_json",
                "vectorQueries": [
                    {
                        "kind": "vector",
                        "vector": vetor,
                        "k": limite,
                        "fields": self.VECTOR_FIELD,
                    }
                ],
            },
        )
        documentos: list[Document] = []
        for item in resposta.get("value", []):
            metadata = {"fonte": item.get("fonte", "")}
            metadata_json = item.get("metadata_json") or ""
            if metadata_json:
                try:
                    metadata.update(json.loads(metadata_json))
                except Exception:
                    pass
            documentos.append(
                Document(
                    page_content=item.get("content", ""),
                    metadata=metadata,
                )
            )
        self.logger.info("Busca vetorial Azure retornou %d chunk(s).", len(documentos))
        return documentos

    def _criar_indice_azure(self) -> None:
        dimensao = len(self.embeddings().embed_query("teste"))
        payload = {
            "name": self.config.azure_search_index,
            "fields": [
                {"name": "id", "type": "Edm.String", "key": True, "searchable": False, "filterable": True, "sortable": True, "facetable": False, "retrievable": True},
                {"name": "content", "type": "Edm.String", "searchable": True, "filterable": False, "sortable": False, "facetable": False, "retrievable": True},
                {"name": "fonte", "type": "Edm.String", "searchable": True, "filterable": True, "sortable": True, "facetable": True, "retrievable": True},
                {"name": "metadata_json", "type": "Edm.String", "searchable": False, "filterable": False, "sortable": False, "facetable": False, "retrievable": True},
                {
                    "name": self.VECTOR_FIELD,
                    "type": "Collection(Edm.Single)",
                    "searchable": True,
                    "retrievable": False,
                    "dimensions": dimensao,
                    "vectorSearchProfile": "default-profile",
                },
            ],
            "vectorSearch": {
                "algorithms": [
                    {"name": "default-hnsw", "kind": "hnsw"}
                ],
                "profiles": [
                    {"name": "default-profile", "algorithm": "default-hnsw"}
                ],
            },
        }
        self._request_azure(
            "PUT",
            f"/indexes/{self.config.azure_search_index}",
            payload=payload,
            allow_not_found=False,
        )

    def _contar_azure(self) -> int:
        resposta = self._request_azure(
            "POST",
            f"/indexes/{self.config.azure_search_index}/docs/search",
            payload={"top": 0, "count": True, "search": "*"},
        )
        return int(resposta.get("@odata.count", 0))

    def _limpar_documentos_azure(self) -> None:
        consulta = self._request_azure(
            "POST",
            f"/indexes/{self.config.azure_search_index}/docs/search",
            payload={"top": 1000, "select": "id", "search": "*"},
        )
        ids = [item["id"] for item in consulta.get("value", []) if item.get("id")]
        if not ids:
            return
        lote = {"value": [{"@search.action": "delete", "id": identificador} for identificador in ids]}
        self._request_azure(
            "POST",
            f"/indexes/{self.config.azure_search_index}/docs/index",
            payload=lote,
        )

    def _request_azure(
        self,
        metodo: str,
        path: str,
        payload: dict | None = None,
        allow_not_found: bool = False,
    ) -> dict:
        if not self.config.azure_search_endpoint or not self.config.azure_search_api_key:
            raise ValueError("AZURE_SEARCH_ENDPOINT/AZURE_SEARCH_API_KEY não configurados.")

        url = f"{self.config.azure_search_endpoint}{path}?api-version={self.SEARCH_API_VERSION}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = request.Request(
            url,
            data=body,
            method=metodo,
            headers={
                "Content-Type": "application/json",
                "api-key": self.config.azure_search_api_key,
            },
        )
        try:
            with request.urlopen(req, timeout=120) as resposta:
                bruto = resposta.read().decode("utf-8")
        except error.HTTPError as exc:
            if allow_not_found and exc.code == 404:
                return {}
            corpo = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Erro Azure Search ({exc.code}): {corpo}") from exc
        return json.loads(bruto) if bruto else {}
