"""Fábrica da aplicação Flask: configuração, sessão, RBAC, CSRF, cabeçalhos de segurança e blueprints."""

from __future__ import annotations

from flask import Flask, g, jsonify, render_template, request, session

from painel import security
from painel.config import TEMAS, build_config
from painel.db import DatabaseUnavailable, close_db
from painel.models import usuarios
from painel.services import auth_service, requisicoes_service


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(build_config(overrides))
    app.teardown_appcontext(close_db)

    from painel.routes import auth, config, github, main, requisicoes
    for module in (auth, main, requisicoes, github, config):
        app.register_blueprint(module.bp)

    @app.before_request
    def carregar_usuario_e_csrf():
        g.user = None
        if request.endpoint == "static":
            return None
        uid = session.get("uid")
        if uid is not None:
            user = usuarios.buscar_por_id(uid)
            if user and user["ativo"]:
                g.user = user
            else:
                session.clear()  # conta removida/desativada derruba a sessão imediatamente
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not security.csrf_valido():
            if security.wants_json():
                return jsonify(erro={"codigo": "csrf", "mensagem": "Token CSRF ausente ou inválido."}), 400
            return render_template("erro.html", titulo="Sessão do formulário expirada",
                                   mensagem="Recarregue a página e tente novamente."), 400
        return None

    @app.after_request
    def cabecalhos(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "frame-ancestors 'none'; form-action 'self'; base-uri 'self'",
        )
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.context_processor
    def contexto():
        user = g.get("user")
        return {
            "current_user": auth_service.usuario_publico(user) if user else None,
            "tema_atual": user["tema"] if user and user["tema"] in TEMAS else "dark",
            "csrf_token": security.csrf_token,
            "pode": lambda permissao: security.pode(user, permissao),
            "STATUS": requisicoes_service.STATUS,
            "SETORES": requisicoes_service.SETORES,
            "PRIORIDADES": requisicoes_service.PRIORIDADES,
        }

    @app.template_filter("dt")
    def fmt_dt(value, formato="%d/%m/%Y %H:%M"):
        return value.strftime(formato) if value else "—"

    @app.template_filter("moeda")
    def fmt_moeda(value):
        if value is None:
            return "—"
        texto = f"{float(value):,.2f}"
        return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")

    @app.errorhandler(DatabaseUnavailable)
    def sem_banco(exc):
        if security.wants_json():
            return jsonify(erro={"codigo": "banco_indisponivel", "mensagem": str(exc)}), 503
        return render_template("erro.html", titulo="Banco indisponível", mensagem=str(exc)), 503

    for status, titulo in ((403, "Acesso negado"), (404, "Não encontrado"), (413, "Requisição grande demais")):
        def handler(_exc, status=status, titulo=titulo):
            if security.wants_json():
                return jsonify(erro={"codigo": f"http_{status}", "mensagem": titulo}), status
            return render_template("erro.html", titulo=titulo, mensagem="Verifique o endereço ou suas permissões."), status
        app.register_error_handler(status, handler)

    return app

