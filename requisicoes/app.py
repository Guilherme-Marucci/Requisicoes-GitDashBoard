"""Entrada HTTP de Requisições: páginas, autenticação por perfil e leitura do JSON privado."""

from datetime import timedelta
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, url_for

from core.auth import (
    AuthServiceUnavailableError,
    CorporateDomainError,
    InvalidCredentialsError,
    PasswordPolicyError,
    ROLE_TV,
    TokenInvalidOrExpiredError,
    UserAlreadyExistsError,
    autenticar_usuario_mysql,
    destino_seguro,
    encerrar_sessao_usuario,
    gerar_csrf_token,
    iniciar_sessao_usuario,
    obter_usuario_sessao,
    redefinir_senha_com_token,
    registrar_usuario,
    resolve_secret_key,
    solicitar_recuperacao_senha,
    validar_csrf_token,
    verificar_token_ativacao,
)
from core.config import load_environment, positive_integer
from core.pedidos import available_branches, calcular_metricas_pedidos, filtrar_pedidos, paginar_pedidos
from core.rankings import calcular_rankings
from core.requisicoes import SnapshotUnavailable, dashboard_payload, read_named_snapshot, storage_directory

_PUBLIC_ENDPOINTS = frozenset({
    "static",
    "health",
    "login",
    "login_submit",
    "legacy_login",
    "logout",
    "api_auth_register",
    "auth_verify_email",
    "api_auth_forgot_password",
    "api_auth_reset_password",
})
_TV_ALLOWED_ENDPOINTS = frozenset({"tv", "tv_chart", "tv_dataset", "logout", "health", "static"})


