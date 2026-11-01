"""Cria o banco (schema.sql) e carrega os usuários iniciais de users_seed.json.

Uso (a partir de requisicoes/):
    python seed.py --init-db      # executa schema.sql e aplica o seed
    python seed.py                # apenas aplica/atualiza os usuários do seed
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from painel import create_app
from painel.config import DatabaseConfig
from painel.db import DatabaseUnavailable, connect
from painel.models import usuarios

BASE = Path(__file__).resolve().parent


def dividir_sql(texto: str) -> list[str]:
    """Separa instruções por ';' ignorando comentários `--` e ponto-e-vírgula dentro de aspas."""
    instrucoes, atual, aspas, i = [], [], None, 0
    while i < len(texto):
        c = texto[i]
        if aspas:
            atual.append(c)
            if c == "\\" and i + 1 < len(texto):
                atual.append(texto[i + 1]); i += 1
            elif c == aspas:
                aspas = None
        elif c in ("'", '"', "`"):
            aspas = c; atual.append(c)
        elif texto.startswith("--", i):
            while i < len(texto) and texto[i] != "\n":
                i += 1
            continue
        elif c == ";":
            sql = "".join(atual).strip()
            if sql:
                instrucoes.append(sql)
            atual = []
        else:
            atual.append(c)
        i += 1
    resto = "".join(atual).strip()
    if resto:
        instrucoes.append(resto)
    return instrucoes


def criar_schema(config: DatabaseConfig) -> int:
    conn = connect(config, with_database=False)
    try:
        with conn.cursor() as cur:
            statements = dividir_sql((BASE / "schema.sql").read_text(encoding="utf-8"))
            for sql in statements:
                cur.execute(sql)
        return len(statements)
    finally:
        conn.close()


def aplicar_seed(app) -> list[str]:
    dados = json.loads((BASE / "users_seed.json").read_text(encoding="utf-8"))
    aplicados = []
    with app.app_context():
        for u in dados["usuarios"]:
            usuarios.upsert_seed(u)
            aplicados.append(f"{u['username']} ({u['role']})")
    return aplicados


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--init-db", action="store_true", help="executa o schema.sql antes do seed")
    args = parser.parse_args()
    app = create_app()
    try:
        if args.init_db:
            print(f"schema.sql: {criar_schema(app.config['DB'])} instruções executadas.")
        print("Usuários aplicados:", ", ".join(aplicar_seed(app)))
    except DatabaseUnavailable as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

