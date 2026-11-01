"""Gera users_seed.json com senhas temporárias aleatórias (somente o hash é gravado).

As senhas em texto claro são impressas UMA vez no console; troque-as em Configurações após o primeiro login.
    python gerar_seed.py
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from painel.services.auth_service import hash_senha

USUARIOS = [
    ("superadmin", "Super Admin", "superadmin@painel.local", "super-admin", "dark"),
    ("admin", "Administrador", "admin@painel.local", "admin", "dark-purple"),
    ("usuario", "Usuário Teste", "usuario@painel.local", "usuario", "dark"),
]


def senha_temporaria() -> str:
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return "".join(secrets.choice(alfabeto) for _ in range(10)) + "#" + str(secrets.randbelow(90) + 10)


def main() -> None:
    saida, credenciais = [], []
    for username, nome, email, role, tema in USUARIOS:
        senha = senha_temporaria()
        saida.append({"username": username, "nome": nome, "email": email, "role": role, "tema": tema,
                      "senha_hash": hash_senha(senha)})
        credenciais.append((role, username, senha))
    Path(__file__).with_name("users_seed.json").write_text(
        json.dumps({"versao": 1, "observacao": "Somente hashes. Troque as senhas temporárias após o primeiro acesso.",
                    "usuarios": saida}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("users_seed.json gerado. Credenciais temporárias:")
    for role, username, senha in credenciais:
        print(f"  {role:<12} usuario={username:<11} senha={senha}")


if __name__ == "__main__":
    main()