def create_app(config=None) -> Flask:
    """Cria uma aplicação independente, também utilizável pelo cliente de testes."""
    application = Flask(__name__)
    env_values = load_environment()
    default_storage = storage_directory()
    application.config.update(
        SNAPSHOT_DIR=default_storage,
        SNAPSHOT_MAX_AGE_SECONDS=positive_integer(env_values, "REQUISICOES_MAX_AGE_SECONDS", 900),
        SECRET_KEY=resolve_secret_key(env_values, default_storage),
        SESSION_COOKIE_NAME="ssonic_req_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        AUTH_BACKEND=autenticar_usuario_mysql,
        AUTH_REGISTER_BACKEND=registrar_usuario,
        AUTH_VERIFY_BACKEND=verificar_token_ativacao,
        AUTH_FORGOT_BACKEND=solicitar_recuperacao_senha,
        AUTH_RESET_BACKEND=redefinir_senha_com_token,
    )
    if config:
        application.config.update(config)
    if application.config["SNAPSHOT_MAX_AGE_SECONDS"] <= 0:
        raise ValueError("O limite de atualização deve ser positivo.")

    @application.context_processor
    def inject_auth_context():
        user = obter_usuario_sessao()
        return {
            "current_user": user,
            "is_tv_only": bool(user and user.get("role") == ROLE_TV),
        }

    @application.before_request
    def enforce_access_control():
        """Aplica autenticação de sessão e isola o perfil da TV (projetos@ssonic.com.br / TVREQ) na rota /tv."""
        endpoint = request.endpoint
        if endpoint is None or endpoint in _PUBLIC_ENDPOINTS or request.path.startswith("/static/"):
            return None

        # O rodapé institucional é utilizado também pela tela pública de login.
        if endpoint == "component" and (request.view_args or {}).get("filename") == "footer.html":
            return None

        user = obter_usuario_sessao()
        is_api_or_fragment = request.path.startswith("/api/") or endpoint == "component"

        if user is None:
            if is_api_or_fragment:
                response = jsonify(error={
                    "code": "unauthenticated",
                    "message": "Sessão não autenticada ou expirada.",
                })
                response.status_code = 401
                return response
            next_target = request.full_path.rstrip("?") if request.query_string else request.path
            return redirect(url_for("login", next=next_target))

        if user.get("role") == ROLE_TV and endpoint not in _TV_ALLOWED_ENDPOINTS:
            if is_api_or_fragment:
                response = jsonify(error={
                    "code": "forbidden",
                    "message": "Acesso restrito ao Painel TV.",
                })
                response.status_code = 403
                return response
            return redirect(url_for("tv"))

        return None

    @application.after_request
    def apply_security_headers(response):
        """Cabeçalhos defensivos contra MIME-sniffing, clickjacking e cache de sessão após logout."""
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if not request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/components/<filename>")
    def component(filename):
        """Entrega somente os fragmentos públicos da composição da interface."""
        if filename not in {"sidebar.html", "topbar.html", "footer.html"}:
            abort(404)
        return send_from_directory(Path(application.root_path) / "components", filename, max_age=0)

    @application.get("/")
    def index():
        return render_template("index.html")

    @application.get("/pedidos")
    def pedidos():
        """Página dedicada de Acompanhamento de Pedidos vinculados às requisições."""
        return render_template("pedidos.html")

    @application.get("/tv")
    def tv():
        """Painel de exibição: utiliza o mesmo retrato, sem acionar a coleta."""
        return render_template("tv.html")

    @application.get("/tv/grafico")
    def tv_chart():
        """Gráfico independente, com a mesma leitura do JSON privado."""
        return render_template("tv_grafico.html", is_graph=True)

    @application.get("/api/tv/<alvo>")
    def tv_dataset(alvo):
        """Entrega o snapshot correspondente (situacoes, pedidos, nf)."""
        mapa_arquivos = {
            "situacoes": "tv_situac.json",
            "pedidos":   "tv_pedidos.json",
            "nf":        "tv_nf.json",
        }
        if alvo not in mapa_arquivos:
            abort(404)

        try:
            dados = read_named_snapshot(
                Path(application.config["SNAPSHOT_DIR"]),
                mapa_arquivos[alvo],
                application.config["SNAPSHOT_MAX_AGE_SECONDS"],
            )
            response = jsonify(dados)
        except SnapshotUnavailable:
            response = jsonify(error={"code": "snapshot_unavailable", "message": "Aguardando primeira coleta."})
            response.status_code = 503

        response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/login")
    def login():
        user = obter_usuario_sessao()
        if user is not None:
            return redirect(destino_seguro(request.args.get("next"), user["role"]))
        return render_template(
            "login.html",
            csrf_token=gerar_csrf_token(),
            next_url=request.args.get("next", ""),
            prefill_email="",
            error_message=None,
            info_message=None,
        )

    @application.post("/login")
    def login_submit():
        """Valida credenciais via backend configurado e redireciona conforme o perfil."""
        payload = request.get_json(silent=True) if request.is_json else None
        identificador = str((payload or request.form).get("email", "")).strip()
        senha = str((payload or request.form).get("password") or (payload or request.form).get("senha") or "")
        next_url = str((payload or request.form).get("next", "")).strip()

        if not request.is_json and not validar_csrf_token(request.form.get("csrf_token")):
            return (
                render_template(
                    "login.html",
                    csrf_token=gerar_csrf_token(),
                    next_url=next_url,
                    prefill_email=identificador,
                    error_message="A sessão do formulário expirou. Tente entrar novamente.",
                    info_message=None,
                ),
                400,
            )

        auth_backend = application.config["AUTH_BACKEND"]
        try:
            user = auth_backend(identificador, senha)
        except CorporateDomainError:
            if request.is_json:
                return jsonify({"erro": "Domínio corporativo não autorizado"}), 400
            return (
                render_template(
                    "login.html",
                    csrf_token=gerar_csrf_token(),
                    next_url=next_url,
                    prefill_email=identificador,
                    error_message="Domínio corporativo não autorizado",
                    info_message=None,
                ),
                400,
            )
        except InvalidCredentialsError as exc:
            if request.is_json:
                return jsonify({"erro": str(exc)}), 401
            return (
                render_template(
                    "login.html",
                    csrf_token=gerar_csrf_token(),
                    next_url=next_url,
                    prefill_email=identificador,
                    error_message=str(exc),
                    info_message=None,
                ),
                401,
            )
        except AuthServiceUnavailableError as exc:
            if request.is_json:
                return jsonify({"erro": str(exc)}), 503
            return (
                render_template(
                    "login.html",
                    csrf_token=gerar_csrf_token(),
                    next_url=next_url,
                    prefill_email=identificador,
                    error_message=str(exc),
                    info_message=None,
                ),
                503,
            )

        iniciar_sessao_usuario(user)
        target = destino_seguro(next_url, user["role"])
        if request.is_json:
            return jsonify({"redirect": target, "role": user["role"], "email": user["email"]}), 200
        return redirect(target)

    @application.route("/logout", methods=["GET", "POST"])
    def logout():
        encerrar_sessao_usuario()
        return redirect(url_for("login"))

    def _read_auth_body() -> dict:
        if request.is_json:
            data = request.get_json(silent=True)
            return data if isinstance(data, dict) else {}
        return request.form.to_dict()

    @application.post("/api/auth/registrar")
    def api_auth_register():
        """Registra novo usuário (@ssonic.com.br) com ativo=0 e despacha token de verificação (24h)."""
        body = _read_auth_body()
        email = str(body.get("email") or "")
        senha = str(body.get("senha") or body.get("password") or "")
        nome = str(body.get("nome") or body.get("name") or "")
        telefone = body.get("telefone")

        register_fn = application.config["AUTH_REGISTER_BACKEND"]
        try:
            created = register_fn(email=email, senha=senha, nome=nome, telefone=telefone)
        except CorporateDomainError:
            return jsonify({"erro": "Domínio corporativo não autorizado"}), 400
        except (PasswordPolicyError, UserAlreadyExistsError) as exc:
            return jsonify({"erro": str(exc)}), 400
        except AuthServiceUnavailableError as exc:
            return jsonify({"erro": str(exc)}), 503

        return (
            jsonify({
                "mensagem": "Cadastro realizado. Verifique seu e-mail corporativo em até 24 horas para ativar a conta.",
                "email": created["email"],
                "ativo": 0,
                "email_verificado": 0,
            }),
            201,
        )

    @application.get("/auth/verificar")
    def auth_verify_email():
        """Valida o token de verificação de 24h, ativa o usuário e invalida o token."""
        token = request.args.get("token", "").strip()
        verify_fn = application.config["AUTH_VERIFY_BACKEND"]
        accept = request.headers.get("Accept", "")
        wants_html = "text/html" in accept and "application/json" not in accept

        try:
            verified = verify_fn(token)
        except TokenInvalidOrExpiredError as exc:
            if wants_html:
                return (
                    render_template(
                        "login.html",
                        csrf_token=gerar_csrf_token(),
                        next_url="",
                        prefill_email="",
                        error_message=str(exc),
                        info_message=None,
                    ),
                    400,
                )
            return jsonify({"erro": str(exc)}), 400
        except AuthServiceUnavailableError as exc:
            if wants_html:
                return (
                    render_template(
                        "login.html",
                        csrf_token=gerar_csrf_token(),
                        next_url="",
                        prefill_email="",
                        error_message=str(exc),
                        info_message=None,
                    ),
                    503,
                )
            return jsonify({"erro": str(exc)}), 503

        if wants_html:
            return (
                render_template(
                    "login.html",
                    csrf_token=gerar_csrf_token(),
                    next_url="",
                    prefill_email=verified.get("email", ""),
                    error_message=None,
                    info_message="E-mail verificado com sucesso! Sua conta está ativa para acesso.",
                ),
                200,
            )
        return (
            jsonify({
                "mensagem": "E-mail verificado e conta ativada com sucesso.",
                "email": verified.get("email"),
                "ativo": 1,
                "email_verificado": 1,
            }),
            200,
        )

    @application.post("/api/auth/esqueci-senha")
    def api_auth_forgot_password():
        """Inicia recuperação de senha com resposta e tempo uniformes contra enumeração."""
        body = _read_auth_body()
        email = str(body.get("email") or "")
        forgot_fn = application.config["AUTH_FORGOT_BACKEND"]
        try:
            resposta = forgot_fn(email)
        except CorporateDomainError:
            return jsonify({"erro": "Domínio corporativo não autorizado"}), 400
        except AuthServiceUnavailableError as exc:
            return jsonify({"erro": str(exc)}), 503

        return jsonify(resposta), 200

    @application.post("/api/auth/redefinir-senha")
    def api_auth_reset_password():
        """Consome token descartável de 20 minutos e redefine senha com PBKDF2-HMAC-SHA256."""
        body = _read_auth_body()
        token = str(body.get("token") or "")
        nova_senha = str(body.get("nova_senha") or body.get("password") or "")
        reset_fn = application.config["AUTH_RESET_BACKEND"]
        try:
            reset_fn(token, nova_senha)
        except (TokenInvalidOrExpiredError, PasswordPolicyError) as exc:
            return jsonify({"erro": str(exc)}), 400
        except AuthServiceUnavailableError as exc:
            return jsonify({"erro": str(exc)}), 503

        return jsonify({"mensagem": "Senha redefinida com sucesso."}), 200

    # Preserva os links dos fragmentos e favoritos anteriores à migração para templates.
    @application.get("/index.html")
    def legacy_index():
        return redirect(url_for("index"))

    @application.get("/login.html")
    def legacy_login():
        return redirect(url_for("login"))

    @application.get("/pedidos.html")
    def legacy_pedidos():
        return redirect(url_for("pedidos"))

    @application.get("/api/health")
    def health():
        """Confirma somente o processo HTTP; não indica disponibilidade de ERP ou banco."""
        return jsonify(status="ok", service="requisicoes", mode="somente_leitura")

    @application.get("/api/requisicoes")
    def requests_snapshot():
        """Entrega o último retrato; navegar nunca dispara coleta ou consulta ao banco."""
        try:
            payload = dashboard_payload(Path(application.config["SNAPSHOT_DIR"]),
                                        application.config["SNAPSHOT_MAX_AGE_SECONDS"])
            response = jsonify(payload)
        except SnapshotUnavailable:
            response = jsonify(error={"code": "snapshot_unavailable",
                                      "message": "Dados indisponíveis. Aguardando uma coleta válida."})
            response.status_code = 503
        response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/api/rankings")
    def rankings_endpoint():
        """Entrega os dados de ranking (top requerentes, setores, itens) baseados no último retrato."""
        try:
            payload = dashboard_payload(Path(application.config["SNAPSHOT_DIR"]),
                                        application.config["SNAPSHOT_MAX_AGE_SECONDS"])
            rankings = calcular_rankings(payload.get("requests", []))
            response = jsonify({
                "meta": payload.get("meta", {}),
                "rankings": rankings
            })
        except SnapshotUnavailable:
            response = jsonify(error={"code": "snapshot_unavailable",
                                      "message": "Dados indisponíveis. Aguardando uma coleta válida."})
            response.status_code = 503
        response.headers["Cache-Control"] = "no-store"
        return response

    def _parse_int_arg(name: str, default: int) -> int:
        raw = request.args.get(name, "")
        try:
            return int(raw) if raw != "" else default
        except ValueError:
            return default

    @application.get("/api/pedidos")
    def pedidos_list_endpoint():
        """Lista paginada de itens de pedidos vinculados às requisições (filtros por filial, período, status e busca)."""
        try:
            snapshot = read_named_snapshot(
                Path(application.config["SNAPSHOT_DIR"]),
                "tv_pedidos.json",
                application.config["SNAPSHOT_MAX_AGE_SECONDS"],
            )
            all_orders = snapshot.get("orders", [])
            applied = {
                "filial": request.args.get("filial", "").strip(),
                "data_inicio": request.args.get("data_inicio", "").strip(),
                "data_fim": request.args.get("data_fim", "").strip(),
                "status": request.args.get("status", "").strip(),
                "q": request.args.get("q", "").strip(),
                "ordenar": request.args.get("ordenar", "datinc_desc").strip() or "datinc_desc",
            }
            filtrados = filtrar_pedidos(all_orders, **applied)
            paginado = paginar_pedidos(
                filtrados,
                page=_parse_int_arg("page", 1),
                per_page=_parse_int_arg("per_page", 50),
            )
            response = jsonify({
                "meta": snapshot.get("meta", {}),
                "filters": {
                    "availableBranches": available_branches(all_orders),
                    "applied": applied,
                },
                "pagination": paginado["pagination"],
                "items": paginado["items"],
            })
        except SnapshotUnavailable:
            response = jsonify(error={
                "code": "snapshot_unavailable",
                "message": "Dados de pedidos indisponíveis. Aguardando uma coleta válida.",
            })
            response.status_code = 503
        response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/api/pedidos/metricas")
    def pedidos_metrics_endpoint():
        """Agregador financeiro e operacional de pedidos (Total Trimestre, Ticket Médio, % Atendido, Comparativo Mensal)."""
        try:
            snapshot = read_named_snapshot(
                Path(application.config["SNAPSHOT_DIR"]),
                "tv_pedidos.json",
                application.config["SNAPSHOT_MAX_AGE_SECONDS"],
            )
            all_orders = snapshot.get("orders", [])
            filtrados = filtrar_pedidos(
                all_orders,
                filial=request.args.get("filial", "").strip(),
                data_inicio=request.args.get("data_inicio", "").strip(),
                data_fim=request.args.get("data_fim", "").strip(),
                status=request.args.get("status", "").strip(),
                q=request.args.get("q", "").strip(),
            )
            metrics = calcular_metricas_pedidos(filtrados)
            response = jsonify({
                "meta": snapshot.get("meta", {}),
                "metrics": metrics,
            })
        except SnapshotUnavailable:
            response = jsonify(error={
                "code": "snapshot_unavailable",
                "message": "Métricas de pedidos indisponíveis. Aguardando uma coleta válida.",
            })
            response.status_code = 503
        response.headers["Cache-Control"] = "no-store"
        return response

    return application


app = create_app()

if __name__ == "__main__":
    # Servidor HTTP acessível na rede local para exibição nas TVs, sem depurador habilitado.
    app.run(host="0.0.0.0", port=5000, debug=False)
