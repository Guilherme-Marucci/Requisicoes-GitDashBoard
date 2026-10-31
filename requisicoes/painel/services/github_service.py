"""Integração com a GitHub REST API (repositórios públicos) e cálculo das métricas do portfólio."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import requests
from flask import current_app

from painel.models import github as github_model

API = "https://api.github.com"
_USERNAME_RE = re.compile(r"^(?!-)(?!.*--)[A-Za-z0-9-]{1,39}(?<!-)$")
MAX_PAGES = 3  # até 300 repositórios por sincronização
ACTIVITY_DAYS = 30


class GitHubErro(Exception):
    """Erro tratado: carrega status HTTP sugerido, resultado para o log e mensagem segura."""
    status = 502
    resultado = "erro"

    def __init__(self, mensagem: str, rate_restante: int | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.rate_restante = rate_restante


class EntradaInvalida(GitHubErro):
    status = 400


class UsuarioNaoEncontrado(GitHubErro):
    status = 404
    resultado = "nao_encontrado"


class RateLimitExcedido(GitHubErro):
    status = 429
    resultado = "rate_limit"


class SincronizacaoRecente(GitHubErro):
    status = 429
    resultado = "rate_limit"


def extrair_username(entrada: str) -> str:
    """Aceita `usuario`, `@usuario`, `github.com/usuario` ou URL completa (inclusive de um repositório)."""
    bruto = (entrada or "").strip()
    if not bruto or len(bruto) > 200:
        raise EntradaInvalida("Informe o link ou o username do GitHub.")
    candidato = bruto.lstrip("@")
    if "/" in candidato or "." in candidato:
        url = candidato if "://" in candidato else f"https://{candidato}"
        partes = urlsplit(url)
        if (partes.hostname or "").lower() not in {"github.com", "www.github.com"}:
            raise EntradaInvalida("O link deve apontar para github.com.")
        segmentos = [s for s in partes.path.split("/") if s]
        if not segmentos:
            raise EntradaInvalida("O link não contém um username.")
        candidato = segmentos[0]
    if not _USERNAME_RE.fullmatch(candidato):
        raise EntradaInvalida("Username do GitHub inválido.")
    return candidato


def _headers() -> dict:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "painel-requisicoes"}
    token = current_app.config.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"  # nunca devolvido ao front-end
    return headers


def _request(path: str, params: dict | None = None) -> tuple[object, int | None]:
    """GET na API; traduz falhas de rede, 404 e rate limit em exceções tratadas."""
    try:
        resp = requests.get(API + path, params=params, headers=_headers(),
                            timeout=current_app.config.get("GITHUB_TIMEOUT", 10))
    except requests.Timeout:
        raise GitHubErro("A API do GitHub não respondeu a tempo. Tente novamente.") from None
    except requests.RequestException:
        raise GitHubErro("Não foi possível contatar a API do GitHub.") from None

    restante = resp.headers.get("X-RateLimit-Remaining")
    restante = int(restante) if restante and restante.isdigit() else None
    if resp.status_code == 404:
        raise UsuarioNaoEncontrado("Usuário do GitHub não encontrado.", restante)
    if resp.status_code in (403, 429):
        if restante == 0 or resp.headers.get("Retry-After") or "rate limit" in resp.text.lower():
            reset = resp.headers.get("X-RateLimit-Reset")
            quando = ""
            if reset and reset.isdigit():
                quando = " Novo limite às " + datetime.fromtimestamp(int(reset)).strftime("%H:%M") + "."
            raise RateLimitExcedido("Limite de requisições da API do GitHub atingido." + quando, 0)
        raise GitHubErro("O GitHub recusou a requisição.", restante)
    if resp.status_code >= 500:
        raise GitHubErro("O GitHub está temporariamente indisponível.", restante)
    if resp.status_code != 200:
        raise GitHubErro(f"Resposta inesperada do GitHub (HTTP {resp.status_code}).", restante)
    try:
        return resp.json(), restante
    except ValueError:
        raise GitHubErro("Resposta inválida do GitHub.", restante) from None


def _parse_dt(valor: str | None):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def coletar_repositorios(username: str) -> tuple[list[dict], int | None]:
    repos, restante = [], None
    for page in range(1, MAX_PAGES + 1):
        dados, restante = _request(f"/users/{username}/repos",
                                   {"per_page": 100, "page": page, "type": "owner", "sort": "pushed"})
        if not isinstance(dados, list):
            raise GitHubErro("Formato inesperado na lista de repositórios.", restante)
        repos.extend(dados)
        if len(dados) < 100:
            break
    return repos, restante


def coletar_atividade(username: str) -> tuple[dict[str, dict[str, int]], int | None]:
    """Commits públicos recentes por dia e por repositório (eventos Push; 1 requisição)."""
    eventos, restante = _request(f"/users/{username}/events/public", {"per_page": 100})
    por_dia: dict[str, int] = defaultdict(int)
    por_repo: dict[str, int] = defaultdict(int)
    limite = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=ACTIVITY_DAYS)
    for ev in eventos if isinstance(eventos, list) else []:
        if ev.get("type") != "PushEvent":
            continue
        quando = _parse_dt(ev.get("created_at"))
        if quando is None or quando < limite:
            continue
        payload = ev.get("payload") or {}
        n = payload.get("distinct_size", payload.get("size", 1)) or 1
        por_dia[quando.strftime("%Y-%m-%d")] += int(n)
        por_repo[(ev.get("repo") or {}).get("name", "")] += int(n)
    return {"dia": dict(por_dia), "repo": dict(por_repo)}, restante


def normalizar_repo(r: dict, commits_por_repo: dict[str, int]) -> dict:
    return {
        "id": int(r["id"]),
        "nome": str(r.get("name", ""))[:100],
        "full_name": str(r.get("full_name", ""))[:140],
        "descricao": (r.get("description") or "")[:500] or None,
        "url": str(r.get("html_url", ""))[:255],
        "linguagem": (r.get("language") or None),
        "estrelas": int(r.get("stargazers_count", 0)),
        "forks": int(r.get("forks_count", 0)),
        "issues_abertas": int(r.get("open_issues_count", 0)),
        "tamanho_kb": int(r.get("size", 0)),
        "commits_recentes": int(commits_por_repo.get(r.get("full_name", ""), 0)),
        "ultimo_push": _parse_dt(r.get("pushed_at")),
    }


def calcular_resumo(repos: list[dict], atividade: dict) -> dict:
    """Métricas para os gráficos e para o log de auditoria."""
    linguagens: Counter = Counter()
    estrelas_lang: Counter = Counter()
    for r in repos:
        lang = r["linguagem"] or "Outras"
        linguagens[lang] += 1
        estrelas_lang[lang] += r["estrelas"]
    hoje = datetime.now(timezone.utc).date()
    dias = [(hoje - timedelta(days=i)).isoformat() for i in range(ACTIVITY_DAYS - 1, -1, -1)]
    por_dia = atividade.get("dia", {})
    return {
        "totais": {
            "repos": len(repos),
            "estrelas": sum(r["estrelas"] for r in repos),
            "forks": sum(r["forks"] for r in repos),
            "issues": sum(r["issues_abertas"] for r in repos),
            "commits": sum(por_dia.values()),
        },
        "linguagens": [{"nome": n, "repos": c, "estrelas": estrelas_lang[n]} for n, c in linguagens.most_common(8)],
        "top_repos": [{"nome": r["nome"], "estrelas": r["estrelas"], "forks": r["forks"], "commits": r["commits_recentes"]}
                      for r in sorted(repos, key=lambda x: (x["estrelas"], x["forks"]), reverse=True)[:8]],
        "atividade": [{"data": d, "commits": por_dia.get(d, 0)} for d in dias],
        "periodo_atividade_dias": ACTIVITY_DAYS,
    }


def sincronizar(usuario: dict, entrada: str) -> dict:
    """Fluxo completo: valida entrada, coleta, persiste projetos e SEMPRE registra o log (sucesso ou falha)."""
    username = None
    try:
        username = extrair_username(entrada)
        intervalo = current_app.config.get("GITHUB_MIN_INTERVAL_SECONDS", 30)
        ultima = github_model.ultima_sincronizacao_segundos(usuario["id"], username)
        if ultima is not None and ultima < intervalo:
            raise SincronizacaoRecente(f"Aguarde {intervalo - ultima}s antes de sincronizar {username} novamente.")

        brutos, restante = coletar_repositorios(username)
        try:
            atividade, restante = coletar_atividade(username)
        except RateLimitExcedido:
            raise
        except GitHubErro:
            atividade = {"dia": {}, "repo": {}}  # atividade é opcional; repositórios já foram coletados
        repos = [normalizar_repo(r, atividade["repo"]) for r in brutos]
        resumo = calcular_resumo(repos, atividade)
        github_model.upsert_projetos(usuario["id"], username, repos)
        resumo["github_username"] = username
        log_id = github_model.registrar_log(usuario["id"], username, "ok", resumo,
                                            f"{len(repos)} repositórios sincronizados.", restante)
        return {"log_id": log_id, "username": username, "resumo": resumo, "rate_limit_restante": restante}
    except GitHubErro as exc:
        if username and not isinstance(exc, (EntradaInvalida, SincronizacaoRecente)):
            github_model.registrar_log(usuario["id"], username, exc.resultado, None, exc.mensagem, exc.rate_restante)
        raise
