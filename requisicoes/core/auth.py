"""Subsistema de autenticação, persistência de usuários e ciclo de vida de credenciais (AppSec).

Implementa:
- Validação estrita do domínio corporativo (@ssonic.com.br).
- Hashing PBKDF2-HMAC-SHA256 com salt de 32 bytes (secrets.token_bytes(32)) e >= 100.000 iterações
  no formato canônico `algoritmo$iteracoes$salt_hex$hash_hex`, validado com `hmac.compare_digest`.
- Pool de conexões MySQL thread-safe com ping/reconexão transparente e retentativa com backoff.
- Ciclo de vida de tokens (`secrets.token_urlsafe(48)`):
  * Token de ativação (`TOKEN_EMAIL` / `token_verificacao`): validade de 24 horas; ativa conta e anula token.
  * Token de recuperação (`reset_token` / `token_recuperacao`): validade estrita de 20 minutos e uso único.
- Mitigação de User Enumeration com tempo e payload uniformes.
- Isolamento de perfil do Painel TV (`projetos@ssonic.com.br` / `nome = TVREQ` / `tv@ssonic.com.br`).
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import importlib.util
import logging
from pathlib import Path
import queue
import re
import secrets
import threading
import time
from urllib.parse import urlsplit

import pymysql
from flask import session
from werkzeug.security import check_password_hash

from core import mail as mail_service
from core.config import ConfigurationError, MailConfig, MySQLAuthConfig

logger = logging.getLogger(__name__)

CORPORATE_DOMAIN = "@ssonic.com.br"
ROLE_TV = "tv"
ROLE_PAINEL = "painel"
DEFAULT_TV_EMAIL = "projetos@ssonic.com.br"
DEFAULT_TV_NAME = "TVREQ"
_TV_EMAIL_ALIASES = frozenset({"projetos@ssonic.com.br", "tv@ssonic.com.br"})

PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_HASH_NAME = "sha256"
PBKDF2_ITERATIONS = 100_000
PBKDF2_SALT_BYTES = 32
TOKEN_URLSAFE_BYTES = 48
ACTIVATION_TOKEN_TTL = timedelta(hours=24)
RESET_TOKEN_TTL = timedelta(minutes=20)
MIN_PASSWORD_LENGTH = 8

# Colunas reais da tabela sistema_login.usuarios (comentário de revisão do usuário) e aliases compatíveis:
# id, nome, email, senha_hash, criado_em, ATIVO, ADM, telefone, reset_token, token_expiracao,
# ACESSOS, telegram_id, ADM_WMS, ADM_SAC, ADM_CONT, DT_ALT, USUARIO_RODOPAR, EMAIL_VERIFICADO,
# TOKEN_EMAIL, TOKEN_EMAIL_EXPIRA, acesso_comp, login_comp, filial, ADM_MAN
_LOGIN_COLUMNS = ("email", "nome", "login_comp", "USUARIO_RODOPAR", "usuario")
_PASSWORD_COLUMNS = ("senha_hash", "senha", "password_hash", "password")
_EMAIL_COLUMNS = ("email", "e_mail", "login_comp", "usuario")
_NAME_COLUMNS = ("nome", "nome_completo", "name", "USUARIO_RODOPAR", "login_comp")

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_LOCAL_EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+$")
_SESSION_USER_KEY = "auth_user"
_SESSION_CSRF_KEY = "csrf_token"
_DUMMY_SALT = b"ssonic_constant_time_mitigation!"


class AuthError(Exception):
    """Erro base sanitizado do subsistema de autenticação."""


class CorporateDomainError(AuthError):
    """Domínio de e-mail fora do padrão corporativo @ssonic.com.br."""


class PasswordPolicyError(AuthError):
    """Senha fora dos requisitos mínimos de segurança."""


class InvalidCredentialsError(AuthError):
    """Credenciais inválidas, e-mail não verificado ou conta inativa."""


class TokenInvalidOrExpiredError(AuthError):
    """Token de verificação ou recuperação inválido, já utilizado ou expirado."""


class UserAlreadyExistsError(AuthError):
    """E-mail corporativo já registrado na base."""


class AuthServiceUnavailableError(AuthError):
    """Banco de dados de login indisponível ou falha operacional sanitizada."""


def _utc_now_naive() -> datetime:
    """Retorna DATETIME UTC sem tzinfo para compatibilidade direta com colunas DATETIME do MySQL."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _coerce_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str):
        cleaned = value.strip().replace("Z", "")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue
    return None


def normalizar_email_corporativo(email: str) -> str:
    """Aplica strip() e lower() e exige estritamente o domínio @ssonic.com.br."""
    if not isinstance(email, str):
        raise CorporateDomainError("Domínio corporativo não autorizado")
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise CorporateDomainError("Domínio corporativo não autorizado")
    local_part, sep, domain_part = normalized.partition("@")
    if not sep or f"@{domain_part}" != CORPORATE_DOMAIN or not local_part or not _LOCAL_EMAIL_RE.match(local_part):
        raise CorporateDomainError("Domínio corporativo não autorizado")
    return normalized


