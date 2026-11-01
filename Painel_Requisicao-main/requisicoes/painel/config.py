"""Configuração do Painel: variáveis do processo > arquivo .env local > padrões de desenvolvimento."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"

TEMAS = ("dark", "dark-pink", "dark-green", "dark-blue", "dark-red", "dark-purple")


def _load_env() -> dict:
    file_values = dotenv_values(BASE_DIR / ".env", interpolate=False)
    merged = {k: v for k, v in file_values.items() if v is not None}
    merged.update(os.environ)
    return merged


def _secret_key(env: dict) -> str:
    """Chave de sessão: variável de ambiente ou arquivo privado gerado na primeira execução."""
    configured = (env.get("PAINEL_SECRET_KEY") or "").strip()
    if len(configured) >= 32:
        return configured
    path = STORAGE_DIR / ".painel_secret"
    if path.is_file():
        stored = path.read_text(encoding="utf-8").strip()
        if len(stored) >= 32:
            return stored
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_hex(32)
    path.write_text(generated, encoding="utf-8")
    return generated


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    user: str
    password: str
    name: str
    connect_timeout: int = 5

    @classmethod
    def from_env(cls, env: dict | None = None) -> "DatabaseConfig":
        env = env if env is not None else _load_env()
        return cls(
            host=env.get("PAINEL_DB_HOST", "127.0.0.1"),
            port=int(env.get("PAINEL_DB_PORT", "3306")),
            user=env.get("PAINEL_DB_USER", "root"),
            password=env.get("PAINEL_DB_PASSWORD", ""),
            name=env.get("PAINEL_DB_NAME", "painel_requisicoes"),
        )


def build_config(overrides: dict | None = None) -> dict:
    """Monta a configuração Flask; `overrides` permite testes sem tocar em segredos locais."""
    env = _load_env()
    config = {
        "SECRET_KEY": _secret_key(env),
        "DB": DatabaseConfig.from_env(env),
        "GITHUB_TOKEN": (env.get("GITHUB_TOKEN") or "").strip() or None,
        "GITHUB_TIMEOUT": 10,
        "SESSION_COOKIE_NAME": "painel_session",
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": env.get("PAINEL_COOKIE_SECURE", "false").lower() == "true",
        "MAX_CONTENT_LENGTH": 256 * 1024,
        "LOGIN_MAX_ATTEMPTS": 5,
        "LOGIN_LOCK_MINUTES": 10,
        "GITHUB_MIN_INTERVAL_SECONDS": 30,
    }
    if overrides:
        config.update(overrides)
    return config

