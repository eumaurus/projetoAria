"""Definição do estado compartilhado da State Machine."""

from enum import StrEnum
from typing import NotRequired, TypedDict

import pandas as pd


class Intencao(StrEnum):
    """Intenções reconhecidas pelo roteador."""

    CONSULTA = "CONSULTA"
    RAG = "RAG"
    ANALYTICS = "ANALYTICS"


class NivelAcesso(StrEnum):
    """Níveis de acesso definidos na política RLS."""

    B = "B"
    A = "A"
    GOD = "GOD"


class Estado(TypedDict, total=False):
    """Fonte de verdade única do fluxo de execução."""

    pergunta: str
    email: str
    nivel: str
    intencao: str
    agente: str
    sql: str
    dados: pd.DataFrame
    contexto: str
    resposta: str
    erro: NotRequired[str]