def validar_forca_senha(senha: str) -> None:
    """Garante senha não vazia e com comprimento mínimo seguro."""
    if not isinstance(senha, str) or len(senha) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"A senha deve conter no mínimo {MIN_PASSWORD_LENGTH} caracteres.")


def gerar_hash_senha(senha: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    """Gera hash PBKDF2-HMAC-SHA256 no formato canônico `algoritmo$iteracoes$salt_hex$hash_hex`."""
    if not isinstance(senha, str) or not senha:
        raise PasswordPolicyError("A senha não pode ser vazia.")
    effective_iterations = max(int(iterations), PBKDF2_ITERATIONS)
    salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        PBKDF2_HASH_NAME,
        senha.encode("utf-8"),
        salt,
        effective_iterations,
    )
    return f"{PBKDF2_ALGORITHM}${effective_iterations}${salt.hex()}${derived.hex()}"


def simular_verificacao_tempo_constante(plain_input: str = "") -> None:
    """Executa derivação PBKDF2 descartável para uniformizar tempo quando usuário não existe."""
    sample = (plain_input or "ssonic_dummy").encode("utf-8")
    derived = hashlib.pbkdf2_hmac(PBKDF2_HASH_NAME, sample, _DUMMY_SALT, PBKDF2_ITERATIONS)
    hmac.compare_digest(derived.hex(), "0" * 64)


def verificar_senha(stored_password, plain_password: str) -> bool:
    """Valida senha em tempo constante (`hmac.compare_digest`) priorizando o formato canônico PBKDF2."""
    if not isinstance(plain_password, str) or not plain_password:
        simular_verificacao_tempo_constante("")
        return False
    if stored_password is None:
        simular_verificacao_tempo_constante(plain_password)
        return False
    if isinstance(stored_password, bytes):
        try:
            stored = stored_password.decode("utf-8")
        except UnicodeDecodeError:
            return False
    elif isinstance(stored_password, str):
        stored = stored_password.strip()
    else:
        return False

    if not stored:
        simular_verificacao_tempo_constante(plain_password)
        return False

    # 1. Formato canônico: algoritmo$iteracoes$salt_hex$hash_hex (ex: pbkdf2_sha256$100000$<salt>$<hash>)
    if "$" in stored and not stored.startswith(("$2a$", "$2b$", "$2y$", "$argon2")):
        parts = stored.split("$")
        if len(parts) == 4 and parts[0].lower() in {PBKDF2_ALGORITHM, "sha256", "pbkdf2_hmac_sha256"}:
            try:
                iterations = int(parts[1])
                salt_bytes = bytes.fromhex(parts[2])
                expected_hex = parts[3].strip().lower()
            except ValueError:
                return False
            if iterations <= 0 or not salt_bytes or not expected_hex:
                return False
            calculated_hex = hashlib.pbkdf2_hmac(
                PBKDF2_HASH_NAME,
                plain_password.encode("utf-8"),
                salt_bytes,
                iterations,
            ).hex()
            return hmac.compare_digest(calculated_hex, expected_hex)

    # 2. Hashes Werkzeug / Flask pré-existentes (scrypt:... ou pbkdf2:...)
    if stored.startswith(("scrypt:", "pbkdf2:")):
        try:
            return check_password_hash(stored, plain_password)
        except ValueError:
            return False

    # 3. Hashes bcrypt ($2a$, $2b$, $2y$) pré-existentes na tabela usuarios
    if stored.startswith(("$2a$", "$2b$", "$2y$")):
        if importlib.util.find_spec("bcrypt") is None:
            raise AuthServiceUnavailableError("O formato de senha exige suporte a bcrypt no servidor.")
        import bcrypt  # type: ignore

        normalized_hash = (
            ("$2b$" + stored[4:]).encode("utf-8")
            if stored.startswith("$2y$")
            else stored.encode("utf-8")
        )
        try:
            return bool(bcrypt.checkpw(plain_password.encode("utf-8"), normalized_hash))
        except ValueError:
            return False

    if stored.startswith("$argon2"):
        raise AuthServiceUnavailableError("O formato de senha exige suporte a argon2 no servidor.")

    # 4. Hash SHA-256 hexadecimal legado
    if _SHA256_RE.match(stored):
        digest = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(stored.lower(), digest)

    # 5. Senha em texto puro legada (comparada com compare_digest)
    return hmac.compare_digest(stored, plain_password)


def gerar_token_seguro() -> str:
    """Gera token criptograficamente seguro com secrets.token_urlsafe(48)."""
    return secrets.token_urlsafe(TOKEN_URLSAFE_BYTES)


