"""Queries de usuários e perfis (camada de modelos: somente SQL, sem regras de negócio)."""

from __future__ import annotations

from painel.db import execute, fetch_all, fetch_one

_SELECT = """
    SELECT u.id, u.username, u.nome, u.email, u.senha_hash, u.ativo, u.tema,
           u.github_username, u.tentativas_falhas, u.bloqueado_ate, u.ultimo_login,
           r.nome AS role, r.nivel AS role_nivel
      FROM usuarios u JOIN roles r ON r.id = u.role_id
"""


def buscar_por_login(identificador: str) -> dict | None:
    return fetch_one(_SELECT + " WHERE u.username = %s OR u.email = %s LIMIT 1", (identificador, identificador))


def buscar_por_id(user_id: int) -> dict | None:
    return fetch_one(_SELECT + " WHERE u.id = %s", (user_id,))


def listar() -> list[dict]:
    return fetch_all(
        """SELECT u.id, u.username, u.nome, u.email, u.ativo, u.ultimo_login, u.tema, r.nome AS role
             FROM usuarios u JOIN roles r ON r.id = u.role_id ORDER BY r.nivel DESC, u.nome"""
    )


def registrar_falha(user_id: int, max_tentativas: int, bloqueio_minutos: int) -> None:
    execute(
        """UPDATE usuarios
              SET tentativas_falhas = tentativas_falhas + 1,
                  bloqueado_ate = IF(tentativas_falhas + 1 >= %s,
                                     DATE_ADD(NOW(), INTERVAL %s MINUTE), bloqueado_ate)
            WHERE id = %s""",
        (max_tentativas, bloqueio_minutos, user_id),
    )


def registrar_sucesso(user_id: int) -> None:
    execute(
        "UPDATE usuarios SET tentativas_falhas = 0, bloqueado_ate = NULL, ultimo_login = NOW() WHERE id = %s",
        (user_id,),
    )


def bloqueado(user_id: int) -> bool:
    row = fetch_one("SELECT (bloqueado_ate IS NOT NULL AND bloqueado_ate > NOW()) AS b FROM usuarios WHERE id = %s", (user_id,))
    return bool(row and row["b"])


def atualizar_tema(user_id: int, tema: str) -> None:
    execute("UPDATE usuarios SET tema = %s WHERE id = %s", (tema, user_id))


def atualizar_perfil(user_id: int, nome: str, github_username: str | None) -> None:
    execute("UPDATE usuarios SET nome = %s, github_username = %s WHERE id = %s", (nome, github_username, user_id))


def atualizar_senha(user_id: int, senha_hash: str) -> None:
    execute("UPDATE usuarios SET senha_hash = %s WHERE id = %s", (senha_hash, user_id))


def alterar_role(user_id: int, role_nome: str) -> int:
    with_role = fetch_one("SELECT id FROM roles WHERE nome = %s", (role_nome,))
    if not with_role:
        return 0
    execute("UPDATE usuarios SET role_id = %s WHERE id = %s", (with_role["id"], user_id))
    return 1


def alterar_ativo(user_id: int, ativo: bool) -> None:
    execute("UPDATE usuarios SET ativo = %s WHERE id = %s", (1 if ativo else 0, user_id))


def upsert_seed(usuario: dict) -> None:
    """Cria ou atualiza (por username) um usuário vindo do users_seed.json."""
    role = fetch_one("SELECT id FROM roles WHERE nome = %s", (usuario["role"],))
    if not role:
        raise ValueError(f"Role desconhecida: {usuario['role']}")
    execute(
        """INSERT INTO usuarios (username, nome, email, senha_hash, role_id, ativo, tema)
           VALUES (%s, %s, %s, %s, %s, 1, %s)
           ON DUPLICATE KEY UPDATE nome = VALUES(nome), email = VALUES(email),
                                   senha_hash = VALUES(senha_hash), role_id = VALUES(role_id), ativo = 1""",
        (usuario["username"], usuario["nome"], usuario["email"], usuario["senha_hash"], role["id"], usuario.get("tema", "dark")),
    )

