"""Requisições: páginas HTML e API JSON (CRUD completo com validação no servidor)."""

from __future__ import annotations

from math import ceil

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from painel.models import requisicoes as model
from painel.routes.main import POR_PAGINA, escopo_requerente, pagina_atual
from painel.security import login_required, permission_required, pode
from painel.services import requisicoes_service as svc

bp = Blueprint("requisicoes", __name__)

EDITAVEL_PELO_DONO = {"registered", "pending"}


def _carregar(req_id: int) -> dict:
    """Carrega a requisição respeitando o escopo; para o usuário comum, de terceiros = 404 (sem vazar existência)."""
    row = model.buscar(req_id)
    if row is None or (escopo_requerente() is not None and row["requerente_id"] != g.user["id"]):
        abort(404)
    return row


def _pode_editar(row: dict) -> bool:
    if pode(g.user, "requisicoes.editar_todas"):
        return True
    return (pode(g.user, "requisicoes.editar_proprias") and row["requerente_id"] == g.user["id"]
            and row["status"] in EDITAVEL_PELO_DONO)


def _payload() -> dict:
    if request.is_json:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}
    return request.form.to_dict()


def _erro_validacao(exc: svc.ValidacaoErro):
    return jsonify(erro={"codigo": "validacao", "mensagem": "Dados inválidos.", "campos": exc.erros}), 422


def _serializar(row: dict) -> dict:
    return {**row, "status_label": svc.STATUS[row["status"]], "setor_label": svc.SETORES.get(row["setor"], row["setor"])}


# ----------------------------------------------------------------------------- Páginas
@bp.route("/requisicoes/nova", methods=["GET", "POST"])
@permission_required("requisicoes.criar")
def nova():
    valores, erros = {"prioridade": "media", "unidade": "UN"}, {}
    if request.method == "POST":
        valores = request.form.to_dict()
        try:
            dados = svc.validar_requisicao(valores)
        except svc.ValidacaoErro as exc:
            erros = exc.erros
        else:
            new_id, codigo = model.criar(dados, g.user["id"])
            flash(f"Requisição {codigo} cadastrada com sucesso.", "ok")
            return redirect(url_for("requisicoes.detalhe", req_id=new_id))
    return render_template("requisicao_form.html", valores=valores, erros=erros, edicao=False, svc=svc), (422 if erros else 200)


@bp.get("/requisicoes/<int:req_id>")
@login_required
def detalhe(req_id: int):
    row = _carregar(req_id)
    return render_template(
        "requisicao_detalhe.html", r=row, historico=model.historico(req_id), svc=svc, pode_editar=_pode_editar(row),
        proximos=svc.STATUS if pode(g.user, "requisicoes.excluir") else sorted(svc.TRANSICOES[row["status"]]),
    )


@bp.route("/requisicoes/<int:req_id>/editar", methods=["GET", "POST"])
@login_required
def editar(req_id: int):
    row = _carregar(req_id)
    if not _pode_editar(row):
        abort(403)
    valores, erros = {**row, "prazo": row["prazo"].isoformat() if row["prazo"] else ""}, {}
    if request.method == "POST":
        valores = request.form.to_dict()
        try:
            dados = svc.validar_requisicao(valores)
        except svc.ValidacaoErro as exc:
            erros = exc.erros
        else:
            model.atualizar(req_id, dados, g.user["id"])
            flash("Requisição atualizada.", "ok")
            return redirect(url_for("requisicoes.detalhe", req_id=req_id))
    return render_template("requisicao_form.html", valores=valores, erros=erros, edicao=True, r=row, svc=svc), (422 if erros else 200)


@bp.post("/requisicoes/<int:req_id>/status")
@permission_required("requisicoes.alterar_status")
def alterar_status(req_id: int):
    row = _carregar(req_id)
    try:
        comentario = svc.validar_mudanca_status(row["status"], request.form.get("status", ""),
                                                request.form.get("comentario"), super_admin=pode(g.user, "requisicoes.excluir"))
    except svc.ValidacaoErro as exc:
        flash(" ".join(exc.erros.values()), "erro")
    else:
        model.alterar_status(req_id, row["status"], request.form["status"], g.user["id"], comentario)
        flash("Status atualizado.", "ok")
    return redirect(url_for("requisicoes.detalhe", req_id=req_id))


@bp.post("/requisicoes/<int:req_id>/excluir")
@permission_required("requisicoes.excluir")
def excluir(req_id: int):
    row = _carregar(req_id)
    model.excluir(req_id)
    flash(f"Requisição {row['codigo']} excluída.", "ok")
    return redirect(url_for("main.painel"))


# ----------------------------------------------------------------------------- API JSON
@bp.get("/api/requisicoes")
@login_required
def api_listar():
    filtros = svc.normalizar_filtros(request.args)
    escopo = escopo_requerente()
    pagina = pagina_atual()
    itens, total = model.listar(filtros, escopo, pagina, POR_PAGINA)
    return jsonify(itens=[_serializar(i) for i in itens], paginacao={"pagina": pagina, "por_pagina": POR_PAGINA,
                   "total": total, "paginas": max(1, ceil(total / POR_PAGINA))},
                   metricas=model.metricas(filtros, escopo), filtros=filtros)


@bp.post("/api/requisicoes")
@permission_required("requisicoes.criar")
def api_criar():
    try:
        dados = svc.validar_requisicao(_payload())
    except svc.ValidacaoErro as exc:
        return _erro_validacao(exc)
    new_id, codigo = model.criar(dados, g.user["id"])
    return jsonify(_serializar(model.buscar(new_id))), 201


@bp.get("/api/requisicoes/<int:req_id>")
@login_required
def api_detalhe(req_id: int):
    return jsonify(requisicao=_serializar(_carregar(req_id)), historico=model.historico(req_id))


@bp.put("/api/requisicoes/<int:req_id>")
@login_required
def api_atualizar(req_id: int):
    row = _carregar(req_id)
    if not _pode_editar(row):
        return jsonify(erro={"codigo": "acesso_negado", "mensagem": "Edição não permitida."}), 403
    try:
        dados = svc.validar_requisicao(_payload())
    except svc.ValidacaoErro as exc:
        return _erro_validacao(exc)
    model.atualizar(req_id, dados, g.user["id"])
    return jsonify(_serializar(model.buscar(req_id)))


@bp.patch("/api/requisicoes/<int:req_id>/status")
@permission_required("requisicoes.alterar_status")
def api_status(req_id: int):
    row = _carregar(req_id)
    body = _payload()
    try:
        comentario = svc.validar_mudanca_status(row["status"], str(body.get("status", "")), body.get("comentario"),
                                                super_admin=pode(g.user, "requisicoes.excluir"))
    except svc.ValidacaoErro as exc:
        return _erro_validacao(exc)
    model.alterar_status(req_id, row["status"], body["status"], g.user["id"], comentario)
    return jsonify(_serializar(model.buscar(req_id)))


@bp.delete("/api/requisicoes/<int:req_id>")
@permission_required("requisicoes.excluir")
def api_excluir(req_id: int):
    _carregar(req_id)
    model.excluir(req_id)
    return "", 204
