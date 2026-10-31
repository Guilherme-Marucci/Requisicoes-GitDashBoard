"""Projetos GitHub: página, sincronização e logs."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, render_template, request

from painel.models import github as model
from painel.security import permission_required, pode
from painel.services import github_service as svc

bp = Blueprint("github", __name__)


@bp.get("/projetos")
@permission_required("github.ver_proprios")
def projetos():
    return render_template("projetos.html", pode_ver_todos=pode(g.user, "github.ver_todos"))


@bp.post("/api/github/sincronizar")
@permission_required("github.sincronizar")
def sincronizar():
    body = request.get_json(silent=True) or {}
    entrada = str(body.get("entrada", "")) if isinstance(body, dict) else ""
    try:
        resultado = svc.sincronizar(g.user, entrada)
    except svc.GitHubErro as exc:
        response = jsonify(erro={"codigo": exc.resultado if exc.status != 400 else "entrada_invalida",
                                 "mensagem": exc.mensagem, "rate_limit_restante": exc.rate_restante})
        response.status_code = exc.status
        return response
    resultado["projetos"] = model.listar_projetos(g.user["id"], resultado["username"])
    return jsonify(resultado)


@bp.get("/api/github/projetos")
@permission_required("github.ver_proprios")
def listar_projetos():
    """Último estado persistido (dados + resumo) do username consultado; não chama a API do GitHub."""
    username = (request.args.get("username") or g.user.get("github_username") or "").strip()
    if not username:
        return jsonify(username=None, projetos=[], resumo=None)
    try:
        username = svc.extrair_username(username)
    except svc.GitHubErro as exc:
        return jsonify(erro={"codigo": "entrada_invalida", "mensagem": exc.mensagem}), 400
    ultimo = model.ultimo_log_ok(g.user["id"], username)
    return jsonify(username=username, projetos=model.listar_projetos(g.user["id"], username),
                   resumo=ultimo["resumo"] if ultimo else None, atualizado_em=ultimo["criado_em"] if ultimo else None)


@bp.get("/api/github/logs")
@permission_required("github.ver_proprios")
def logs():
    todos = pode(g.user, "github.ver_todos") and request.args.get("escopo") == "todos"
    return jsonify(logs=model.listar_logs(None if todos else g.user["id"]), escopo="todos" if todos else "proprios")