def resolve_secret_key(env_values: dict, storage_dir: Path) -> str:
    """Obtém AUTH_SECRET_KEY / FLASK_SECRET_KEY do ambiente ou persiste chave privada em storage."""
    configured = str(
        env_values.get("AUTH_SECRET_KEY")
        or env_values.get("FLASK_SECRET_KEY")
        or env_values.get("SECRET_KEY")
        or ""
    ).strip()
    if configured:
        return configured

    secret_file = Path(storage_dir) / ".flask_secret"
    try:
        if secret_file.is_file():
            existing = secret_file.read_text(encoding="utf-8").strip()
            if len(existing) >= 32:
                return existing
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        generated = secrets.token_hex(32)
        secret_file.write_text(generated, encoding="utf-8")
        return generated
    except OSError:
        return secrets.token_hex(32)


def definir_perfil(
    email: str,
    nome: str = "",
    tv_email: str = DEFAULT_TV_EMAIL,
    tv_name: str = DEFAULT_TV_NAME,
) -> str:
    """Identifica o perfil restrito da TV (`projetos@ssonic.com.br` / `nome = TVREQ`)."""
    norm_email = (email or "").strip().lower()
    norm_name = (nome or "").strip().upper()
    cfg_tv_email = (tv_email or DEFAULT_TV_EMAIL).strip().lower()
    cfg_tv_name = (tv_name or DEFAULT_TV_NAME).strip().upper()

    if norm_name and norm_name == cfg_tv_name:
        return ROLE_TV
    # Caso a conta de e-mail seja exclusiva da TV (ou projetos@ssonic.com.br sem outro nome administrativo)
    if norm_email == "tv@ssonic.com.br":
        return ROLE_TV
    if norm_email == cfg_tv_email and (not norm_name or norm_name in {cfg_tv_name, "PROJETOS", "PAINEL TV", "TV"}):
        return ROLE_TV
    return ROLE_PAINEL


class MySQLConnectionPool:
    """Pool thread-safe de conexões MySQL com reconexão automática (`ping`) e retentativas com backoff."""

    def __init__(self, config: MySQLAuthConfig, connector=None):
        self.config = config
        self._connector = connector or pymysql.connect
        self._pool: queue.LifoQueue = queue.LifoQueue(maxsize=max(1, config.pool_size))

    def _create_connection_with_retry(self):
        self.config.validate_connection()
        attempts = max(1, self.config.retry_attempts)
        delay = max(0.05, self.config.retry_backoff_seconds)
        last_exc = None
        for attempt in range(1, attempts + 1):
            try:
                return self._connector(
                    host=self.config.host,
                    port=self.config.port,
                    user=self.config.username,
                    password=self.config.password,
                    database=self.config.database,
                    connect_timeout=self.config.connect_timeout,
                    read_timeout=self.config.read_timeout,
                    autocommit=True,
                    charset="utf8mb4",
                    cursorclass=pymysql.cursors.DictCursor,
                )
            except (pymysql.MySQLError, OSError) as exc:
                last_exc = exc
                if attempt < attempts:
                    time.sleep(delay * (2 ** (attempt - 1)))
        raise AuthServiceUnavailableError(
            "Não foi possível conectar ao servidor de autenticação no momento."
        ) from last_exc

    @contextmanager
    def connection(self):
        conn = None
        try:
            while not self._pool.empty():
                try:
                    candidate = self._pool.get_nowait()
                except queue.Empty:
                    break
                try:
                    if hasattr(candidate, "ping"):
                        candidate.ping(reconnect=True)
                    conn = candidate
                    break
                except Exception:
                    self._safe_close(candidate)

            if conn is None:
                conn = self._create_connection_with_retry()

            yield conn

            try:
                self._pool.put_nowait(conn)
                conn = None
            except queue.Full:
                self._safe_close(conn)
                conn = None
        except Exception:
            if conn is not None:
                self._safe_close(conn)
            raise

    def execute_with_retry(self, callback):
        """Executa operação de banco com retentativa transparente em quedas transitórias de rede."""
        try:
            self.config.validate_connection()
        except ConfigurationError as exc:
            raise AuthServiceUnavailableError(
                "Serviço de autenticação não configurado no ambiente."
            ) from exc

        attempts = max(1, self.config.retry_attempts)
        delay = max(0.05, self.config.retry_backoff_seconds)
        last_exc = None
        for attempt in range(1, attempts + 1):
            try:
                with self.connection() as conn:
                    return callback(conn)
            except (AuthError, ConfigurationError):
                raise
            except pymysql.err.IntegrityError:
                raise
            except (pymysql.MySQLError, OSError) as exc:
                last_exc = exc
                if attempt < attempts:
                    time.sleep(delay * (2 ** (attempt - 1)))
        raise AuthServiceUnavailableError(
            "Não foi possível concluir a operação no servidor de login no momento."
        ) from last_exc

    @staticmethod
    def _safe_close(conn) -> None:
        try:
            conn.close()
        except Exception:
            pass


