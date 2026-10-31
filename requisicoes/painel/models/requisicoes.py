"""Queries de requisições: listagem filtrada, métricas, escrita e histórico."""

from __future__ import annotations

from painel.db import execute, fetch_all, fetch_one, transaction

_BASE = """
    FROM requisicoes q
    JOIN usuarios req ON req.id = q.requerente_id
    LEFT JOIN usuarios resp ON resp.id = q.responsavel_id
"""
_COLS = """
    q.id, q.codigo, q.titulo, q.descricao, q.setor, q.filial, q.item, q.quantidade, q.unidade,
    q.valor_estimado, q.prioridade, q.status, q.prazo, q.referencia, q.requerente_id,
    q.responsavel_id, q.criado_em, q.atualizado_em,
    req.nome AS requerente_nome, resp.nome AS responsavel_nome
"""
_ORDER = {"recentes": "q.criado_em DESC, q.id DESC", "antigas": "q.criado_em ASC, q.id ASC",
          "prazo": "q.prazo IS NULL, q.prazo ASC, q.id DESC", "prioridade": "q.prioridade DESC, q.criado_em DESC"}


def _where(filtros: dict, requerente_id: int | None):
    clauses, params = [], []
    if requerente_id is not None:
        clauses.append("q.requerente_id = %s")
        params.append(requerente_id)
    for campo in ("status", "setor", "filial", "prioridade"):
        if filtros.get(campo):
            clauses.append(f"q.{campo} = %s")
            params.append(filtros[campo])
    if filtros.get("q"):
        like = f"%{filtros['q']}%"
        clauses.append("(q.codigo LIKE %s OR q.titulo LIKE %s OR q.item LIKE %s OR q.referencia LIKE %s)")
        params.extend([like] * 4)
    if filtros.get("data_inicio"):
        clauses.append("q.criado_em >= %s")
        params.append(filtros["data_inicio"])
    if filtros.get("data_fim"):
        clauses.append("q.criado_em < DATE_ADD(%s, INTERVAL 1 DAY)")
        params.append(filtros["data_fim"])
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def listar(filtros: dict, requerente_id: int | None, pagina: int, por_pagina: int) -> tuple[list[dict], int]:
    where, params = _where(filtros, requerente_id)
    total = fetch_one("SELECT COUNT(*) AS n" + _BASE + where, params)["n"]
    order = _ORDER.get(filtros.get("ordenar"), _ORDER["recentes"])
    rows = fetch_all(
        f"SELECT {_COLS}{_BASE}{where} ORDER BY {order} LIMIT %s OFFSET %s",
        [*params, por_pagina, (pagina - 1) * por_pagina],
    )
    return rows, total


def metricas(filtros: dict, requerente_id: int | None) -> dict:
    where, params = _where(filtros, requerente_id)
    por_status = fetch_all("SELECT q.status AS chave, COUNT(*) AS n" + _BASE + where + " GROUP BY q.status", params)
    por_setor = fetch_all(
        "SELECT q.setor AS chave, COUNT(*) AS n" + _BASE + where + " GROUP BY q.setor ORDER BY n DESC LIMIT 8", params
    )
    totais = fetch_one(
        "SELECT COUNT(*) AS total, COALESCE(SUM(q.valor_estimado), 0) AS valor,"
        " SUM(q.prazo IS NOT NULL AND q.prazo < CURDATE() AND q.status NOT IN ('closed','canceled','rejected')) AS atrasadas"
        + _BASE + where,
        params,
    )
    return {
        "total": int(totais["total"] or 0),
        "valor_estimado": float(totais["valor"] or 0),
        "atrasadas": int(totais["atrasadas"] or 0),
        "por_status": {r["chave"]: int(r["n"]) for r in por_status},
        "por_setor": [{"setor": r["chave"], "total": int(r["n"])} for r in por_setor],
    }


def opcoes_filtro(requerente_id: int | None) -> dict:
    where, params = _where({}, requerente_id)
    return {
        "setores": [r["setor"] for r in fetch_all("SELECT DISTINCT q.setor" + _BASE + where + " ORDER BY q.setor", params)],
        "filiais": [r["filial"] for r in fetch_all("SELECT DISTINCT q.filial" + _BASE + where + " ORDER BY q.filial", params)],
    }


def buscar(req_id: int) -> dict | None:
    return fetch_one(f"SELECT {_COLS}{_BASE} WHERE q.id = %s", (req_id,))


def historico(req_id: int) -> list[dict]:
    return fetch_all(
        """SELECT h.acao, h.status_anterior, h.status_novo, h.comentario, h.criado_em, u.nome AS usuario_nome
             FROM requisicoes_historico h LEFT JOIN usuarios u ON u.id = h.usuario_id
            WHERE h.requisicao_id = %s ORDER BY h.criado_em DESC, h.id DESC""",
        (req_id,),
    )


def criar(dados: dict, requerente_id: int) -> tuple[int, str]:
    """Insere a requisição, gera o código sequencial anual e grava o primeiro evento do histórico."""
    with transaction():
        new_id = execute(
            """INSERT INTO requisicoes (codigo, titulo, descricao, setor, filial, item, quantidade, unidade,
                                        valor_estimado, prioridade, status, prazo, referencia, requerente_id)
               VALUES ('PENDENTE', %s, %s, %s, %s, %s, %s, %s, %s, %s, 'registered', %s, %s, %s)""",
            (dados["titulo"], dados["descricao"], dados["setor"], dados["filial"], dados["item"], dados["quantidade"],
             dados["unidade"], dados["valor_estimado"], dados["prioridade"], dados["prazo"], dados["referencia"], requerente_id),
        )
        codigo = f"REQ-{fetch_one('SELECT YEAR(CURDATE()) AS y')['y']}-{new_id:06d}"
        execute("UPDATE requisicoes SET codigo = %s WHERE id = %s", (codigo, new_id))
        execute(
            "INSERT INTO requisicoes_historico (requisicao_id, usuario_id, acao, status_novo) VALUES (%s, %s, 'criada', 'registered')",
            (new_id, requerente_id),
        )
    return new_id, codigo


def atualizar(req_id: int, dados: dict, usuario_id: int) -> None:
    with transaction():
        execute(
            """UPDATE requisicoes SET titulo=%s, descricao=%s, setor=%s, filial=%s, item=%s, quantidade=%s,
                      unidade=%s, valor_estimado=%s, prioridade=%s, prazo=%s, referencia=%s WHERE id=%s""",
            (dados["titulo"], dados["descricao"], dados["setor"], dados["filial"], dados["item"], dados["quantidade"],
             dados["unidade"], dados["valor_estimado"], dados["prioridade"], dados["prazo"], dados["referencia"], req_id),
        )
        execute("INSERT INTO requisicoes_historico (requisicao_id, usuario_id, acao) VALUES (%s, %s, 'editada')", (req_id, usuario_id))


def alterar_status(req_id: int, anterior: str, novo: str, usuario_id: int, comentario: str | None) -> None:
    with transaction():
        execute("UPDATE requisicoes SET status = %s, responsavel_id = %s WHERE id = %s", (novo, usuario_id, req_id))
        execute(
            """INSERT INTO requisicoes_historico (requisicao_id, usuario_id, acao, status_anterior, status_novo, comentario)
               VALUES (%s, %s, 'status', %s, %s, %s)""",
            (req_id, usuario_id, anterior, novo, comentario),
        )


def excluir(req_id: int) -> None:
    execute("DELETE FROM requisicoes WHERE id = %s", (req_id,))

