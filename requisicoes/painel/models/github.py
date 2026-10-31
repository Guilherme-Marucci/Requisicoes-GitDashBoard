"""Queries do portfólio GitHub e do log de métricas."""

from __future__ import annotations

import json

from painel.db import execute, fetch_all, fetch_one, transaction


def upsert_projetos(usuario_id: int, username: str, repos: list[dict]) -> None:
    """Grava/atualiza os repositórios e remove os que deixaram de existir para o mesmo username."""
    with transaction():
        for r in repos:
            execute(
                """INSERT INTO github_projetos (usuario_id, github_username, github_repo_id, nome, full_name, descricao,
                                                url, linguagem, estrelas, forks, issues_abertas, tamanho_kb,
                                                commits_recentes, ultimo_push)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE github_username=VALUES(github_username), nome=VALUES(nome),
                       full_name=VALUES(full_name), descricao=VALUES(descricao), url=VALUES(url),
                       linguagem=VALUES(linguagem), estrelas=VALUES(estrelas), forks=VALUES(forks),
                       issues_abertas=VALUES(issues_abertas), tamanho_kb=VALUES(tamanho_kb),
                       commits_recentes=VALUES(commits_recentes), ultimo_push=VALUES(ultimo_push),
                       sincronizado_em=NOW()""",
                (usuario_id, username, r["id"], r["nome"], r["full_name"], r["descricao"], r["url"], r["linguagem"],
                 r["estrelas"], r["forks"], r["issues_abertas"], r["tamanho_kb"], r["commits_recentes"], r["ultimo_push"]),
            )
        ids = [r["id"] for r in repos]
        if ids:
            marks = ",".join(["%s"] * len(ids))
            execute(
                f"DELETE FROM github_projetos WHERE usuario_id=%s AND github_username=%s AND github_repo_id NOT IN ({marks})",
                (usuario_id, username, *ids),
            )
        else:
            execute("DELETE FROM github_projetos WHERE usuario_id=%s AND github_username=%s", (usuario_id, username))


def listar_projetos(usuario_id: int | None, username: str | None = None) -> list[dict]:
    clauses, params = [], []
    if usuario_id is not None:
        clauses.append("usuario_id = %s")
        params.append(usuario_id)
    if username:
        clauses.append("github_username = %s")
        params.append(username)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return fetch_all(
        "SELECT github_username, nome, full_name, descricao, url, linguagem, estrelas, forks, issues_abertas,"
        " tamanho_kb, commits_recentes, ultimo_push, sincronizado_em FROM github_projetos" + where +
        " ORDER BY estrelas DESC, nome", params)


def registrar_log(usuario_id: int | None, username: str, resultado: str, resumo: dict | None,
                  mensagem: str | None, rate_restante: int | None) -> int:
    totais = (resumo or {}).get("totais", {})
    return execute(
        """INSERT INTO github_metricas_log (usuario_id, github_username, resultado, total_repos, total_estrelas,
                                           total_forks, total_commits, resumo, mensagem, rate_limit_restante)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (usuario_id, username, resultado, totais.get("repos", 0), totais.get("estrelas", 0), totais.get("forks", 0),
         totais.get("commits", 0), json.dumps(resumo, ensure_ascii=False, default=str) if resumo else None,
         (mensagem or "")[:300] or None, rate_restante),
    )


def listar_logs(usuario_id: int | None, limite: int = 30) -> list[dict]:
    where, params = ("WHERE l.usuario_id = %s", [usuario_id]) if usuario_id is not None else ("", [])
    rows = fetch_all(
        f"""SELECT l.id, l.github_username, l.resultado, l.total_repos, l.total_estrelas, l.total_forks,
                   l.total_commits, l.mensagem, l.rate_limit_restante, l.criado_em, u.nome AS usuario_nome
              FROM github_metricas_log l LEFT JOIN usuarios u ON u.id = l.usuario_id
              {where} ORDER BY l.id DESC LIMIT %s""",
        [*params, limite],
    )
    return rows


def ultimo_log_ok(usuario_id: int, username: str) -> dict | None:
    row = fetch_one(
        """SELECT resumo, criado_em FROM github_metricas_log
            WHERE usuario_id=%s AND github_username=%s AND resultado='ok' ORDER BY id DESC LIMIT 1""",
        (usuario_id, username),
    )
    if row and row["resumo"]:
        row["resumo"] = json.loads(row["resumo"])
    return row


def ultima_sincronizacao_segundos(usuario_id: int, username: str) -> int | None:
    row = fetch_one(
        """SELECT TIMESTAMPDIFF(SECOND, MAX(criado_em), NOW()) AS s FROM github_metricas_log
            WHERE usuario_id=%s AND github_username=%s""",
        (usuario_id, username),
    )
    return None if not row or row["s"] is None else int(row["s"])

