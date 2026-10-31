"""Configuração privada do coletor, do MySQL de autenticação, do SMTP e do Flask."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLSERVER_DRIVER = "ODBC Driver 13 for SQL Server"
# Timeout obrigatório de socket do SMTP (conexão e leituras), fixo para proteger os workers do Flask.
MAIL_TIMEOUT_SECONDS = 10
DEFAULT_MAIL_SENDER = "automacao@ssonic.com.br"
DEFAULT_MAIL_SENDER_NAME = "Painel de Requisições Supersonic"
_TRUE_VALUES = frozenset({"true", "1", "yes", "on", "sim"})
_FALSE_VALUES = frozenset({"false", "0", "no", "off", "nao", "não"})
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f\u2028\u2029]")
_EMAIL_ADDRESS_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_DATABASE_ALIASES = {
    "DB_SERVER": "SQLSERVER_SERVER",
    "DB_DATABASE": "SQLSERVER_DATABASE",
    "DB_USERNAME": "SQLSERVER_USERNAME",
    "DB_RD_PASSWORD": "SQLSERVER_PASSWORD",
    "DB_DRIVER": "SQLSERVER_DRIVER",
}


class ConfigurationError(ValueError):
    """Configuração ausente ou inválida, sem expor valores privados."""


def _database_names(values):
    """Aceita os nomes antigos sem misturar credenciais MySQL com SQL Server."""
    normalized = dict(values)
    for current, legacy in _DATABASE_ALIASES.items():
        if current not in normalized and legacy in normalized:
            normalized[current] = normalized[legacy]
    return normalized


def load_environment(path=None, environ=None) -> dict:
    """Lê somente o .env desta aplicação; variáveis do processo têm prioridade.

    Não altera os.environ e não expande ${...}, preservando senhas literalmente.
    O caminho explícito permite testar sem ler credenciais locais.
    """
    values = dotenv_values(path or PROJECT_ROOT / ".env", encoding="utf-8-sig", interpolate=False)
    # Normaliza cada fonte antes de mesclar: um alias no processo também vence o arquivo.
    return {**_database_names({key: value for key, value in values.items() if value is not None}),
            **_database_names(os.environ if environ is None else environ)}


def positive_integer(values, name, default) -> int:
    raw = values.get(name, str(default))
    if raw is None or str(raw).strip() == "":
        raw = str(default)
    try:
        result = int(str(raw).strip())
    except (ValueError, TypeError):
        raise ConfigurationError(f"{name} deve ser um inteiro positivo.") from None
    if result <= 0:
        raise ConfigurationError(f"{name} deve ser um inteiro positivo.")
    return result


def positive_float(values, name, default: float) -> float:
    raw = values.get(name, str(default))
    if raw is None or str(raw).strip() == "":
        raw = str(default)
    try:
        result = float(str(raw).strip())
    except (ValueError, TypeError):
        raise ConfigurationError(f"{name} deve ser um número positivo.") from None
    if result <= 0:
        raise ConfigurationError(f"{name} deve ser um número positivo.")
    return result


@dataclass(frozen=True)
class SQLServerConfig:
    enabled: bool
    server: str = field(repr=False)
    database: str = field(repr=False)
    username: str = field(repr=False)
    password: str = field(repr=False)
    driver: str = DEFAULT_SQLSERVER_DRIVER
    auth: str = "sql"
    connect_timeout: int = 10
    query_timeout: int = 30
    max_rows: int = 10000
    encrypt: str = "yes"
    trust_server_certificate: str = "no"

    @classmethod
    def from_environment(cls, values=None):
        """Valida parâmetros técnicos; credenciais só são exigidas ao consultar."""
        values = load_environment() if values is None else _database_names(values)
        enabled = values.get("SQLSERVER_ENABLED", "false").strip().lower()
        if enabled not in {"true", "false"}:
            raise ConfigurationError("SQLSERVER_ENABLED deve ser true ou false.")
        auth = values.get("SQLSERVER_AUTH", "sql").strip().lower()
        if auth not in {"sql", "windows"}:
            raise ConfigurationError("SQLSERVER_AUTH deve ser sql ou windows.")
        encrypt = values.get("SQLSERVER_ENCRYPT", "yes").strip().lower()
        if encrypt not in {"yes", "no", "true", "false"}:
            raise ConfigurationError("SQLSERVER_ENCRYPT deve ser yes ou no.")
        encrypt = "yes" if encrypt in {"yes", "true"} else "no"
        trust_cert = values.get("SQLSERVER_TRUST_SERVER_CERTIFICATE", values.get("SQLSERVER_TRUST_CERTIFICATE", "no")).strip().lower()
        if trust_cert not in {"yes", "no", "true", "false"}:
            raise ConfigurationError("SQLSERVER_TRUST_SERVER_CERTIFICATE deve ser yes ou no.")
        trust_cert = "yes" if trust_cert in {"yes", "true"} else "no"
        return cls(enabled=enabled == "true",
                   server=values.get("DB_SERVER", "").strip(),
                   database=values.get("DB_DATABASE", "").strip(),
                   username=values.get("DB_USERNAME", "").strip(),
                   password=values.get("DB_RD_PASSWORD", ""),
                   driver=values.get("DB_DRIVER", DEFAULT_SQLSERVER_DRIVER).strip(),
                   auth=auth,
                   connect_timeout=positive_integer(values, "SQLSERVER_CONNECT_TIMEOUT", 10),
                   query_timeout=positive_integer(values, "SQLSERVER_QUERY_TIMEOUT", 30),
                   max_rows=positive_integer(values, "SQLSERVER_MAX_ROWS", 10000),
                   encrypt=encrypt,
                   trust_server_certificate=trust_cert)

    def validate_connection(self):
        if not self.enabled:
            raise ConfigurationError("SQL Server desabilitado. Configure SQLSERVER_ENABLED para habilitar a leitura.")
        if not self.server or not self.database or not self.driver:
            raise ConfigurationError("Preencha DB_SERVER, DB_DATABASE e DB_DRIVER do SQL Server.")
        if self.auth == "sql" and (not self.username or not self.password):
            raise ConfigurationError("Preencha DB_USERNAME e DB_RD_PASSWORD da conta de leitura.")
        if self.auth not in {"sql", "windows"} or min(self.connect_timeout, self.query_timeout, self.max_rows) <= 0:
            raise ConfigurationError("Autenticação ou limites do SQL Server inválidos.")


@dataclass(frozen=True)
class MySQLAuthConfig:
    """Configuração do banco MySQL de autenticação (sistema_login / usuarios)."""

    host: str = field(repr=False)
    port: int = 3306
    database: str = field(default="sistema_login", repr=False)
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
    pool_size: int = 5
    connect_timeout: int = 5
    read_timeout: int = 5
    retry_attempts: int = 3
    retry_backoff_seconds: float = 0.5
    tv_email: str = "projetos@ssonic.com.br"
    tv_name: str = "TVREQ"

    @classmethod
    def from_environment(cls, values=None):
        values = load_environment() if values is None else dict(values)
        host = str(values.get("MYSQL_HOST") or values.get("DB_HOST") or "").strip()
        raw_port = str(values.get("MYSQL_PORT") or values.get("DB_PORT") or "").strip()
        port = positive_integer({"MYSQL_PORT": raw_port}, "MYSQL_PORT", 3306) if raw_port else 3306
        database = str(values.get("MYSQL_DATABASE") or values.get("DB_NAME") or "sistema_login").strip() or "sistema_login"
        username = str(values.get("MYSQL_USER") or values.get("DB_USER") or "").strip()
        password = str(values.get("MYSQL_PASSWORD") if "MYSQL_PASSWORD" in values else values.get("DB_PASSWORD") or "")
        tv_email = str(values.get("TV_LOGIN_EMAIL") or "projetos@ssonic.com.br").strip().lower() or "projetos@ssonic.com.br"
        tv_name = str(values.get("TV_LOGIN_NAME") or "TVREQ").strip() or "TVREQ"
        return cls(
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            pool_size=positive_integer(values, "MYSQL_POOL_SIZE", 5),
            connect_timeout=positive_integer(values, "MYSQL_CONNECT_TIMEOUT", 5),
            read_timeout=positive_integer(values, "MYSQL_READ_TIMEOUT", 5),
            retry_attempts=positive_integer(values, "MYSQL_RETRY_ATTEMPTS", 3),
            retry_backoff_seconds=positive_float(values, "MYSQL_RETRY_BACKOFF_SECONDS", 0.5),
            tv_email=tv_email,
            tv_name=tv_name,
        )

    def validate_connection(self):
        if not self.host or not self.database or not self.username:
            raise ConfigurationError(
                "Configuração MySQL de login incompleta (MYSQL_HOST/DB_HOST, MYSQL_DATABASE/DB_NAME, MYSQL_USER/DB_USER)."
            )


def boolean_value(values, name, default: bool) -> bool:
    """Lê booleano do ambiente; vazio usa o padrão e valor desconhecido é rejeitado (sem adivinhar)."""
    raw = values.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    text = str(raw).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    raise ConfigurationError(f"{name} deve ser true ou false.")


@dataclass(frozen=True)
class MailConfig:
    """Configuração do despacho SMTP transacional (ativação de conta e recuperação de senha).

    Padrões defensivos: envio desabilitado (modo desenvolvimento, sem rede) e STARTTLS exigido.
    O timeout de rede é uma constante (MAIL_TIMEOUT_SECONDS) e não pode ser ampliado por ambiente,
    para que uma indisponibilidade do SMTP nunca retenha workers do Flask por mais de 10 segundos.
    """

    enabled: bool = False
    host: str = field(default="", repr=False)
    port: int = 587
    use_tls: bool = True
    use_ssl: bool = False
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
    sender: str = DEFAULT_MAIL_SENDER
    sender_name: str = DEFAULT_MAIL_SENDER_NAME
    base_url: str = "http://localhost:5000"
    timeout: int = MAIL_TIMEOUT_SECONDS

    @property
    def security(self) -> str:
        """Modo de transporte efetivo: 'ssl' (porta 465), 'starttls' (porta 587) ou 'none'."""
        if self.use_ssl:
            return "ssl"
        return "starttls" if self.use_tls else "none"

    @classmethod
    def from_environment(cls, values=None):
        values = load_environment() if values is None else dict(values)
        enabled = boolean_value(values, "MAIL_ENABLED", False)

        raw_port = str(values.get("MAIL_PORT") or "").strip()
        port = positive_integer({"MAIL_PORT": raw_port}, "MAIL_PORT", 587) if raw_port else 587
        if port > 65535:
            raise ConfigurationError("MAIL_PORT deve estar entre 1 e 65535.")

        # A porta 465 implica SSL/TLS nativo, salvo configuração explícita em contrário.
        use_ssl = boolean_value(values, "MAIL_USE_SSL", port == 465)
        use_tls = boolean_value(values, "MAIL_USE_TLS", True)

        sender = str(values.get("MAIL_SENDER") or DEFAULT_MAIL_SENDER).strip()
        if not _EMAIL_ADDRESS_RE.fullmatch(sender):
            raise ConfigurationError("MAIL_SENDER deve ser um endereço de e-mail válido.")

        base_url = str(values.get("APP_BASE_URL") or "http://localhost:5000").strip().rstrip("/")
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or _CONTROL_RE.search(base_url):
            raise ConfigurationError("APP_BASE_URL deve ser uma URL http(s) válida.")

        sender_name = " ".join(_CONTROL_RE.sub(" ", str(values.get("MAIL_SENDER_NAME") or "")).split())
        return cls(
            enabled=enabled,
            host=str(values.get("MAIL_HOST") or "").strip(),
            port=port,
            use_tls=use_tls,
            use_ssl=use_ssl,
            username=str(values.get("MAIL_USERNAME") or "").strip(),
            password=str(values.get("MAIL_PASSWORD") or ""),
            sender=sender,
            sender_name=sender_name or DEFAULT_MAIL_SENDER_NAME,
            base_url=base_url,
        )

    def validate_delivery(self):
        """Exigida somente quando o envio real está habilitado; o modo mock dispensa SMTP."""
        if not self.host:
            raise ConfigurationError("Preencha MAIL_HOST para habilitar o envio de e-mails.")
        if bool(self.username) != bool(self.password):
            raise ConfigurationError("Preencha MAIL_USERNAME e MAIL_PASSWORD juntos.")
        if self.username and self.security == "none":
            # Nunca transmitir credenciais SMTP em texto claro.
            raise ConfigurationError("Credenciais SMTP exigem MAIL_USE_TLS=true ou MAIL_USE_SSL=true.")