_POOLS_LOCK = threading.Lock()
_POOLS: dict[tuple, MySQLConnectionPool] = {}


def obter_pool_mysql(config: MySQLAuthConfig | None = None, connector=None) -> MySQLConnectionPool:
    """Retorna pool compartilhado para a configuração atual (ou instância dedicada quando connector customizado)."""
    cfg = config or MySQLAuthConfig.from_environment()
    if connector is not None:
        return MySQLConnectionPool(cfg, connector=connector)
    key = (cfg.host, cfg.port, cfg.database, cfg.username, cfg.pool_size)
    with _POOLS_LOCK:
        pool = _POOLS.get(key)
        if pool is None:
            pool = MySQLConnectionPool(cfg)
            _POOLS[key] = pool
        return pool


def _flag_ativa(val) -> bool:
    """Converte valores booleanos corporativos ('S'/'N' ou 1/0/True/False) para bool."""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    return str(val).strip().upper() in {"S", "SIM", "1", "TRUE", "Y"}


def _usuario_ativo(lower_row: dict) -> bool:
    if "inativo" in lower_row and lower_row["inativo"] is not None:
        if _flag_ativa(lower_row["inativo"]):
            return False
    for key in ("ativo", "active"):
        if key in lower_row and lower_row[key] is not None:
            return _flag_ativa(lower_row[key])
    if "status" in lower_row and lower_row["status"] is not None:
        st = str(lower_row["status"]).strip().lower()
        if st in {"0", "n", "inativo", "bloqueado", "cancelado", "desativado"}:
            return False
    return True


def _email_verificado(lower_row: dict) -> bool:
    for key in ("email_verificado", "verificado"):
        if key in lower_row and lower_row[key] is not None:
            return _flag_ativa(lower_row[key])
    # Se a coluna não estiver preenchida em registros antigos já ativos, respeita ATIVO
    return _usuario_ativo(lower_row)


def _executar_sql_adaptativo(cursor, sql_primary: str, params_primary: tuple, sql_fallback: str | None = None, params_fallback: tuple | None = None):
    """Executa SQL priorizando o schema corporativo (`TOKEN_EMAIL`/`ATIVO`) com fallback para colunas canônicas."""
    try:
        return cursor.execute(sql_primary, params_primary)
    except pymysql.err.OperationalError as exc:
        if sql_fallback and exc.args and exc.args[0] == 1054:
            return cursor.execute(sql_fallback, params_fallback if params_fallback is not None else params_primary)
        raise


def _buscar_usuario_por_identificador(cursor, ident_norm: str) -> dict | None:
    """Executa SELECT parametrizado na tabela usuarios por email ou nome/login_comp (ex: TVREQ)."""
    found_valid_column = False
    for col in _LOGIN_COLUMNS:
        try:
            cursor.execute(
                f"SELECT * FROM `usuarios` WHERE LOWER(TRIM(`{col}`)) = %s LIMIT 1",
                (ident_norm,),
            )
            found_valid_column = True
            row = cursor.fetchone()
            if row:
                return row
        except pymysql.err.OperationalError as exc:
            if exc.args and exc.args[0] == 1054:
                continue
            raise
    if not found_valid_column:
        raise AuthServiceUnavailableError("Estrutura da tabela de usuários incompatível com o login.")
    return None


def _buscar_usuario_por_coluna_token(cursor, token: str, candidate_columns: tuple[str, ...]) -> dict | None:
    """Busca usuário pelo token em colunas candidatas sem expor a estrutura em caso de coluna ausente."""
    found_col = False
    for col in candidate_columns:
        try:
            cursor.execute(
                f"SELECT * FROM `usuarios` WHERE `{col}` = %s LIMIT 1",
                (token,),
            )
            found_col = True
            row = cursor.fetchone()
            if row:
                return row
        except pymysql.err.OperationalError as exc:
            if exc.args and exc.args[0] == 1054:
                continue
            raise
    if not found_col:
        raise AuthServiceUnavailableError("Colunas de token ausentes na tabela usuarios.")
    return None


def _converter_falha_de_email(operacao):
    """Executa o envio convertendo falhas de configuração, whitelist e transporte em erros de auth."""
    try:
        return operacao()
    except mail_service.RecipientNotAllowedError as exc:
        raise CorporateDomainError("Domínio corporativo não autorizado") from exc
    except ConfigurationError as exc:
        logger.error("[Auth Mail] Configuração de e-mail inválida: %s", exc)
        raise AuthServiceUnavailableError("Serviço de e-mail não configurado no ambiente.") from exc
    except mail_service.EmailTransportError as exc:
        # O transporte já registrou o motivo de forma sanitizada.
        raise AuthServiceUnavailableError(
            "Não foi possível enviar o e-mail no momento. Tente novamente em instantes."
        ) from exc


