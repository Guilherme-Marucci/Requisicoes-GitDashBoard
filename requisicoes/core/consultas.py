"""Catálogo interno de SELECTs revisados; nunca recebe SQL da página ou do .env."""
#    Registra explicitamente os três novos arquivos sem interpolação de strings:

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType


class ConsultaNaoHomologada(ValueError):
    """Nome ausente do catálogo de consultas autorizadas."""


@dataclass(frozen=True)
class Consulta:
    sql: str
    parametros: tuple[str, ...] = ()


def _ler_sql(nome_arquivo: str) -> str:
    caminho = Path(__file__).with_name(nome_arquivo)
    if not caminho.exists():
        return ""
    return caminho.read_text(encoding="utf-8-sig").strip()


from core.rankings import SQL_FUNCIONARIOS, SQL_TOP_ITENS, SQL_TOP_REQUERENTES, SQL_TOP_SETORES


CONSULTAS = MappingProxyType({
    "diagnostico":      Consulta("SELECT CAST(1 AS int) AS conexao_ok"),
    "requisicoes":      Consulta(_ler_sql("database.sql")),
    "tv_situac":         Consulta(_ler_sql("TV_situac.sql")),
    "tv_pedidos":        Consulta(_ler_sql("TV_pedidos.sql")),
    "tv_nf":             Consulta(_ler_sql("TV_nf.sql")),
    "top_requerentes":   Consulta(SQL_TOP_REQUERENTES),
    "top_setores":       Consulta(SQL_TOP_SETORES),
    "top_itens":         Consulta(SQL_TOP_ITENS),
    "funcionarios":      Consulta(SQL_FUNCIONARIOS),
})


def obter_consulta(nome: str) -> Consulta:
    try:
        consulta = CONSULTAS[nome]
        if not consulta.sql:
            raise ConsultaNaoHomologada(f"O arquivo SQL da consulta '{nome}' está vazio.")
        return consulta
    except KeyError:
        raise ConsultaNaoHomologada(f"SELECT '{nome}' não homologado no catálogo interno.") from None
