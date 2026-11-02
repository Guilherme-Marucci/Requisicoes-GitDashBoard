"""Painel (listagem, filtros e métricas) e health check."""

from __future__ import annotations

from datetime import datetime
import json
from math import ceil

from flask import Blueprint, g, jsonify, render_template, request

from painel.db import fetch_one
from painel.models import github as gh_model
from painel.models import requisicoes as model
from painel.security import login_required, pode
from painel.services import requisicoes_service as svc

bp = Blueprint("main", __name__)
POR_PAGINA = 15


def escopo_requerente() -> int | None:
    """Usuário comum enxerga somente o que criou; admin/super-admin enxergam tudo."""
    return None if pode(g.user, "requisicoes.ver_todas") else g.user["id"]


def pagina_atual() -> int:
    try:
        return max(1, int(request.args.get("pagina", 1)))
    except ValueError:
        return 1


@bp.get("/requisicoes")
@login_required
def painel():
    filtros = svc.normalizar_filtros(request.args)
    escopo = escopo_requerente()
    pagina = pagina_atual()
    itens, total = model.listar(filtros, escopo, pagina, POR_PAGINA)
    return render_template(
        "painel.html", itens=itens, total=total, pagina=pagina, paginas=max(1, ceil(total / POR_PAGINA)),
        filtros=filtros, metricas=model.metricas(filtros, escopo), opcoes=model.opcoes_filtro(escopo),
        escopo_proprio=escopo is not None,
    )


@bp.get("/tv")
def tv():
    """Painel de exibição contínua para TVs corporativas e telões."""
    return render_template("tv.html")


@bp.get("/api/tv/dados")
def api_tv_dados():
    """Dados consolidados para auto-refresh silencioso do painel de TV."""
    metricas_req = model.metricas({}, None)
    itens_req, total_req = model.listar({}, None, 1, 8)

    projetos_gh = gh_model.listar_projetos(None)
    ultimo_log = fetch_one(
        "SELECT resumo, criado_em, github_username FROM github_metricas_log WHERE resultado='ok' ORDER BY id DESC LIMIT 1"
    )
    resumo_gh = None
    if ultimo_log and ultimo_log.get("resumo"):
        try:
            resumo_gh = json.loads(ultimo_log["resumo"]) if isinstance(ultimo_log["resumo"], str) else ultimo_log["resumo"]
        except Exception:
            resumo_gh = None

    def _serializar_req(r):
        return {
            "id": r["id"],
            "codigo": r["codigo"],
            "titulo": r["titulo"],
            "item": r["item"],
            "setor": svc.SETORES.get(r["setor"], r["setor"]),
            "prioridade": r["prioridade"],
            "status": r["status"],
            "status_label": svc.STATUS.get(r["status"], r["status"]),
            "requerente_nome": r.get("requerente_nome", "—"),
            "criado_em": r["criado_em"].strftime("%d/%m %H:%M") if r.get("criado_em") else "—",
        }

    return jsonify({
        "requisicoes": {
            "metricas": metricas_req,
            "itens": [_serializar_req(i) for i in itens_req],
            "total": total_req,
        },
        "github": {
            "projetos": projetos_gh[:8],
            "resumo": resumo_gh,
            "username": ultimo_log["github_username"] if ultimo_log else None,
        },
        "atualizado_em": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    })


@bp.get("/api/health")
def health():
    return jsonify(status="ok", service="painel-requisicoes", persistencia="mysql")

