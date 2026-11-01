"""Regras de autenticação: verificação de senha, bloqueio por tentativas e política de senha."""

from __future__ import annotations

import re

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from painel.models import usuarios

HASH_METHOD = "pbkdf2:sha256:600000"
_DUMMY_HASH = generate_password_hash("senha-inexistente-para-igualar-tempo", method="pbkdf2:sha256:600000")


class CredenciaisInvalidas(Exception):
    """Mensagem única para usuário inexistente, inativo ou senha incorreta (evita enumeração)."""


class ContaBloqueada(Exception):
    pass


class SenhaFraca(ValueError):
    pass


def hash_senha(senha: str) -> str:
    return generate_password_hash(senha, method=HASH_METHOD)


def validar_politica_senha(senha: str) -> None:
    if len(senha) < 10 or not re.search(r"[A-Za-z]", senha) or not re.search(r"\d", senha):
        raise SenhaFraca("A senha deve ter ao menos 10 caracteres, com letras e números.")
    if len(senha) > 128:
        raise SenhaFraca("A senha deve ter no máximo 128 caracteres.")


def autenticar(identificador: str, senha: str) -> dict:
    identificador = (identificador or "").strip()[:150]
    user = usuarios.buscar_por_login(identificador) if identificador else None
    if user is None or not user["ativo"]:
        check_password_hash(_DUMMY_HASH, senha or "")  # custo constante
        raise CredenciaisInvalidas("Usuário ou senha inválidos.")
    if usuarios.bloqueado(user["id"]):
        raise ContaBloqueada("Muitas tentativas. Aguarde alguns minutos e tente novamente.")
    if not check_password_hash(user["senha_hash"], senha or ""):
        cfg = current_app.config
        usuarios.registrar_falha(user["id"], cfg["LOGIN_MAX_ATTEMPTS"], cfg["LOGIN_LOCK_MINUTES"])
        raise CredenciaisInvalidas("Usuário ou senha inválidos.")
    usuarios.registrar_sucesso(user["id"])
    return user


def usuario_publico(user: dict) -> dict:
    """Projeção sem senha_hash nem contadores internos, segura para templates e JSON."""
    return {k: user[k] for k in ("id", "username", "nome", "email", "role", "tema", "github_username")}