def despachar_email_ativacao(destinatario: str, nome: str, token: str,
                             mail_config: MailConfig | None = None,
                             smtp_factory=None, smtp_ssl_factory=None) -> bool:
    """Envia o link de verificação (validade = ACTIVATION_TOKEN_TTL) ou apenas o registra em modo mock."""
    return _converter_falha_de_email(lambda: mail_service.enviar_email_ativacao(
        destinatario, nome, token, ACTIVATION_TOKEN_TTL,
        config=mail_config or MailConfig.from_environment(),
        smtp_factory=smtp_factory, smtp_ssl_factory=smtp_ssl_factory,
    ))


def despachar_email_recuperacao(destinatario: str, nome: str, token: str,
                                mail_config: MailConfig | None = None,
                                smtp_factory=None, smtp_ssl_factory=None) -> bool:
    """Envia o link de redefinição (validade = RESET_TOKEN_TTL, uso único) ou apenas o registra em modo mock."""
    return _converter_falha_de_email(lambda: mail_service.enviar_email_recuperacao(
        destinatario, nome, token, RESET_TOKEN_TTL,
        config=mail_config or MailConfig.from_environment(),
        smtp_factory=smtp_factory, smtp_ssl_factory=smtp_ssl_factory,
    ))


def _remover_cadastro_pendente(pool: MySQLConnectionPool, email: str, token: str) -> None:
    """Desfaz um cadastro ainda não ativado cujo e-mail de verificação não pôde ser entregue.

    Sem isso o colaborador ficaria bloqueado ("já possui cadastro") sem nunca receber o link.
    A condição pelo token e por ATIVO='N' garante que somente o registro recém-criado seja removido.
    """

    def _op(conn):
        with conn.cursor() as cursor:
            _executar_sql_adaptativo(
                cursor,
                "DELETE FROM `usuarios` WHERE LOWER(TRIM(`email`)) = %s AND `TOKEN_EMAIL` = %s AND `ATIVO` = 'N'",
                (email, token),
                "DELETE FROM `usuarios` WHERE LOWER(TRIM(`email`)) = %s AND `token_verificacao` = %s AND `ativo` = 0",
                (email, token),
            )

    try:
        pool.execute_with_retry(_op)
    except Exception as exc:
        logger.error("[Auth] Não foi possível desfazer o cadastro pendente (%s).", type(exc).__name__)


def _despachar_recuperacao_sem_propagar(sender_fn, email: str, nome: str, token: str, mail_config) -> None:
    """Falhas de e-mail na recuperação nunca chegam ao cliente: mudariam a resposta só para contas existentes."""
    try:
        sender_fn(email, nome, token, mail_config=mail_config)
    except Exception as exc:
        logger.error("[Auth Mail] Recuperação de senha não despachada (%s).", type(exc).__name__)


def registrar_usuario(
    email: str,
    senha: str,
    nome: str = "",
    telefone: str | None = None,
    config: MySQLAuthConfig | None = None,
    mail_config: MailConfig | None = None,
    connector=None,
    pool: MySQLConnectionPool | None = None,
    mail_sender=None,
    now: datetime | None = None,
) -> dict:
    """Registra novo usuário corporativo (@ssonic.com.br) com ATIVO='N'/0 e token de ativação de 24h."""
    email_norm = normalizar_email_corporativo(email)
    validar_forca_senha(senha)

    nome_limpo = (nome or "").strip() or email_norm.split("@")[0].upper()
    telefone_limpo = (telefone or "").strip() or None
    senha_hash = gerar_hash_senha(senha)
    token_ativacao = gerar_token_seguro()
    instante = (now or _utc_now_naive()).replace(tzinfo=None, microsecond=0)
    expira_em = instante + ACTIVATION_TOKEN_TTL

    db_pool = pool or obter_pool_mysql(config=config, connector=connector)

    def _op(conn):
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT `id` FROM `usuarios` WHERE LOWER(TRIM(`email`)) = %s LIMIT 1",
                (email_norm,),
            )
            if cursor.fetchone():
                raise UserAlreadyExistsError("Este e-mail corporativo já possui cadastro.")

            sql_corp = (
                "INSERT INTO `usuarios` "
                "(`nome`, `email`, `senha_hash`, `criado_em`, `ATIVO`, `EMAIL_VERIFICADO`, "
                "`telefone`, `TOKEN_EMAIL`, `TOKEN_EMAIL_EXPIRA`) "
                "VALUES (%s, %s, %s, %s, 'N', 'N', %s, %s, %s)"
            )
            params_corp = (
                nome_limpo[:120],
                email_norm,
                senha_hash,
                instante,
                telefone_limpo,
                token_ativacao,
                expira_em,
            )
            sql_canon = (
                "INSERT INTO `usuarios` "
                "(`email`, `senha_hash`, `ativo`, `email_verificado`, "
                "`token_verificacao`, `token_verificacao_expira`, `criado_em`) "
                "VALUES (%s, %s, 0, 0, %s, %s, %s)"
            )
            params_canon = (email_norm, senha_hash, token_ativacao, expira_em, instante)
            _executar_sql_adaptativo(cursor, sql_corp, params_corp, sql_canon, params_canon)

    try:
        db_pool.execute_with_retry(_op)
    except pymysql.err.IntegrityError as exc:
        raise UserAlreadyExistsError("Este e-mail corporativo já possui cadastro.") from exc

    # Sem entrega do link o cadastro não serve a ninguém: desfaz e propaga o 503 para o cliente tentar de novo.
    sender_fn = mail_sender or despachar_email_ativacao
    try:
        sender_fn(email_norm, nome_limpo, token_ativacao, mail_config=mail_config)
    except AuthError:
        _remover_cadastro_pendente(db_pool, email_norm, token_ativacao)
        raise

    return {
        "email": email_norm,
        "nome": nome_limpo,
        "ativo": False,
        "email_verificado": False,
        "token_verificacao": token_ativacao,
        "token_verificacao_expira": expira_em.isoformat(),
    }


