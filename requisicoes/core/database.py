"""SELECTs parametrizados no SQL Server, fora do ciclo HTTP e sem publicação automática."""

from contextlib import closing
import time

from core.config import SQLServerConfig
from core.consultas import obter_consulta


class DatabaseError(RuntimeError):
    """Falha sanitizada; mensagens do driver podem conter servidor, SQL ou credenciais."""


def _odbc_value(value: str) -> str:
    # Delimitação ODBC preserva ponto e vírgula e chaves em credenciais.
    return "{" + value.replace("}", "}}") + "}"


def _connection_string(config: SQLServerConfig, *, driver=None) -> str:
    parts = [
        f"DRIVER={_odbc_value(driver if driver is not None else config.driver)}",
        f"SERVER={_odbc_value(config.server)}",
        f"DATABASE={_odbc_value(config.database)}",
        f"Encrypt={config.encrypt}",
        f"TrustServerCertificate={config.trust_server_certificate}",
        "ApplicationIntent=ReadOnly",
    ]
    if config.auth == "windows":
        parts.append("Trusted_Connection=yes")
    else:
        parts.extend([f"UID={_odbc_value(config.username)}", f"PWD={_odbc_value(config.password)}"])
    return ";".join(parts) + ";"


def _obter_driver(pyodbc, config: SQLServerConfig) -> str:
    # Aceita diferenças de maiúsculas, mas conecta com o nome registrado no ODBC.
    driver = next((name for name in pyodbc.drivers() if name.casefold() == config.driver.casefold()), None)
    if driver is None:
        raise DatabaseError("Driver ODBC configurado não está instalado nesta máquina.")
    return driver


def conectar_sqlserver(config: SQLServerConfig = None, tentativas: int = 3, espera_segundos: float = 1.5):
    """Abre uma conexão com o SQL Server com retentativas automáticas para falhas transitórias (ex.: erros 4060, 18456)."""
    config = SQLServerConfig.from_environment() if config is None else config
    config.validate_connection()

    try:
        import pyodbc
    except ImportError:
        raise DatabaseError("Instale as dependências SQL Server deste projeto.") from None

    driver = _obter_driver(pyodbc, config)
    conn_str = _connection_string(config, driver=driver)

    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            # autocommit=True evita transações implícitas para consultas SELECT somente leitura
            return pyodbc.connect(conn_str, timeout=config.connect_timeout, autocommit=True)
        except pyodbc.Error as exc:
            ultimo_erro = exc
            if tentativa < tentativas:
                time.sleep(espera_segundos)

    msg = str(ultimo_erro)
    if config and config.password:
        msg = msg.replace(config.password, "******")
    raise DatabaseError(f"Falha ao consultar SQL Server: {msg}") from None


def consultar(nome: str, parametros=(), *, config=None, connection=None) -> list[dict]:
    """Executa apenas SELECT nomeado do catálogo, mantendo tipos nativos do driver.

    Permite reutilizar uma conexão aberta através do parâmetro `connection`, evitando
    múltiplos logins e reduzindo o tempo total de coleta em lote.
    """
    consulta = obter_consulta(nome)
    if not isinstance(parametros, (tuple, list)) or len(parametros) != len(consulta.parametros):
        raise ValueError("Parâmetros incompatíveis com a consulta homologada.")

    config = SQLServerConfig.from_environment() if config is None else config
    config.validate_connection()

    deve_fechar = connection is None
    conn = connection if connection is not None else conectar_sqlserver(config)

    try:
        conn.timeout = config.query_timeout
        with closing(conn.cursor()) as cursor:
            cursor.execute(consulta.sql, tuple(parametros))
            # Lotes com SET/DECLARE podem preceder o resultado final do SELECT.
            while not cursor.description:
                if not cursor.nextset():
                    raise DatabaseError("A consulta não retornou colunas.")
            columns = [column[0] for column in cursor.description]
            if any(not isinstance(name, str) or not name.strip() for name in columns):
                raise DatabaseError("O SELECT precisa nomear todas as colunas.")
            if len({name.casefold() for name in columns}) != len(columns):
                raise DatabaseError("O SELECT retornou aliases duplicados.")
            records = []
            while True:
                rows = cursor.fetchmany(min(500, config.max_rows + 1 - len(records)))
                if not rows:
                    return records
                records.extend(dict(zip(columns, row)) for row in rows)
                if len(records) > config.max_rows:
                    raise DatabaseError("Limite de linhas excedido. Revise o recorte homologado da consulta.")
    except Exception as exc:
        if isinstance(exc, DatabaseError):
            raise
        try:
            import pyodbc
            if isinstance(exc, pyodbc.Error):
                msg = str(exc)
                if config and config.password:
                    msg = msg.replace(config.password, "******")
                raise DatabaseError(f"Falha ao consultar SQL Server: {msg}") from None
        except ImportError:
            pass
        raise
    finally:
        if deve_fechar and conn is not None:
            try:
                conn.close()
            except Exception:
                pass
