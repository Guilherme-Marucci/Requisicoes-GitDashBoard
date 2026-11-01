"""Sessão, RBAC por permissão e proteção CSRF."""

from __future__ import annotations

import hmac
import secrets
from functools import wraps
from urllib.parse import urlsplit

from flask import abort, g, jsonify, redirect, request, session, url_for

ROLE_USUARIO, ROLE_ADMIN, ROLE_SUPER = "usuario", "admin", "super-admin"

# Matriz de permissões: cada rota exige uma permissão, nunca um nome de perfil fixo.
PERMISSOES: dict[str, frozenset[str]] = {
    ROLE_USUARIO: frozenset({
        "requisicoes.criar", "requisicoes.ver_proprias", "requisicoes.editar_proprias",
        "github.sincronizar", "github.ver_proprios", "preferencias.editar",
    }),
    ROLE_ADMIN: frozenset({
        "requisicoes.criar", "requisicoes.ver_proprias", "requisicoes.editar_proprias",
        "requisicoes.ver_todas", "requisicoes.editar_todas", "requisicoes.alterar_status",
        "github.sincronizar", "github.ver_proprios", "github.ver_todos", "preferencias.editar",
    }),
    ROLE_SUPER: frozenset({
        "requisicoes.criar", "requisicoes.ver_proprias", "requisicoes.editar_proprias",
        "requisicoes.ver_todas", "requisicoes.editar_todas", "requisicoes.alterar_status", "requisicoes.excluir",
        "github.sincronizar", "github.ver_proprios", "github.ver_todos", "preferencias.editar",
        "usuarios.gerenciar",
    }),
}


def pode(user: dict | None, permissao: str) -> bool:
    return bool(user and permissao in PERMISSOES.get(user["role"], frozenset()))


def wants_json() -> bool:
    return request.path.startswith("/api/")


def _deny(status: int, code: str, message: str):
    if wants_json():
        response = jsonify(erro={"codigo": code, "mensagem": message})
        response.status_code = status
        return response
    if status == 401:
        return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
    abort(status)


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.get("user") is None:
            return _deny(401, "nao_autenticado", "Sessão ausente ou expirada.")
        return view(*args, **kwargs)
    return wrapper


def permission_required(permissao: str):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(*args, **kwargs):
            if not pode(g.user, permissao):
                return _deny(403, "acesso_negado", "Seu perfil não possui permissão para esta ação.")
            return view(*args, **kwargs)
        return wrapper
    return decorator


# --- Sessão ----------------------------------------------------------------
def iniciar_sessao(user: dict) -> None:
    csrf = secrets.token_urlsafe(32)
    session.clear()  # evita fixação de sessão
    session.permanent = False
    session["uid"] = user["id"]
    session["csrf"] = csrf


def encerrar_sessao() -> None:
    session.clear()


# --- CSRF ------------------------------------------------------------------
def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def csrf_valido() -> bool:
    sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token") or ""
    expected = session.get("csrf", "")
    return bool(expected) and hmac.compare_digest(str(sent), expected)


def destino_seguro(target: str | None, default: str = "/") -> str:
    """Aceita apenas caminhos relativos internos (bloqueia open redirect)."""
    if not target:
        return default
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return default
    return target

