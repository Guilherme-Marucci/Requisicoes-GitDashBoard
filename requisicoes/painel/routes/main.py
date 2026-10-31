"""Painel (listagem, filtros e métricas) e health check."""

from __future__ import annotations

from math import ceil

from flask import Blueprint, g, jsonify, render_template, request

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


@bp.get("/")
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


@bp.get("/api/health")
def health():
    return jsonify(status="ok", service="painel-requisicoes", persistencia="mysql")

