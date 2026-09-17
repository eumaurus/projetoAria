"""Catálogo técnico e mapeamento semântico de colunas."""

from __future__ import annotations

import logging
import re
import unicodedata

import pandas as pd

from app.servicos.azure_sql_service import AzureSqlService
from app.servicos.base_service import BaseService
from app.servicos.config import Config
from app.servicos.data_service import DataService


class MetadataService(BaseService):
    """Gera catálogo semântico automaticamente a partir das bases ativas."""

    TABELAS_SUPORTE = {"rls", "dicionario_dados"}

    def __init__(
        self,
        config: Config,
        logger: logging.Logger,
        data_service: DataService,
        azure_sql_service: AzureSqlService | None = None,
    ) -> None:
        super().__init__(config, logger)
        self._data_service = data_service
        self._azure_sql_service = azure_sql_service
        self._mapeamento: dict[str, str] = {}
        self._descricoes: dict[str, str] = {}
        self._sinonimos_por_coluna: dict[str, set[str]] = {}
        self._carregar_catalogo()

    def _carregar_catalogo(self) -> None:
        tabelas = self._tabelas_contexto()
        if not tabelas:
            self.logger.warning("Nenhuma tabela de contexto disponível para metadados.")
            return

        for tabela in tabelas:
            try:
                df = self._data_service.obter(tabela)
            except KeyError:
                continue

            for coluna in df.columns.astype(str):
                referencia = f"{tabela}.[{coluna}]"
                descricao = self._descrever_coluna(tabela, df, coluna)
                sinonimos = self._gerar_sinonimos(tabela, coluna)

                self._descricoes[referencia] = descricao
                self._sinonimos_por_coluna.setdefault(referencia, set()).update(sinonimos)

                for termo in sinonimos | {coluna, referencia, tabela}:
                    termo_norm = self._normalizar(termo)
                    if termo_norm:
                        self._mapeamento[termo_norm] = referencia

        self.logger.info("Metadados automáticos carregados: %d termo(s).", len(self._mapeamento))

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

    def _descrever_coluna(self, tabela: str, df: pd.DataFrame, coluna: str) -> str:
        serie = df[coluna]
        tipo = str(serie.dtype)
        preenchidos = int(serie.notna().sum())
        descricao = [
            f"Tabela {tabela}",
            f"coluna {coluna}",
            f"tipo {tipo}",
            f"{preenchidos} valor(es) preenchido(s) em {len(df)} linha(s)",
        ]

        if pd.api.types.is_datetime64_any_dtype(serie):
            serie_dt = pd.to_datetime(serie, errors="coerce").dropna()
            if not serie_dt.empty:
                descricao.append(
                    f"intervalo de {serie_dt.min().date()} até {serie_dt.max().date()}"
                )
        elif pd.api.types.is_bool_dtype(serie):
            distribuicao = serie.astype("boolean").value_counts(dropna=False).to_dict()
            descricao.append(f"distribuição observada {distribuicao}")
        elif pd.api.types.is_numeric_dtype(serie):
            serie_num = pd.to_numeric(serie, errors="coerce").dropna()
            if not serie_num.empty:
                descricao.append(
                    "mínimo {:.2f}, média {:.2f}, máximo {:.2f}".format(
                        float(serie_num.min()),
                        float(serie_num.mean()),
                        float(serie_num.max()),
                    )
                )
        else:
            exemplos = [
                str(valor).strip()
                for valor in serie.dropna().astype(str).head(5).tolist()
                if str(valor).strip()
            ]
            if exemplos:
                descricao.append(f"exemplos: {', '.join(exemplos)}")

        return "; ".join(descricao)

    def _gerar_sinonimos(self, tabela: str, coluna: str) -> set[str]:
        partes = {
            coluna,
            coluna.replace("_", " "),
            tabela,
            f"{tabela} {coluna}",
        }

        tokens = [
            token for token in re.split(r"[_\s?/()-]+", coluna)
            if token
        ]
        partes.update(tokens)

        aliases: dict[str, tuple[str, ...]] = {
            "Número": ("incidente", "numero do incidente", "chamado", "ticket"),
            "Prioridade": ("criticidade", "severidade", "prioridade do incidente"),
            "Grupo designado": ("grupo", "time", "equipe", "grupo responsável"),
            "Item de configuração": ("ic", "item", "configuração"),
            "Aberto": ("data de abertura", "abertura"),
            "Resolvido": ("data de resolução", "resolucao"),
            "Encerrado": ("data de encerramento", "fechamento"),
            "Duração": ("duracao", "tempo de atendimento", "tempo de resolução", "tempo"),
            "Código de fechamento": ("codigo de fechamento", "fechamento"),
            "Descrição resumida": ("descricao", "descrição", "resumo"),
            "Solução": ("acao aplicada", "resolucao aplicada", "tratativa"),
            "Status": ("estado", "situação"),
            "Entrou para KPI?": ("entrou no kpi", "considerado no kpi"),
            "KPI Violado?": ("violacao de kpi", "violado", "descumprimento de kpi"),
            "Duração_outlier": ("outlier de duracao", "anomalia de duração"),
            "Data": ("data de referencia", "data"),
            "Ano": ("ano"),
            "Mes": ("mês", "mes"),
            "Dia_semana": ("dia da semana"),
            "Eh_fim_de_semana": ("fim de semana", "eh final de semana"),
            "Prioridade_num": ("prioridade numerica", "prioridade número"),
            "Novo_patamar_volume": ("novo patamar", "patamar de volume", "volume elevado"),
            "data": ("data"),
            "volume_total_real": ("volume real", "volume total real"),
            "volume_p2_real": ("volume p2 real", "p2 real"),
            "volume_p3_real": ("volume p3 real", "p3 real"),
            "taxa_atingimento_kpi_real": ("taxa real de kpi", "atingimento real", "kpi real"),
            "volume_total_previsto_d1": ("previsao d1", "volume previsto d1"),
            "volume_p2_previsto_d1": ("p2 previsto d1", "previsao p2 d1"),
            "volume_p3_previsto_d1": ("p3 previsto d1", "previsao p3 d1"),
            "taxa_atingimento_kpi_previsto_d1": ("kpi previsto d1", "atingimento previsto d1"),
            "volume_total_previsto_d7": ("previsao d7", "volume previsto d7"),
            "volume_p2_previsto_d7": ("p2 previsto d7", "previsao p2 d7"),
            "volume_p3_previsto_d7": ("p3 previsto d7", "previsao p3 d7"),
            "taxa_atingimento_kpi_previsto_d7": ("kpi previsto d7", "atingimento previsto d7"),
            "dia_semana": ("dia da semana",),
            "eh_fim_de_semana": ("fim de semana",),
        }
        partes.update(aliases.get(coluna, ()))

        return {parte for parte in partes if parte and parte.lower() != "nan"}

    @staticmethod
    def _normalizar(texto: str) -> str:
        texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
        return re.sub(r"\s+", " ", texto.lower().strip())

    def localizar_coluna(self, pergunta: str) -> list[str]:
        """Identifica colunas técnicas mencionadas ou inferidas na pergunta."""
        pergunta_norm = self._normalizar(pergunta)
        encontradas: list[str] = []

        for sinonimo, coluna in sorted(self._mapeamento.items(), key=lambda x: len(x[0]), reverse=True):
            if sinonimo in pergunta_norm and coluna not in encontradas:
                encontradas.append(coluna)

        return encontradas

    def obter_catalogo_texto(self) -> str:
        """Retorna catálogo legível para enriquecimento de prompts."""
        if not self._descricoes:
            return "Catálogo de metadados indisponível."

        linhas = ["Referência | Sinônimos | Descrição"]
        for referencia in sorted(self._descricoes):
            sinonimos = ", ".join(sorted(self._sinonimos_por_coluna.get(referencia, set())))
            linhas.append(f"{referencia} | {sinonimos} | {self._descricoes[referencia]}")
        return "\n".join(linhas)

    def obter_tabelas_disponiveis(self, nomes: list[str]) -> str:
        """Resume estrutura das tabelas disponíveis para geração de SQL."""
        if self.config.fonte_dados == "azure" and self._azure_sql_service:
            return self._azure_sql_service.descrever_tabelas()

        blocos: list[str] = []
        for nome in nomes:
            try:
                df = self._data_service.obter(nome.split(".")[-1].strip("[]"))
                colunas = ", ".join(f"[{coluna}]" for coluna in df.columns.astype(str).tolist())
                blocos.append(f"Tabela `{nome.split('.')[-1].strip('[]')}`: colunas [{colunas}]")
            except KeyError:
                continue
        return "\n".join(blocos) if blocos else "Nenhuma tabela disponível."
