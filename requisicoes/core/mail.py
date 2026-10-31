"""Mensageria corporativa: disparo SMTP transacional (multipart) para @ssonic.com.br.

Responsabilidades deste módulo (sem dependência de core.auth, evitando importação circular):
- Whitelist estrita do destinatário (somente @ssonic.com.br), aplicada ANTES de qualquer disparo,
  inclusive no modo mock.
- Sanitização de cabeçalhos (Subject, To, From) contra injeção de CRLF.
- Montagem MIME multipart/alternative (texto puro + HTML responsivo).
- Transporte STARTTLS (587) ou SSL/TLS nativo (465) com timeout fixo de 10 s.
- Modo MAIL_ENABLED=false: nenhuma conexão de rede; o link (com o token) é registrado no console
  somente para desenvolvimento.

Falhas de rede/SMTP viram EmailTransportError com log sanitizado (tipo da exceção e código SMTP,
nunca mensagens do servidor, destinatário ou credenciais). A conversão para
AuthServiceUnavailableError (HTTP 503) é feita em core.auth.
"""

from datetime import timedelta
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
import html
import logging
import re
import smtplib
import socket
import ssl
from urllib.parse import quote

from core.config import MAIL_TIMEOUT_SECONDS, ConfigurationError, MailConfig

logger = logging.getLogger(__name__)

# Whitelist: domínio exato, sem subdomínios. fullmatch evita que "\n" final passe por "$".
_RECIPIENT_RE = re.compile(r"[a-z0-9._%+-]+@ssonic\.com\.br")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f\u2028\u2029]")

# Identidade visual Supersonic (supersonic.css) em estilos inline, exigidos por clientes de e-mail.
_COLOR_NIGHT = "#394f5a"
_COLOR_DAY = "#14b1e7"
_COLOR_BUTTON = "#08799f"


class EmailTransportError(Exception):
    """Falha de rede, TLS ou SMTP ao entregar a mensagem (já registrada em log sanitizado)."""


class RecipientNotAllowedError(ValueError):
    """Destinatário fora do domínio corporativo ou com caracteres de controle."""


def sanitizar_cabecalho(valor) -> str:
    """Remove CR/LF e demais caracteres de controle, impedindo a injeção de novos cabeçalhos."""
    texto = "" if valor is None else str(valor)
    return " ".join(_CONTROL_CHARS_RE.sub(" ", texto).split())


def validar_destinatario(destinatario) -> str:
    """Retorna o endereço normalizado ou rejeita qualquer destinatário fora de @ssonic.com.br."""
    if not isinstance(destinatario, str) or _CONTROL_CHARS_RE.search(destinatario):
        raise RecipientNotAllowedError("Destinatário inválido.")
    normalizado = destinatario.strip().lower()
    if not _RECIPIENT_RE.fullmatch(normalizado):
        raise RecipientNotAllowedError("Domínio corporativo não autorizado")
    return normalizado