def verificar_token_ativacao(
    token: str,
    config: MySQLAuthConfig | None = None,
    connector=None,
    pool: MySQLConnectionPool | None = None,
    now: datetime | None = None,
) -> dict:
    """Consome o token de ativação (24h), habilita `ATIVO='S'` e `EMAIL_VERIFICADO='S'` e anula o token."""
    token_limpo = (token or "").strip()
    if not token_limpo or len(token_limpo) < 16:
        raise TokenInvalidOrExpiredError("Token de verificação inválido ou expirado.")

    instante = (now or _utc_now_naive()).replace(tzinfo=None, microsecond=0)
    db_pool = pool or obter_pool_mysql(config=config, connector=connector)

    def _op(conn):
        with conn.cursor() as cursor:
            row = _buscar_usuario_por_coluna_token(
                cursor,
                token_limpo,
                ("TOKEN_EMAIL", "token_verificacao"),
            )
            if not row:
                raise TokenInvalidOrExpiredError("Token de verificação inválido ou já utilizado.")

            lower_row = {str(k).strip().lower(): v for k, v in row.items()}
            stored_token = str(
                lower_row.get("token_email") or lower_row.get("token_verificacao") or ""
            ).strip()
            if not stored_token or not hmac.compare_digest(stored_token, token_limpo):
                raise TokenInvalidOrExpiredError("Token de verificação inválido.")

            expira_raw = lower_row.get("token_email_expira") or lower_row.get("token_verificacao_expira")
            expira_dt = _coerce_datetime(expira_raw)
            if expira_dt is None or instante > expira_dt:
                raise TokenInvalidOrExpiredError("O prazo de 24 horas do link de verificação expirou.")

            user_id = lower_row.get("id")
            email_val = str(lower_row.get("email") or "").strip().lower()

            sql_corp = (
                "UPDATE `usuarios` "
                "SET `EMAIL_VERIFICADO` = 'S', `ATIVO` = 'S', "
                "`TOKEN_EMAIL` = NULL, `TOKEN_EMAIL_EXPIRA` = NULL "
                "WHERE `id` = %s"
            )
            sql_canon = (
                "UPDATE `usuarios` "
                "SET `email_verificado` = 1, `ativo` = 1, "
                "`token_verificacao` = NULL, `token_verificacao_expira` = NULL "
                "WHERE `id` = %s"
            )
            _executar_sql_adaptativo(cursor, sql_corp, (user_id,), sql_canon, (user_id,))
            return {"id": user_id, "email": email_val, "ativo": True, "email_verificado": True}

    return db_pool.execute_with_retry(_op)


