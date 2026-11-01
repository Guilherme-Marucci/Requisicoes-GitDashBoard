"""Login e logout."""

from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from painel.security import csrf_token, csrf_valido, destino_seguro, encerrar_sessao, iniciar_sessao
from painel.services import auth_service

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None and request.method == "GET":
        return redirect(destino_seguro(request.args.get("next")))
    erro, identificador = None, ""
    next_url = request.values.get("next", "")
    if request.method == "POST":
        identificador = request.form.get("identificador", "").strip()
        try:
            user = auth_service.autenticar(identificador, request.form.get("senha", ""))
        except auth_service.ContaBloqueada as exc:
            erro = str(exc)
        except auth_service.CredenciaisInvalidas as exc:
            erro = str(exc)
        else:
            iniciar_sessao(user)
            return redirect(destino_seguro(next_url))
    csrf_token()
    return render_template("login.html", erro=erro, identificador=identificador, next_url=next_url), (401 if erro else 200)


@bp.post("/logout")
def logout():
    encerrar_sessao()
    flash("Sessão encerrada.", "info")
    return redirect(url_for("auth.login"))

