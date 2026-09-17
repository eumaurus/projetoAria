"""Cálculo de métricas analíticas sobre os datasets comerciais."""

from __future__ import annotations

import logging
import re
import unicodedata

import pandas as pd

from app.servicos.azure_sql_service import AzureSqlService
from app.servicos.base_service import BaseService
from app.servicos.config import Config
from app.servicos.data_service import DataService


class AnalyticsService(BaseService):
    """Executa agregações e estatísticas descritivas sobre incidentes e previsões."""

    NOME_BASE_INCIDENTES = "base_tratada"
    NOME_BASE_PREVISAO = "previsao_kpi"

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

    def calcular_metricas(self, pergunta: str) -> str:
        pergunta_norm = self._normalizar(pergunta)
        if any(
            termo in pergunta_norm
            for termo in ("previs", "previsto", "d1", "d7", "forecast", "volume", "atingimento")
        ):
            return self._metricas_previsao()
        return self._metricas_incidentes(pergunta_norm)

    def _metricas_incidentes(self, pergunta_norm: str) -> str:
        try:
            df = self._carregar_base(self.NOME_BASE_INCIDENTES)
        except KeyError:
            return "Dataset base_tratada não disponível para análise."
        except Exception as exc:
            return f"Não foi possível ler a base de incidentes: {exc}"

        if df.empty:
            return "Dataset base_tratada está vazio."

        blocos = [
            f"Total de incidentes: {len(df)}",
            f"Duração média: {pd.to_numeric(df['Duração'], errors='coerce').mean():.2f}",
            f"Duração mediana: {pd.to_numeric(df['Duração'], errors='coerce').median():.2f}",
        ]

        if "Entrou para KPI?" in df.columns:
            taxa_kpi = self._percentual_sim(df["Entrou para KPI?"])
            blocos.append(f"Percentual que entrou no KPI: {taxa_kpi:.2f}%")

        if "KPI Violado?" in df.columns:
            taxa_violacao = self._percentual_sim(df["KPI Violado?"])
            blocos.append(f"Percentual com KPI violado: {taxa_violacao:.2f}%")

        if any(termo in pergunta_norm for termo in ("prioridade", "criticidade", "severidade")):
            blocos.append("Incidentes por prioridade:")
            blocos.append(df["Prioridade"].value_counts().head(10).to_string())

        if any(termo in pergunta_norm for termo in ("status", "situação", "situacao")):
            blocos.append("Incidentes por status:")
            blocos.append(df["Status"].value_counts().head(10).to_string())

        if any(termo in pergunta_norm for termo in ("grupo", "time", "equipe")):
            blocos.append("Incidentes por grupo designado:")
            blocos.append(df["Grupo designado"].value_counts().head(10).to_string())

        if any(termo in pergunta_norm for termo in ("dia", "semana", "fim de semana", "tendencia", "tendência", "mês", "mes")):
            blocos.append("Volume por dia da semana:")
            blocos.append(df["Dia_semana"].value_counts().to_string())

            serie_data = pd.to_datetime(df["Data"], errors="coerce")
            if serie_data.notna().any():
                por_mes = (
                    df.assign(_periodo=serie_data.dt.to_period("M"))
                    .groupby("_periodo")["Número"]
                    .count()
                    .sort_index()
                )
                blocos.append("Evolução mensal de incidentes:")
                blocos.append(por_mes.tail(12).to_string())

        if len(blocos) <= 5:
            blocos.append("Top grupos por volume:")
            blocos.append(df["Grupo designado"].value_counts().head(5).to_string())

        self.logger.info("Analytics de incidentes gerou %d bloco(s).", len(blocos))
        return "\n".join(blocos)

    def _metricas_previsao(self) -> str:
        try:
            df = self._carregar_base(self.NOME_BASE_PREVISAO)
        except KeyError:
            return "Dataset previsao_kpi não disponível para análise."
        except Exception as exc:
            return f"Não foi possível ler a base de previsão: {exc}"

        if df.empty:
            return "Dataset previsao_kpi está vazio."

        datas = pd.to_datetime(df["data"], errors="coerce").dropna()
        blocos = [
            f"Total de dias observados: {len(df)}",
        ]
        if not datas.empty:
            blocos.append(f"Período: {datas.min().date()} até {datas.max().date()}")

        for coluna in (
            "volume_total_real",
            "volume_p2_real",
            "volume_p3_real",
            "taxa_atingimento_kpi_real",
        ):
            serie = pd.to_numeric(df[coluna], errors="coerce").dropna()
            if not serie.empty:
                blocos.append(
                    f"{coluna}: média {serie.mean():.2f}, mediana {serie.median():.2f}, máximo {serie.max():.2f}"
                )

        for horizonte in ("d1", "d7"):
            col_prev = f"volume_total_previsto_{horizonte}"
            if col_prev in df.columns:
                comparacao = df[["volume_total_real", col_prev]].dropna()
                if not comparacao.empty:
                    erro_abs = (comparacao["volume_total_real"] - comparacao[col_prev]).abs()
                    blocos.append(
                        f"Erro absoluto médio do volume total previsto {horizonte.upper()}: {erro_abs.mean():.2f}"
                    )

            col_kpi = f"taxa_atingimento_kpi_previsto_{horizonte}"
            if col_kpi in df.columns:
                comparacao_kpi = df[["taxa_atingimento_kpi_real", col_kpi]].dropna()
                if not comparacao_kpi.empty:
                    erro_kpi = (comparacao_kpi["taxa_atingimento_kpi_real"] - comparacao_kpi[col_kpi]).abs()
                    blocos.append(
                        f"Erro absoluto médio da taxa de KPI prevista {horizonte.upper()}: {erro_kpi.mean():.4f}"
                    )

        blocos.append("Volume real por dia da semana:")
        blocos.append(
            df.groupby("dia_semana")["volume_total_real"]
            .mean()
            .sort_values(ascending=False)
            .to_string()
        )
        self.logger.info("Analytics de previsão gerou %d bloco(s).", len(blocos))
        return "\n".join(blocos)

    def _carregar_base(self, nome_tabela: str) -> pd.DataFrame:
        if self.config.fonte_dados == "azure" and self._azure_sql_service:
            tabela = self._qualificar_tabela(nome_tabela)
            return self._azure_sql_service.executar(f"SELECT TOP 10000 * FROM {tabela}")
        return self._data_service.obter(nome_tabela)

    def _qualificar_tabela(self, nome_tabela: str) -> str:
        for tabela in self.config.azure_sql_tabelas:
            tabela_limpa = tabela.split(".")[-1].strip("[]")
            if tabela_limpa == nome_tabela:
                return tabela if "." in tabela else f"{self.config.azure_sql_schema}.{tabela}"
        return f"{self.config.azure_sql_schema}.{nome_tabela}"

    @staticmethod
    def _percentual_sim(serie: pd.Series) -> float:
        serie_norm = serie.astype(str).str.strip().str.upper()
        positivos = serie_norm.isin({"SIM", "S", "TRUE", "1"})
        base = serie_norm[serie_norm != "NAN"]
        if base.empty:
            return 0.0
        return float(positivos.loc[base.index].mean() * 100)

    @staticmethod
    def _normalizar(texto: str) -> str:
        texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
        return re.sub(r"\s+", " ", texto.lower().strip())

    @staticmethod
    def _resolver_coluna(df: pd.DataFrame, candidatos: list[str]) -> str | None:
        mapa = {str(c).strip().lower(): c for c in df.columns}
        for candidato in candidatos:
            if candidato in mapa:
                return mapa[candidato]
        return None
