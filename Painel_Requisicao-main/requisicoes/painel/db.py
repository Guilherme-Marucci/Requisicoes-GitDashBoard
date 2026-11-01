"""Acesso ao MySQL via PyMySQL: uma conexão por requisição, consultas sempre parametrizadas."""

from __future__ import annotations

from contextlib import contextmanager

import pymysql
from flask import current_app, g
from pymysql.cursors import DictCursor


class DatabaseUnavailable(RuntimeError):
    """MySQL inacessível; a mensagem é segura para exibir (sem host, usuário ou senha)."""


def connect(config, *, with_database: bool = True):
    try:
        return pymysql.connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            database=config.name if with_database else None,
            charset="utf8mb4",
            cursorclass=DictCursor,
            connect_timeout=config.connect_timeout,
            autocommit=True,
        )
    except pymysql.MySQLError as exc:
        raise DatabaseUnavailable("Banco de dados indisponível. Verifique o MySQL local e o schema.sql.") from exc


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DB"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def fetch_all(sql: str, params=()) -> list[dict]:
    with get_db().cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def fetch_one(sql: str, params=()) -> dict | None:
    with get_db().cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def execute(sql: str, params=()) -> int:
    """Executa INSERT/UPDATE/DELETE e devolve o último id gerado."""
    with get_db().cursor() as cur:
        cur.execute(sql, params)
        return cur.lastrowid


@contextmanager
def transaction():
    """Agrupa várias escritas de forma atômica."""
    conn = get_db()
    conn.autocommit(False)
    try:
        yield
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit(True)