def rotulo_validade(validade: timedelta) -> str:
    """Converte a validade real do token em texto (24 horas, 20 minutos), evitando divergência."""
    minutos = max(1, int(validade.total_seconds() // 60))
    if minutos % 60 == 0:
        horas = minutos // 60
        return f"{horas} hora" if horas == 1 else f"{horas} horas"
    return f"{minutos} minutos"


def _link(config: MailConfig, caminho: str, parametro: str, token: str) -> str:
    # O token é urlsafe; quote() é uma segunda barreira caso o formato mude.
    return f"{config.base_url}{caminho}?{parametro}={quote(token, safe='')}"


def _html_transacional(titulo, saudacao, paragrafos, botao, link, aviso, rodape) -> str:
    """Layout responsivo de coluna única (max-width 560px) com tabelas e estilos inline."""
    e = html.escape
    corpo = "".join(
        f'<p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:{_COLOR_NIGHT};">{e(p)}</p>'
        for p in paragrafos
    )
    return (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="color-scheme" content="light">'
        f"<title>{e(titulo)}</title></head>"
        '<body style="margin:0;padding:0;background:#eef2f5;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="background:#eef2f5;"><tr><td align="center" style="padding:24px 12px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden;'
        'font-family:\'Segoe UI\',Arial,sans-serif;">'
        f'<tr><td style="background:{_COLOR_NIGHT};padding:20px 28px;border-bottom:4px solid {_COLOR_DAY};">'
        '<span style="font-size:12px;font-weight:700;letter-spacing:.14em;color:#ffffff;">'
        "SUPERSONIC · COMPRAS &amp; MANUTENÇÃO</span></td></tr>"
        '<tr><td style="padding:28px;">'
        f'<h1 style="margin:0 0 18px;font-size:22px;line-height:1.3;color:{_COLOR_NIGHT};">{e(titulo)}</h1>'
        f'<p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:{_COLOR_NIGHT};">{e(saudacao)}</p>'
        f"{corpo}"
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0;">'
        f'<tr><td style="background:{_COLOR_BUTTON};border-radius:8px;">'
        f'<a href="{e(link, quote=True)}" style="display:inline-block;padding:14px 28px;font-size:15px;'
        f'font-weight:700;color:#ffffff;text-decoration:none;">{e(botao)}</a></td></tr></table>'
        f'<p style="margin:0 0 16px;padding:12px 14px;font-size:14px;line-height:1.5;color:{_COLOR_NIGHT};'
        f'background:#e8f6fc;border-left:4px solid {_COLOR_DAY};border-radius:4px;">{aviso}</p>'
        '<p style="margin:0 0 6px;font-size:13px;line-height:1.5;color:#5c6f79;">'
        "Se o botão não funcionar, copie e cole este endereço no navegador:</p>"
        f'<p style="margin:0 0 20px;font-size:13px;line-height:1.5;word-break:break-all;">'
        f'<a href="{e(link, quote=True)}" style="color:{_COLOR_BUTTON};">{e(link)}</a></p>'
        f'<p style="margin:0;font-size:12px;line-height:1.5;color:#5c6f79;">{e(rodape)}</p>'
        "</td></tr></table></td></tr></table></body></html>"
    )


def renderizar_ativacao(nome: str, link: str, validade: timedelta) -> tuple[str, str]:
    """Retorna (texto_puro, html) do e-mail de verificação de conta."""
    prazo = rotulo_validade(validade)
    nome = sanitizar_cabecalho(nome) or "colaborador(a)"
    saudacao = f"Olá, {nome}."
    paragrafos = ["Recebemos um cadastro para o seu e-mail corporativo no Painel de Requisições Supersonic. "
                  "Confirme o endereço para ativar o seu acesso."]
    rodape = "Se você não solicitou este cadastro, ignore esta mensagem: nenhuma conta será ativada."
    texto = (
        f"{saudacao}\n\n{paragrafos[0]}\n\n"
        f"Ative sua conta acessando:\n{link}\n\n"
        f"Este link é válido por {prazo}.\n\n{rodape}\n"
    )
    pagina = _html_transacional(
        "Ative sua conta", saudacao, paragrafos, "Ativar minha conta", link,
        f"<strong>Validade:</strong> este link expira em {html.escape(prazo)}.", rodape,
    )
    return texto, pagina


def renderizar_recuperacao(nome: str, link: str, validade: timedelta) -> tuple[str, str]:
    """Retorna (texto_puro, html) do e-mail de redefinição de senha."""
    prazo = rotulo_validade(validade)
    nome = sanitizar_cabecalho(nome) or "colaborador(a)"
    saudacao = f"Olá, {nome}."
    paragrafos = ["Recebemos uma solicitação para redefinir a senha do seu acesso ao Painel de Requisições Supersonic."]
    rodape = ("Se você não fez esta solicitação, ignore esta mensagem: sua senha atual continua válida. "
              "Nunca compartilhe este link.")
    texto = (
        f"{saudacao}\n\n{paragrafos[0]}\n\n"
        f"Defina uma nova senha acessando:\n{link}\n\n"
        f"ATENÇÃO: o link expira em {prazo} e é de uso único (só pode ser usado uma vez).\n\n{rodape}\n"
    )
    pagina = _html_transacional(
        "Redefinição de senha", saudacao, paragrafos, "Redefinir minha senha", link,
        f"<strong>Atenção:</strong> este link expira em <strong>{html.escape(prazo)}</strong> "
        "e é de <strong>uso único</strong>.", rodape,
    )
    return texto, pagina


def construir_mensagem(destinatario: str, assunto: str, texto: str, corpo_html: str,
                       config: MailConfig) -> EmailMessage:
    """Monta multipart/alternative (text/plain + text/html) com cabeçalhos sanitizados."""
    para = validar_destinatario(destinatario)
    remetente = config.sender.strip()
    if _CONTROL_CHARS_RE.search(config.sender) or not re.fullmatch(r"[^@\s<>,;\"]+@[^@\s<>,;\"]+", remetente):
        raise ConfigurationError("MAIL_SENDER inválido.")

    mensagem = EmailMessage()
    mensagem["Subject"] = sanitizar_cabecalho(assunto)
    mensagem["From"] = formataddr((sanitizar_cabecalho(config.sender_name), remetente))
    mensagem["To"] = para
    mensagem["Date"] = formatdate(localtime=True)
    mensagem["Message-ID"] = make_msgid(domain=remetente.rsplit("@", 1)[1])
    mensagem["Auto-Submitted"] = "auto-generated"
    mensagem.set_content(texto)
    mensagem.add_alternative(corpo_html, subtype="html")
    return mensagem


def _registrar_falha(exc: Exception, config: MailConfig) -> None:
    """Log sem dados sensíveis: só o tipo, o código SMTP e o destino de infraestrutura."""
    codigo = getattr(exc, "smtp_code", None)
    logger.error(
        "[Auth Mail] Falha de transporte SMTP: %s%s (%s:%s, modo=%s)",
        type(exc).__name__, f" {codigo}" if codigo else "", config.host, config.port, config.security,
    )


def _entregar(mensagem: EmailMessage, destinatario: str, config: MailConfig,
              smtp_factory=None, smtp_ssl_factory=None) -> None:
    config.validate_delivery()
    remetente = config.sender.strip()
    try:
        if config.security == "ssl":
            conexao = (smtp_ssl_factory or smtplib.SMTP_SSL)(
                config.host, config.port, timeout=MAIL_TIMEOUT_SECONDS,
                context=ssl.create_default_context(),
            )
        else:
            conexao = (smtp_factory or smtplib.SMTP)(config.host, config.port, timeout=MAIL_TIMEOUT_SECONDS)
        with conexao as servidor:
            if config.security == "starttls":
                servidor.ehlo()
                servidor.starttls(context=ssl.create_default_context())
                servidor.ehlo()
            if config.username and config.password:
                servidor.login(config.username, config.password)
            servidor.send_message(mensagem, from_addr=remetente, to_addrs=[destinatario])
    except (smtplib.SMTPException, socket.timeout, OSError) as exc:
        _registrar_falha(exc, config)
        raise EmailTransportError("Falha ao entregar o e-mail.") from exc


def enviar_email(destinatario: str, assunto: str, texto: str, corpo_html: str,
                 config: MailConfig | None = None, smtp_factory=None, smtp_ssl_factory=None) -> bool:
    """Envia um e-mail multipart. Retorna False (sem rede) quando MAIL_ENABLED=false."""
    cfg = config or MailConfig.from_environment()
    para = validar_destinatario(destinatario)  # whitelist antes de qualquer disparo
    mensagem = construir_mensagem(para, assunto, texto, corpo_html, cfg)
    if not cfg.enabled:
        logger.warning("[Auth Mail][DEV] MAIL_ENABLED=false: envio ignorado para %s | %s",
                       para, mensagem["Subject"])
        return False
    _entregar(mensagem, para, cfg, smtp_factory, smtp_ssl_factory)
    return True


def _enviar_transacional(destinatario, assunto, texto, corpo_html, link, config,
                         smtp_factory, smtp_ssl_factory) -> bool:
    para = validar_destinatario(destinatario)
    mensagem = construir_mensagem(para, assunto, texto, corpo_html, config)
    if not config.enabled:
        # Somente desenvolvimento: sem SMTP, o link com o token vai ao console para uso manual.
        logger.warning("[Auth Mail][DEV] MAIL_ENABLED=false: envio ignorado para %s | %s | link: %s",
                       para, mensagem["Subject"], link)
        return False
    _entregar(mensagem, para, config, smtp_factory, smtp_ssl_factory)
    return True


def enviar_email_ativacao(destinatario: str, nome: str, token: str, validade: timedelta,
                          config: MailConfig | None = None, smtp_factory=None, smtp_ssl_factory=None) -> bool:
    """E-mail de verificação: {APP_BASE_URL}/auth/verificar?token={token}."""
    cfg = config or MailConfig.from_environment()
    link = _link(cfg, "/auth/verificar", "token", token)
    texto, pagina = renderizar_ativacao(nome, link, validade)
    return _enviar_transacional(destinatario, "Ative sua conta — Painel de Requisições Supersonic",
                                texto, pagina, link, cfg, smtp_factory, smtp_ssl_factory)


def enviar_email_recuperacao(destinatario: str, nome: str, token: str, validade: timedelta,
                             config: MailConfig | None = None, smtp_factory=None, smtp_ssl_factory=None) -> bool:
    """E-mail de recuperação: {APP_BASE_URL}/login?reset_token={token}."""
    cfg = config or MailConfig.from_environment()
    link = _link(cfg, "/login", "reset_token", token)
    texto, pagina = renderizar_recuperacao(nome, link, validade)
    return _enviar_transacional(destinatario, "Redefinição de senha — Painel de Requisições Supersonic",
                                texto, pagina, link, cfg, smtp_factory, smtp_ssl_factory)
