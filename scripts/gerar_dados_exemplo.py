"""Gera arquivos Excel de exemplo para desenvolvimento local."""

from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
PASTA_DADOS = RAIZ / "dados"


def gerar() -> None:
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)

    base_final = pd.DataFrame(
        {
            "Cliente": ["Alpha Ltda", "Beta SA", "Gamma Corp", "Delta Inc"],
            "Regiao": ["Sul", "Sudeste", "Nordeste", "Sul"],
            "TCV_Full": [120000.0, 85000.5, 43000.0, 99000.0],
            "Data_Fechamento": pd.to_datetime(
                ["2025-01-15", "2025-02-20", "2025-03-10", "2025-04-05"]
            ),
        }
    )

    rls = pd.DataFrame(
        {
            "email": ["admin@lux.com", "analista@lux.com", "usuario@lux.com"],
            "nivel": ["GOD", "A", "B"],
        }
    )

    dicionario = pd.DataFrame(
        {
            "coluna_tecnica": ["TCV_Full", "Regiao", "Cliente", "Data_Fechamento"],
            "sinonimo": ["venda, faturamento, receita", "região, area", "cliente, conta", "data, fechamento"],
            "descricao": [
                "Valor total do contrato",
                "Região comercial",
                "Nome do cliente",
                "Data de fechamento da oportunidade",
            ],
        }
    )

    base_final.to_excel(PASTA_DADOS / "base_final.xlsx", index=False)
    rls.to_excel(PASTA_DADOS / "rls.xlsx", index=False)
    dicionario.to_excel(PASTA_DADOS / "dicionario_dados.xlsx", index=False)

    print("Arquivos gerados em:", PASTA_DADOS)


if __name__ == "__main__":
    gerar()