def solicitar_recuperacao_senha(
    email: str,
    config: MySQLAuthConfig | None = None,
    mail_config: MailConfig | None = None,
    connector=None,
    pool: MySQLConnectionPool | None = None,
    mail_sender=None,
    now: datetime | None = None,
    despacho_assincrono: bool = True,
) -> dict:
    """Gera token de recuperação (20 min) com mitigação de User Enumeration (tempo e resposta uniformes)."""
    email_norm = normalizar_email_corporativo(email)
    instante = (now or _utc_now_naive()).replace(tzinfo=None, microsecond=0)
    expira_em = instante + RESET_TOKEN_TTL
    token_reset = gerar_token_seguro()

    db_pool = pool or obter_pool_mysql(config=config, connector=connector)

    def _op(conn):
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM `usuarios` WHERE LOWER(TRIM(`email`)) = %s LIMIT 1",
                (email_norm,),
            )
            row = cursor.fetchone()
            if not row:
                simular_verificacao_tempo_constante(email_norm)
                return None

            lower_row = {str(k).strip().lower(): v for k, v in row.items()}
            if not _usuario_ativo(lower_row):
                simular_verificacao_tempo_constante(email_norm)
                return None

            user_id = lower_row.get("id")
            nome_usuario = str(lower_row.get("nome") or email_norm.split("@")[0]).strip()
            sql_corp = (
                "UPDATE `usuarios` "
                "SET `reset_token` = %s, `token_expiracao` = %s "
                "WHERE `id` = %s"
            )
            sql_canon = (
                "UPDATE `usuarios` "
                "SET `token_recuperacao` = %s, `token_recuperacao_expira` = %s "
                "WHERE `id` = %s"
            )
            _executar_sql_adaptativo(
                cursor,
                sql_corp,
                (token_reset, expira_em, user_id),
                sql_canon,
                (token_reset, expira_em, user_id),
            )
            return {"nome": nome_usuario, "token": token_reset}

    resultado = db_pool.execute_with_retry(_op)

    if resultado is not None:
        sender_fn = mail_sender or despachar_email_recuperacao
        args = (sender_fn, email_norm, resultado["nome"], resultado["token"], mail_config)
        if despacho_assincrono:
            # Em segundo plano o tempo de resposta não depende do SMTP (que só é acionado para contas
            # existentes e ativas), fechando o canal de tempo para enumeração e liberando o worker.
            threading.Thread(
                target=_despachar_recuperacao_sem_propagar, args=args,
                name="auth-mail-recuperacao", daemon=True,
            ).start()
        else:
            _despachar_recuperacao_sem_propagar(*args)

    return {
        "mensagem": "Se o e-mail corporativo estiver cadastrado e ativo, as instruções de recuperação serão enviadas."
    }


def redefinir_senha_com_token(
    token: str,
    nova_senha: str,
    config: MySQLAuthConfig | None = None,
    connector=None,
    pool: MySQLConnectionPool | None = None,
    now: datetime | None = None,
) -> dict:
    """Valida o token de reset (20 min), atualiza `senha_hash` com PBKDF2-SHA256 e invalida o token."""
    token_limpo = (token or "").strip()
    if not token_limpo or len(token_limpo) < 16:
        raise TokenInvalidOrExpiredError("Token de recuperação inválido ou expirado.")
    validar_forca_senha(nova_senha)

    novo_hash = gerar_hash_senha(nova_senha)
    instante = (now or _utc_now_naive()).replace(tzinfo=None, microsecond=0)
    db_pool = pool or obter_pool_mysql(config=config, connector=connector)

    def _op(conn):
        with conn.cursor() as cursor:
            row = _buscar_usuario_por_coluna_token(
                cursor,
                token_limpo,
                ("reset_token", "token_recuperacao"),
            )
            if not row:
                raise TokenInvalidOrExpiredError("Token de recuperação inválido ou já utilizado.")

            lower_row = {str(k).strip().lower(): v for k, v in row.items()}
            stored_token = str(
                lower_row.get("reset_token") or lower_row.get("token_recuperacao") or ""
            ).strip()
            if not stored_token or not hmac.compare_digest(stored_token, token_limpo):
                raise TokenInvalidOrExpiredError("Token de recuperação inválido.")

            expira_raw = lower_row.get("token_expiracao") or lower_row.get("token_recuperacao_expira")
            expira_dt = _coerce_datetime(expira_raw)
            if expira_dt is None or instante > expira_dt:
                raise TokenInvalidOrExpiredError("O token de recuperação expirou (limite de 20 minutos).")

            user_id = lower_row.get("id")
            email_val = str(lower_row.get("email") or "").strip().lower()

            sql_corp = (
                "UPDATE `usuarios` "
                "SET `senha_hash` = %s, `reset_token` = NULL, `token_expiracao` = NULL "
                "WHERE `id` = %s"
            )
            sql_canon = (
                "UPDATE `usuarios` "
                "SET `senha_hash` = %s, `token_recuperacao` = NULL, `token_recuperacao_expira` = NULL "
                "WHERE `id` = %s"
            )
            _executar_sql_adaptativo(cursor, sql_corp, (novo_hash, user_id), sql_canon, (novo_hash, user_id))
            return {"id": user_id, "email": email_val}

    return db_pool.execute_with_retry(_op)


