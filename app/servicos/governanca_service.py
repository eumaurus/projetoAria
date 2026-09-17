"""Auditoria de interações e métricas de sustentação do copiloto."""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.servicos.base_service import BaseService
from app.servicos.config import Config


class GovernancaService(BaseService):
    """Persiste rastros mínimos de uso para governança e observabilidade.

    O serviço registra cada solicitação concluída com contexto de execução e
    indicadores de custo estimados. SQLite com WAL atende o uso local; em uma
    implantação concorrente, a mesma interface pode ser apontada para um banco
    gerenciado sem alterar as telas de governança.
    """

    NOME_ARQUIVO = "governanca.sqlite3"
    STOPWORDS = {
        "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos",
        "e", "em", "essa", "esse", "esta", "este", "eu", "foi", "me", "na", "nas",
        "no", "nos", "o", "os", "ou", "para", "por", "qual", "quais", "que", "um",
        "uma", "sobre", "tem", "total", "vendas", "venda", "mostrar", "mostre",
    }

    def __init__(self, config: Config, logger: logging.Logger) -> None:
        super().__init__(config, logger)
        self._arquivo = self.config.pasta_logs / self.NOME_ARQUIVO
        self._inicializar_banco()

    def registrar_interacao(
        self,
        email: str,
        pergunta: str,
        estado: dict[str, Any],
        latencia_ms: int,
    ) -> int | None:
        """Grava uma interação finalizada e retorna seu identificador de auditoria."""
        contexto = str(estado.get("contexto", ""))
        resposta = str(estado.get("resposta", ""))
        sql = str(estado.get("sql", ""))
        tokens_entrada = self._estimar_tokens(f"{pergunta}\n{contexto}")
        tokens_saida = self._estimar_tokens(f"{resposta}\n{sql}")
        dados = estado.get("dados")
        linhas = len(dados) if isinstance(dados, pd.DataFrame) else 0
        criado_em = datetime.now(timezone.utc).isoformat(timespec="seconds")

        try:
            with self._conectar() as conexao:
                cursor = conexao.execute(
                    """
                    INSERT INTO interacoes (
                        criado_em, email, pergunta, pergunta_hash, nivel, intencao,
                        agente, fonte_dados, modelo, modo_modelo, status, erro,
                        latencia_ms, tokens_entrada, tokens_saida, tokens_total,
                        tipo_tokens, contexto_disponivel, linhas_retornadas
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        criado_em,
                        email.strip().lower(),
                        pergunta.strip(),
                        hashlib.sha256(pergunta.strip().encode("utf-8")).hexdigest(),
                        str(estado.get("nivel", "")),
                        str(estado.get("intencao", "")),
                        str(estado.get("agente", "")),
                        self.config.fonte_dados,
                        self.config.gemini_model,
                        self.config.gemini_modo,
                        "ERRO" if estado.get("erro") else "SUCESSO",
                        str(estado.get("erro", ""))[:1000] or None,
                        max(latencia_ms, 0),
                        tokens_entrada,
                        tokens_saida,
                        tokens_entrada + tokens_saida,
                        "estimado",
                        int(bool(contexto.strip())),
                        linhas,
                    ),
                )
                auditoria_id = int(cursor.lastrowid)
            self.logger.info("Auditoria registrada: id=%s, agente=%s", auditoria_id, estado.get("agente"))
            return auditoria_id
        except Exception as exc:
            # A telemetria não pode interromper a resposta do copiloto.
            self.logger.exception("Falha ao registrar auditoria: %s", exc)
            return None

    def registrar_feedback(self, auditoria_id: int, feedback: int) -> None:
        """Salva avaliação explícita do usuário: 1 positivo, -1 negativo."""
        if feedback not in (-1, 1):
            raise ValueError("Feedback deve ser 1 (positivo) ou -1 (negativo).")
        with self._conectar() as conexao:
            conexao.execute(
                "UPDATE interacoes SET feedback = ? WHERE id = ?",
                (feedback, auditoria_id),
            )

    def listar_interacoes(self, dias: int = 30, email: str | None = None) -> pd.DataFrame:
        """Lista rastros recentes, com filtro opcional de usuário."""
        inicio = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat(timespec="seconds")
        sql = "SELECT * FROM interacoes WHERE criado_em >= ?"
        parametros: list[Any] = [inicio]
        if email:
            sql += " AND email = ?"
            parametros.append(email.strip().lower())
        sql += " ORDER BY criado_em DESC"
        with self._conectar() as conexao:
            return pd.read_sql_query(sql, conexao, params=parametros)

    def resumo(self, dias: int = 30) -> dict[str, float | int | None]:
        """Calcula indicadores operacionais e de qualidade para o período."""
        dados = self.listar_interacoes(dias)
        if dados.empty:
            return {
                "consultas": 0, "usuarios_ativos": 0, "sucesso_pct": None,
                "erros": 0, "latencia_p95": None, "tokens_total": 0,
                "tokens_por_consulta": None, "feedback_positivo_pct": None,
                "feedback_cobertura_pct": None, "cobertura_rag_pct": None,
            }

        sucesso = dados["status"].eq("SUCESSO")
        feedback = dados["feedback"].dropna()
        consultas_rag = dados[dados["agente"].eq("RagAgent")]
        return {
            "consultas": int(len(dados)),
            "usuarios_ativos": int(dados["email"].nunique()),
            "sucesso_pct": float(sucesso.mean() * 100),
            "erros": int((~sucesso).sum()),
            "latencia_p95": float(dados["latencia_ms"].quantile(0.95)),
            "tokens_total": int(dados["tokens_total"].sum()),
            "tokens_por_consulta": float(dados["tokens_total"].mean()),
            "feedback_positivo_pct": float((feedback == 1).mean() * 100) if not feedback.empty else None,
            "feedback_cobertura_pct": float(len(feedback) / len(dados) * 100),
            "cobertura_rag_pct": (
                float(consultas_rag["contexto_disponivel"].mean() * 100)
                if not consultas_rag.empty else None
            ),
        }

    def resumo_por_usuario(self, dias: int = 30) -> pd.DataFrame:
        """Agrega volume, tokens e confiabilidade por usuário autorizado."""
        dados = self.listar_interacoes(dias)
        if dados.empty:
            return pd.DataFrame(columns=["Usuário", "Perguntas", "Tokens estimados", "Latência média (ms)", "Sucesso (%)"])
        dados["_sucesso"] = dados["status"].eq("SUCESSO").astype(float)
        tabela = (
            dados.groupby("email", as_index=False)
            .agg(
                Perguntas=("id", "count"),
                **{
                    "Tokens estimados": ("tokens_total", "sum"),
                    "Latência média (ms)": ("latencia_ms", "mean"),
                    "Sucesso (%)": ("_sucesso", "mean"),
                },
            )
            .rename(columns={"email": "Usuário"})
        )
        tabela["Sucesso (%)"] = (tabela["Sucesso (%)"] * 100).round(1)
        tabela["Latência média (ms)"] = tabela["Latência média (ms)"].round(0).astype(int)
        return tabela.sort_values(["Perguntas", "Tokens estimados"], ascending=False)

    def frequencia_palavras(self, dias: int = 30, limite: int = 32) -> list[tuple[str, int]]:
        """Produz termos de consulta para uma nuvem de palavras explicável."""
        dados = self.listar_interacoes(dias)
        contagem: dict[str, int] = {}
        for pergunta in dados.get("pergunta", pd.Series(dtype=str)).dropna():
            for termo in re.findall(r"[a-zà-ÿ0-9_]+", str(pergunta).lower()):
                if len(termo) < 3 or termo in self.STOPWORDS:
                    continue
                contagem[termo] = contagem.get(termo, 0) + 1
        return sorted(contagem.items(), key=lambda item: (-item[1], item[0]))[:limite]

    def _inicializar_banco(self) -> None:
        with self._conectar() as conexao:
            conexao.execute("PRAGMA journal_mode = WAL")
            conexao.execute(
                """
                CREATE TABLE IF NOT EXISTS interacoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    criado_em TEXT NOT NULL,
                    email TEXT NOT NULL,
                    pergunta TEXT NOT NULL,
                    pergunta_hash TEXT NOT NULL,
                    nivel TEXT,
                    intencao TEXT,
                    agente TEXT,
                    fonte_dados TEXT,
                    modelo TEXT,
                    modo_modelo TEXT,
                    status TEXT NOT NULL,
                    erro TEXT,
                    latencia_ms INTEGER NOT NULL,
                    tokens_entrada INTEGER NOT NULL,
                    tokens_saida INTEGER NOT NULL,
                    tokens_total INTEGER NOT NULL,
                    tipo_tokens TEXT NOT NULL,
                    contexto_disponivel INTEGER NOT NULL,
                    linhas_retornadas INTEGER NOT NULL,
                    feedback INTEGER
                )
                """
            )
            conexao.execute("CREATE INDEX IF NOT EXISTS idx_interacoes_data ON interacoes(criado_em)")
            conexao.execute("CREATE INDEX IF NOT EXISTS idx_interacoes_email ON interacoes(email)")

    def _conectar(self) -> sqlite3.Connection:
        conexao = sqlite3.connect(self._arquivo, timeout=10)
        conexao.row_factory = sqlite3.Row
        return conexao

    @staticmethod
    def _estimar_tokens(texto: str) -> int:
        """Aproxima tokens para o modo atual, que não expõe uso do provedor."""
        limpo = texto.strip()
        return max(1, (len(limpo) + 3) // 4) if limpo else 0
