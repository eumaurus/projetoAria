"""Ponto de entrada CLI do copiloto de incidentes e KPI."""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from app.container import construir_container


def _serializar_estado(estado: dict) -> dict:
    """Converte DataFrames para formato serializável."""
    saida = dict(estado)
    dados = saida.get("dados")
    if isinstance(dados, pd.DataFrame):
        saida["dados"] = dados.to_dict(orient="records")
    return saida


def main() -> int:
    parser = argparse.ArgumentParser(description="Projeto LUX — Copiloto de incidentes e KPI")
    parser.add_argument("--pergunta", "-p", required=True, help="Pergunta do usuário")
    parser.add_argument("--email", "-e", required=True, help="E-mail autorizado (RLS)")
    parser.add_argument("--json", action="store_true", help="Saída em JSON")
    args = parser.parse_args()

    container = construir_container()
    estado = container.orquestrador.executar(args.pergunta, args.email)
    estado_serializado = _serializar_estado(estado)

    if args.json:
        print(json.dumps(estado_serializado, ensure_ascii=False, indent=2))
    else:
        print("\n=== LUX — Resposta ===\n")
        print(estado.get("resposta", ""))
        if estado.get("sql"):
            print("\n--- SQL gerado ---")
            print(estado["sql"])

    return 1 if estado.get("erro") else 0


if __name__ == "__main__":
    sys.exit(main())
