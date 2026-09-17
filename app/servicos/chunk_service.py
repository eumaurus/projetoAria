"""Chunking de documentos com LangChain Text Splitters."""

from __future__ import annotations

import logging

import pandas as pd
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.servicos.base_service import BaseService
from app.servicos.config import Config
from app.servicos.data_service import DataService


class ChunkService(BaseService):
    """Carrega fontes de conhecimento e divide em chunks."""

    TABELAS_SUPORTE = {"rls", "dicionario_dados"}
    EXTENSOES = (".txt", ".md")

    def __init__(
        self,
        config: Config,
        logger: logging.Logger,
        data_service: DataService,
    ) -> None:
        super().__init__(config, logger)
        self._data_service = data_service
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.chunk_tamanho,
            chunk_overlap=self.config.chunk_sobreposicao,
            separators=["\n\n", "\n", ". ", "; ", " ", ""],
        )

    def montar_documentos(self) -> list[Document]:
        """Reúne documentos brutos a partir das bases e arquivos de apoio."""
        documentos: list[Document] = []
        documentos.extend(self._documentos_tabelas())
        documentos.extend(self._documentos_arquivos())
        self.logger.info("Documentos brutos carregados: %d", len(documentos))
        return documentos

    def dividir(self, documentos: list[Document] | None = None) -> list[Document]:
        """Aplica chunking e devolve trechos prontos para embedding."""
        origem = documentos if documentos is not None else self.montar_documentos()
        if not origem:
            return []
        chunks = self._splitter.split_documents(origem)
        self.logger.info("Chunks gerados: %d (tamanho=%d, overlap=%d)", len(chunks), self.config.chunk_tamanho, self.config.chunk_sobreposicao)
        return chunks

    def _documentos_tabelas(self) -> list[Document]:
        documentos: list[Document] = []
        for nome in self._tabelas_contexto():
            try:
                df = self._data_service.obter(nome)
            except KeyError:
                continue

            documentos.append(
                Document(
                    page_content=self._resumo_tabela(nome, df),
                    metadata={"fonte": nome, "tipo": "resumo_tabela"},
                )
            )

            for coluna in df.columns.astype(str):
                documentos.append(
                    Document(
                        page_content=self._resumo_coluna(nome, df, coluna),
                        metadata={"fonte": nome, "tipo": "coluna", "coluna": coluna},
                    )
                )
        return documentos

    def _tabelas_contexto(self) -> list[str]:
        configuradas = [
            tabela.split(".")[-1].strip("[]")
            for tabela in self.config.azure_sql_tabelas
            if tabela.split(".")[-1].strip("[]") in self._data_service.listar()
        ]
        if configuradas:
            return configuradas

        return [
            nome for nome in self._data_service.listar()
            if nome not in self.TABELAS_SUPORTE
        ]

    def _resumo_tabela(self, nome: str, df: pd.DataFrame) -> str:
        linhas = [
            f"Tabela: {nome}",
            f"Linhas: {len(df)}",
            f"Colunas: {', '.join(df.columns.astype(str).tolist())}",
        ]

        colunas_data = [
            coluna for coluna in df.columns
            if pd.api.types.is_datetime64_any_dtype(df[coluna])
        ]
        for coluna in colunas_data[:2]:
            serie = pd.to_datetime(df[coluna], errors="coerce").dropna()
            if not serie.empty:
                linhas.append(
                    f"Faixa da coluna {coluna}: {serie.min().date()} até {serie.max().date()}"
                )

        return "\n".join(linhas)

    def _resumo_coluna(self, nome: str, df: pd.DataFrame, coluna: str) -> str:
        serie = df[coluna]
        linhas = [
            f"Tabela: {nome}",
            f"Coluna: {coluna}",
            f"Tipo: {serie.dtype}",
            f"Nulos: {int(serie.isna().sum())}",
        ]

        if pd.api.types.is_datetime64_any_dtype(serie):
            serie_dt = pd.to_datetime(serie, errors="coerce").dropna()
            if not serie_dt.empty:
                linhas.append(f"Intervalo: {serie_dt.min().date()} até {serie_dt.max().date()}")
        elif pd.api.types.is_bool_dtype(serie):
            linhas.append(f"Distribuição: {serie.astype('boolean').value_counts(dropna=False).to_dict()}")
        elif pd.api.types.is_numeric_dtype(serie):
            serie_num = pd.to_numeric(serie, errors="coerce").dropna()
            if not serie_num.empty:
                linhas.append(
                    "Resumo numérico: min={:.2f}, média={:.2f}, mediana={:.2f}, max={:.2f}".format(
                        float(serie_num.min()),
                        float(serie_num.mean()),
                        float(serie_num.median()),
                        float(serie_num.max()),
                    )
                )
        else:
            amostra = serie.dropna().astype(str).value_counts().head(5)
            if not amostra.empty:
                linhas.append(
                    "Valores frequentes: "
                    + ", ".join(f"{indice} ({valor})" for indice, valor in amostra.items())
                )

        return "\n".join(linhas)

    def _documentos_arquivos(self) -> list[Document]:
        pasta = self.config.pasta_conhecimento
        if not pasta.exists():
            return []

        documentos: list[Document] = []
        for arquivo in pasta.rglob("*"):
            if arquivo.suffix.lower() not in self.EXTENSOES:
                continue
            try:
                texto = arquivo.read_text(encoding="utf-8")
            except Exception as exc:
                self.logger.error("Falha ao ler %s: %s", arquivo, exc)
                continue
            if not texto.strip():
                continue
            documentos.append(
                Document(
                    page_content=texto,
                    metadata={"fonte": str(arquivo.relative_to(self.config.raiz_projeto)), "arquivo": arquivo.name},
                )
            )
        return documentos