def autenticar_usuario_mysql(
    identificador: str,
    senha: str,
    config: MySQLAuthConfig | None = None,
    connector=None,
    pool: MySQLConnectionPool | None = None,
) -> dict:
    """Autentica credenciais no banco MySQL (sistema_login.usuarios) com pool e tempo constante."""
    ident_raw = (identificador or "").strip()
    if not ident_raw or not senha:
        simular_verificacao_tempo_constante(senha or "")
        raise InvalidCredentialsError("Informe seu e-mail corporativo e sua senha.")

    # Se contiver '@', exige domínio corporativo @ssonic.com.br; se for identificador curto (ex: TVREQ), normaliza.
    if "@" in ident_raw:
        ident_norm = normalizar_email_corporativo(ident_raw)
    else:
        ident_norm = ident_raw.lower()

    cfg = config or MySQLAuthConfig.from_environment()
    db_pool = pool or obter_pool_mysql(config=cfg, connector=connector)

    def _op(conn):
        with conn.cursor() as cursor:
            return _buscar_usuario_por_identificador(cursor, ident_norm)

    row = db_pool.execute_with_retry(_op)
    if not row:
        simular_verificacao_tempo_constante(senha)
        raise InvalidCredentialsError("E-mail ou senha inválidos.")

    lower_row = {str(k).strip().lower(): v for k, v in row.items()}

    stored_password = None
    for key in _PASSWORD_COLUMNS:
        if key in lower_row and lower_row[key] is not None:
            stored_password = lower_row[key]
            break

    senha_valida = verificar_senha(stored_password, senha)
    if not senha_valida:
        raise InvalidCredentialsError("E-mail ou senha inválidos.")

    if not _usuario_ativo(lower_row):
        raise InvalidCredentialsError("Esta conta está inativa ou pendente de verificação de e-mail.")

    if not _email_verificado(lower_row):
        raise InvalidCredentialsError("Verifique seu e-mail corporativo para ativar a conta antes de entrar.")

    email_val = ""
    for key in _EMAIL_COLUMNS:
        raw_val = lower_row.get(key)
        if raw_val is not None and str(raw_val).strip():
            email_val = str(raw_val).strip().lower()
            break
    if not email_val:
        email_val = ident_norm if "@" in ident_norm else f"{ident_norm}{CORPORATE_DOMAIN}"

    if "@" in email_val:
        email_val = normalizar_email_corporativo(email_val)

    name_val = ""
    for key in _NAME_COLUMNS:
        raw_name = lower_row.get(key)
        if raw_name is not None and str(raw_name).strip():
            name_val = str(raw_name).strip()
            break
    if not name_val:
        name_val = email_val.split("@")[0]

    role = definir_perfil(
        email=email_val,
        nome=name_val,
        tv_email=cfg.tv_email,
        tv_name=cfg.tv_name,
    )
    return {
        "id": lower_row.get("id"),
        "email": email_val,
        "name": name_val[:60],
        "role": role,
        "adm": _flag_ativa(lower_row.get("adm")),
        "filial": str(lower_row.get("filial") or "").strip() or None,
    }


def destino_seguro(next_url: str | None, role: str) -> str:
    """Resolve URL pós-login bloqueando redirecionamentos externos e respeitando o perfil."""
    default_target = "/tv" if role == ROLE_TV else "/"
    candidate = (next_url or "").strip()
    if not candidate:
        return default_target

    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc or not candidate.startswith("/") or candidate.startswith("//"):
        return default_target

    clean_path = parsed.path or "/"
    if clean_path in {"/login", "/login.html", "/logout"}:
        return default_target

    if role == ROLE_TV:
        if clean_path in {"/tv", "/tv/grafico"}:
            return candidate
        return "/tv"

    return candidate


def obter_usuario_sessao() -> dict | None:
    """Retorna os dados do usuário autenticado na sessão atual ou None."""
    user = session.get(_SESSION_USER_KEY)
    if not isinstance(user, dict):
        return None
    role = user.get("role")
    email = user.get("email")
    if role not in {ROLE_TV, ROLE_PAINEL} or not isinstance(email, str) or not email.strip():
        return None
    return {
        "email": email.strip().lower(),
        "name": str(user.get("name") or email.split("@")[0])[:60],
        "role": role,
    }


def iniciar_sessao_usuario(user: dict) -> None:
    """Registra sessão limpa após login válido; sessões da TV permanecem persistentes."""
    session.clear()
    role = user.get("role") if user.get("role") in {ROLE_TV, ROLE_PAINEL} else ROLE_PAINEL
    session[_SESSION_USER_KEY] = {
        "email": str(user.get("email", "")).strip().lower(),
        "name": str(user.get("name", "")).strip()[:60],
        "role": role,
    }
    session[_SESSION_CSRF_KEY] = secrets.token_hex(24)
    session.permanent = role == ROLE_TV


def encerrar_sessao_usuario() -> None:
    """Limpa integralmente a sessão autenticada."""
    session.clear()


def gerar_csrf_token() -> str:
    """Garante e retorna um token anti-CSRF vinculado à sessão."""
    token = session.get(_SESSION_CSRF_KEY)
    if not isinstance(token, str) or len(token) < 32:
        token = secrets.token_hex(24)
        session[_SESSION_CSRF_KEY] = token
    return token


def validar_csrf_token(enviado: str | None) -> bool:
    """Compara o token enviado pelo formulário com o token armazenado na sessão."""
    esperado = session.get(_SESSION_CSRF_KEY)
    if not isinstance(esperado, str) or not esperado or not isinstance(enviado, str) or not enviado:
        return False
    return hmac.compare_digest(esperado, enviado)
