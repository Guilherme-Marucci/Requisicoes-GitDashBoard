"""Configurações do usuário (tema, perfil, senha) e administração de usuários."""

from __future__ import annotations

import re

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from painel.config import TEMAS
from painel.models import usuarios
from painel.security import ROLE_SUPER, permission_required
from painel.services import auth_service, github_service

bp = Blueprint("config", __name__)
ROLES = ("usuario", "admin", "super-admin")


@bp.get("/configuracoes")
@permission_required("preferencias.editar")
def configuracoes():
    return render_template("configuracoes.html", temas=TEMAS)


@bp.post("/api/preferencias/tema")
@permission_required("preferencias.editar")
def salvar_tema():
    body = request.get_json(silent=True) or {}
    tema = str(body.get("tema", "")) if isinstance(body, dict) else ""
    if tema not in TEMAS:
        return jsonify(erro={"codigo": "validacao", "mensagem": "Tema inválido."}), 422
    usuarios.atualizar_tema(g.user["id"], tema)
    return jsonify(tema=tema)


@bp.post("/configuracoes/perfil")
@permission_required("preferencias.editar")
def salvar_perfil():
    nome = re.sub(r"\s+", " ", request.form.get("nome", "")).strip()
    github = request.form.get("github_username", "").strip()
    if not 2 <= len(nome) <= 120:
        flash("Informe um nome entre 2 e 120 caracteres.", "erro")
        return redirect(url_for("config.configuracoes"))
    if github:
        try:
            github = github_service.extrair_username(github)
        except github_service.GitHubErro as exc:
            flash(exc.mensagem, "erro")
            return redirect(url_for("config.configuracoes"))
    usuarios.atualizar_perfil(g.user["id"], nome, github or None)
    flash("Perfil atualizado.", "ok")
    return redirect(url_for("config.configuracoes"))


@bp.post("/configuracoes/senha")
@permission_required("preferencias.editar")
def alterar_senha():
    atual, nova = request.form.get("senha_atual", ""), request.form.get("senha_nova", "")
    from werkzeug.security import check_password_hash
    if not check_password_hash(g.user["senha_hash"], atual):
        flash("Senha atual incorreta.", "erro")
    elif nova != request.form.get("senha_confirma", ""):
        flash("A confirmação não confere com a nova senha.", "erro")
    else:
        try:
            auth_service.validar_politica_senha(nova)
        except auth_service.SenhaFraca as exc:
            flash(str(exc), "erro")
        else:
            usuarios.atualizar_senha(g.user["id"], auth_service.hash_senha(nova))
            flash("Senha alterada com sucesso.", "ok")
    return redirect(url_for("config.configuracoes"))


# --------------------------------------------------------------------- administração (super-admin)
@bp.get("/admin/usuarios")
@permission_required("usuarios.gerenciar")
def admin_usuarios():
    return render_template("admin_usuarios.html", lista=usuarios.listar(), roles=ROLES)


@bp.post("/admin/usuarios/<int:user_id>/role")
@permission_required("usuarios.gerenciar")
def admin_role(user_id: int):
    role = request.form.get("role", "")
    if role not in ROLES:
        abort(422)
    if user_id == g.user["id"] and role != ROLE_SUPER:
        flash("Você não pode remover seu próprio perfil de super-admin.", "erro")
    elif usuarios.buscar_por_id(user_id) is None:
        abort(404)
    else:
        usuarios.alterar_role(user_id, role)
        flash("Perfil atualizado.", "ok")
    return redirect(url_for("config.admin_usuarios"))


@bp.post("/admin/usuarios/<int:user_id>/ativo")
@permission_required("usuarios.gerenciar")
def admin_ativo(user_id: int):
    if user_id == g.user["id"]:
        flash("Você não pode desativar a própria conta.", "erro")
    elif usuarios.buscar_por_id(user_id) is None:
        abort(404)
    else:
        usuarios.alterar_ativo(user_id, request.form.get("ativo") == "1")
        flash("Situação da conta atualizada.", "ok")
    return redirect(url_for("config.admin_usuarios"))

