"""Testes do Painel. Unitários sempre rodam; os de integração exigem MySQL (variáveis PAINEL_DB_*).

    python -m unittest discover -s tests_painel -v
"""

import json
import os
import re
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from painel import create_app  # noqa: E402
from painel.config import DatabaseConfig  # noqa: E402
from painel.db import DatabaseUnavailable, connect  # noqa: E402
from painel.security import destino_seguro, pode  # noqa: E402
from painel.services import github_service as gh  # noqa: E402
from painel.services import requisicoes_service as rs  # noqa: E402
from seed import dividir_sql  # noqa: E402

TEST_DB = "painel_test"
CRED = {"super-admin": ("superadmin", None), "admin": ("admin", None), "usuario": ("usuario", None)}


class UnitTests(unittest.TestCase):
    def test_extrair_username(self):
        for entrada in ("octocat", "@octocat", "github.com/octocat", "https://github.com/octocat/Hello-World", "https://www.github.com/octocat?tab=x"):
            self.assertEqual(gh.extrair_username(entrada), "octocat")
        for ruim in ("", "a--b", "-abc", "https://gitlab.com/x", "has space", "x" * 40, "https://github.com/"):
            with self.assertRaises(gh.EntradaInvalida):
                gh.extrair_username(ruim)

    def test_validacao_requisicao(self):
        ok = {"titulo": "Compra de toner", "descricao": "Toner para impressora do setor", "item": "Toner", "filial": "Matriz",
              "setor": "ti", "quantidade": "2,5", "valor_estimado": "100,50", "prazo": (date.today() + timedelta(days=3)).isoformat()}
        limpo = rs.validar_requisicao(ok)
        self.assertEqual(str(limpo["quantidade"]), "2.500")
        self.assertEqual(str(limpo["valor_estimado"]), "100.50")
        with self.assertRaises(rs.ValidacaoErro) as ctx:
            rs.validar_requisicao({**ok, "titulo": "x", "setor": "xx", "quantidade": "-1", "prazo": "2001-01-01", "valor_estimado": "abc"})
        self.assertEqual(set(ctx.exception.erros), {"titulo", "setor", "quantidade", "prazo", "valor_estimado"})

    def test_transicoes(self):
        self.assertIsNone(rs.validar_mudanca_status("registered", "pending", "", super_admin=False))
        with self.assertRaises(rs.ValidacaoErro):
            rs.validar_mudanca_status("closed", "pending", "", super_admin=False)
        with self.assertRaises(rs.ValidacaoErro):
            rs.validar_mudanca_status("registered", "rejected", "", super_admin=False)  # exige motivo
        self.assertEqual(rs.validar_mudanca_status("closed", "pending", "reabrir", super_admin=True), "reabrir")

    def test_destino_seguro(self):
        self.assertEqual(destino_seguro("/projetos"), "/projetos")
        for ruim in ("https://evil.com", "//evil.com", "javascript:alert(1)", "/\\evil.com"):
            self.assertEqual(destino_seguro(ruim), "/")

    def test_matriz_rbac(self):
        u = {"role": "usuario"}; a = {"role": "admin"}; s = {"role": "super-admin"}
        self.assertFalse(pode(u, "requisicoes.ver_todas")); self.assertTrue(pode(a, "requisicoes.ver_todas"))
        self.assertFalse(pode(a, "requisicoes.excluir")); self.assertTrue(pode(s, "usuarios.gerenciar"))
        self.assertFalse(pode(None, "requisicoes.criar"))

    def test_dividir_sql_respeita_aspas(self):
        partes = dividir_sql("-- c;\nSELECT 'a;b'; /* x */ SELECT 2;")
        self.assertEqual(partes[0], "SELECT 'a;b'")
        self.assertEqual(len(partes), 2)

    def test_resumo(self):
        repos = [{"linguagem": "Python", "estrelas": 5, "forks": 1, "issues_abertas": 2, "nome": "a", "commits_recentes": 3},
                 {"linguagem": None, "estrelas": 1, "forks": 0, "issues_abertas": 0, "nome": "b", "commits_recentes": 0}]
        r = gh.calcular_resumo(repos, {"dia": {date.today().isoformat(): 4}, "repo": {}})
        self.assertEqual(r["totais"], {"repos": 2, "estrelas": 6, "forks": 1, "issues": 2, "commits": 4})
        self.assertEqual({l["nome"] for l in r["linguagens"]}, {"Python", "Outras"})
        self.assertEqual(len(r["atividade"]), 30)


def _db_config():
    cfg = DatabaseConfig.from_env()
    return DatabaseConfig(cfg.host, cfg.port, cfg.user, cfg.password, TEST_DB)


def _db_disponivel():
    try:
        connect(_db_config(), with_database=False).close()
        return True
    except DatabaseUnavailable:
        return False


@unittest.skipUnless(_db_disponivel(), "MySQL não disponível (defina PAINEL_DB_*)")
class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = _db_config()
        conn = connect(cfg, with_database=False)
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{TEST_DB}`")
            for sql in dividir_sql((BASE / "schema.sql").read_text(encoding="utf-8").replace("painel_requisicoes", TEST_DB)):
                cur.execute(sql)
        conn.close()
        cls.app = create_app({"DB": cfg, "TESTING": True, "GITHUB_MIN_INTERVAL_SECONDS": 0})
        # senhas de teste conhecidas, hash real (mesmo caminho do seed)
        from painel.services.auth_service import hash_senha
        from painel.models import usuarios
        cls.senhas = {"superadmin": "Super#Senha123", "admin": "Admin#Senha123", "usuario": "Usuario#Senha123"}
        seed = json.loads((BASE / "users_seed.json").read_text(encoding="utf-8"))["usuarios"]
        with cls.app.app_context():
            for u in seed:
                u = {**u, "senha_hash": hash_senha(cls.senhas[u["username"]])}
                usuarios.upsert_seed(u)

    @classmethod
    def tearDownClass(cls):
        conn = connect(_db_config(), with_database=False)
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{TEST_DB}`")
        conn.close()

    def novo_cliente(self, username=None):
        c = self.app.test_client()
        if username:
            self.login(c, username, self.senhas[username])
        return c

    def token(self, c):
        page = c.get("/login").get_data(as_text=True)
        return re.search(r'name="csrf-token" content="([^"]+)"', page).group(1)

    def login(self, c, username, senha):
        tok = self.token(c)
        return c.post("/login", data={"identificador": username, "senha": senha, "csrf_token": tok})

    def csrf(self, c):
        return {"X-CSRF-Token": self.token_logado(c)}

    def token_logado(self, c):
        page = c.get("/configuracoes").get_data(as_text=True)
        return re.search(r'name="csrf-token" content="([^"]+)"', page).group(1)

    # ------------------------------------------------------------------ auth
    def test_login_e_anonimo(self):
        c = self.app.test_client()
        self.assertEqual(c.get("/").status_code, 302)
        self.assertEqual(c.get("/api/requisicoes").status_code, 401)
        self.assertEqual(self.login(c, "admin", "errada").status_code, 401)
        r = self.login(c, "admin", self.senhas["admin"])
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.get("/").status_code, 200)

    def test_post_sem_csrf_e_rejeitado(self):
        c = self.novo_cliente("usuario")
        r = c.post("/api/preferencias/tema", json={"tema": "dark-pink"})
        self.assertEqual(r.status_code, 400)

    def test_nao_expoe_hash_nem_senha_no_html(self):
        c = self.novo_cliente("superadmin")
        for url in ("/", "/configuracoes", "/admin/usuarios", "/projetos"):
            html = c.get(url).get_data(as_text=True)
            self.assertNotIn("pbkdf2", html); self.assertNotIn(self.senhas["superadmin"], html)

    def test_bloqueio_por_tentativas(self):
        from painel.models import usuarios
        c = self.app.test_client()
        with self.app.app_context():
            from painel.db import execute
            execute("INSERT INTO usuarios (username,nome,email,senha_hash,role_id) VALUES ('lock','Lock','lock@x.local','x',1)")
        for _ in range(5):
            self.login(c, "lock", "qualquer")
        r = self.login(c, "lock", "qualquer")
        self.assertEqual(r.status_code, 401)
        self.assertIn("Muitas tentativas", r.get_data(as_text=True))

    # ------------------------------------------------------------------ RBAC
    def test_rbac_rotas(self):
        u, a, s = self.novo_cliente("usuario"), self.novo_cliente("admin"), self.novo_cliente("superadmin")
        self.assertEqual(u.get("/admin/usuarios").status_code, 403)
        self.assertEqual(a.get("/admin/usuarios").status_code, 403)
        self.assertEqual(s.get("/admin/usuarios").status_code, 200)

    def payload(self, **kw):
        base = {"titulo": "Compra de cabos", "descricao": "Cabos de rede para o setor de TI", "item": "Cabo UTP",
                "filial": "Matriz", "setor": "ti", "quantidade": "10", "prioridade": "alta"}
        base.update(kw)
        return base

    def test_crud_requisicoes_e_escopo(self):
        u, a, s = self.novo_cliente("usuario"), self.novo_cliente("admin"), self.novo_cliente("superadmin")
        # validação no back-end (422 com mensagens por campo)
        r = u.post("/api/requisicoes", json=self.payload(titulo="x", quantidade="0"), headers=self.csrf(u))
        self.assertEqual(r.status_code, 422)
        self.assertIn("titulo", r.get_json()["erro"]["campos"])
        # criação
        r = u.post("/api/requisicoes", json=self.payload(), headers=self.csrf(u))
        self.assertEqual(r.status_code, 201)
        req = r.get_json(); rid = req["id"]
        self.assertTrue(req["codigo"].startswith("REQ-")); self.assertEqual(req["status"], "registered")
        # escopo: usuário vê a sua; outro usuário (admin cria a dele) não é visto pelo usuário
        r2 = a.post("/api/requisicoes", json=self.payload(titulo="Requisição do admin"), headers=self.csrf(a))
        rid_admin = r2.get_json()["id"]
        ids_user = {i["id"] for i in u.get("/api/requisicoes").get_json()["itens"]}
        self.assertIn(rid, ids_user); self.assertNotIn(rid_admin, ids_user)
        self.assertEqual(u.get(f"/api/requisicoes/{rid_admin}").status_code, 404)
        ids_admin = {i["id"] for i in a.get("/api/requisicoes").get_json()["itens"]}
        self.assertTrue({rid, rid_admin} <= ids_admin)
        # filtros + métricas vindos do MySQL
        j = a.get("/api/requisicoes?status=registered&q=cabos").get_json()
        self.assertGreaterEqual(j["metricas"]["total"], 1)
        self.assertEqual(a.get("/api/requisicoes?status=%27%3BDROP%20TABLE%20x").status_code, 200)  # filtro inválido descartado
        # usuário não altera status; admin sim
        self.assertEqual(u.patch(f"/api/requisicoes/{rid}/status", json={"status": "approved"}, headers=self.csrf(u)).status_code, 403)
        r = a.patch(f"/api/requisicoes/{rid}/status", json={"status": "approved"}, headers=self.csrf(a))
        self.assertEqual(r.status_code, 200); self.assertEqual(r.get_json()["status"], "approved")
        self.assertEqual(a.patch(f"/api/requisicoes/{rid}/status", json={"status": "pending"}, headers=self.csrf(a)).status_code, 422)
        # dono não edita após sair de registered/pending; admin edita
        self.assertEqual(u.put(f"/api/requisicoes/{rid}", json=self.payload(), headers=self.csrf(u)).status_code, 403)
        self.assertEqual(a.put(f"/api/requisicoes/{rid}", json=self.payload(titulo="Titulo editado"), headers=self.csrf(a)).status_code, 200)
        hist = a.get(f"/api/requisicoes/{rid}").get_json()["historico"]
        self.assertEqual({h["acao"] for h in hist}, {"criada", "status", "editada"})
        # exclusão: só super-admin
        self.assertEqual(a.delete(f"/api/requisicoes/{rid}", headers=self.csrf(a)).status_code, 403)
        self.assertEqual(s.delete(f"/api/requisicoes/{rid}", headers=self.csrf(s)).status_code, 204)
        self.assertEqual(s.get(f"/api/requisicoes/{rid}").status_code, 404)

    def test_formulario_html(self):
        u = self.novo_cliente("usuario")
        html = u.get("/requisicoes/nova").get_data(as_text=True)
        self.assertIn("Cadastrar nova requisição", html)
        tok = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
        r = u.post("/requisicoes/nova", data={**self.payload(titulo="x"), "csrf_token": tok})
        self.assertEqual(r.status_code, 422)
        r = u.post("/requisicoes/nova", data={**self.payload(), "csrf_token": tok})
        self.assertEqual(r.status_code, 302)
        self.assertIn("REQ-", u.get(r.headers["Location"]).get_data(as_text=True))

    # ------------------------------------------------------------------ temas
    def test_tema_persistido(self):
        c = self.novo_cliente("usuario")
        self.assertEqual(c.post("/api/preferencias/tema", json={"tema": "nope"}, headers=self.csrf(c)).status_code, 422)
        for tema in ("dark-pink", "dark-green", "dark-blue", "dark-red", "dark-purple", "dark"):
            self.assertEqual(c.post("/api/preferencias/tema", json={"tema": tema}, headers=self.csrf(c)).status_code, 200)
        c.post("/api/preferencias/tema", json={"tema": "dark-red"}, headers=self.csrf(c))
        c2 = self.novo_cliente("usuario")  # nova sessão: tema vem do banco
        self.assertIn('data-theme="dark-red"', c2.get("/").get_data(as_text=True))

    # ------------------------------------------------------------------ GitHub
    def _fake_request(self, falha=None):
        agora = date.today().isoformat() + "T10:00:00Z"
        repos = [{"id": 1, "name": "alpha", "full_name": "octo/alpha", "html_url": "https://github.com/octo/alpha", "language": "Python",
                  "stargazers_count": 10, "forks_count": 2, "open_issues_count": 1, "size": 100, "pushed_at": agora, "description": "d"},
                 {"id": 2, "name": "beta", "full_name": "octo/beta", "html_url": "https://github.com/octo/beta", "language": "Go",
                  "stargazers_count": 3, "forks_count": 0, "open_issues_count": 0, "size": 5, "pushed_at": agora, "description": None}]
        eventos = [{"type": "PushEvent", "created_at": agora, "repo": {"name": "octo/alpha"}, "payload": {"distinct_size": 4}}]

        def fake(path, params=None):
            if falha:
                raise falha
            return (repos if path.endswith("/repos") else eventos), 57
        return fake

    def test_github_sincronizacao_e_logs(self):
        u, a = self.novo_cliente("usuario"), self.novo_cliente("admin")
        with mock.patch.object(gh, "_request", self._fake_request()):
            r = u.post("/api/github/sincronizar", json={"entrada": "https://github.com/octo/alpha"}, headers=self.csrf(u))
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        j = r.get_json()
        self.assertEqual(j["username"], "octo")
        self.assertEqual(j["resumo"]["totais"], {"repos": 2, "estrelas": 13, "forks": 2, "issues": 1, "commits": 4})
        self.assertEqual(len(j["projetos"]), 2)
        logs = u.get("/api/github/logs").get_json()["logs"]
        self.assertEqual(logs[0]["resultado"], "ok"); self.assertEqual(logs[0]["total_repos"], 2); self.assertEqual(logs[0]["rate_limit_restante"], 57)
        # estado persistido (sem chamar o GitHub)
        p = u.get("/api/github/projetos?username=octo").get_json()
        self.assertEqual(len(p["projetos"]), 2); self.assertEqual(p["resumo"]["totais"]["estrelas"], 13)
        # erros tratados geram log e status adequado
        with mock.patch.object(gh, "_request", self._fake_request(gh.RateLimitExcedido("limite", 0))):
            r = u.post("/api/github/sincronizar", json={"entrada": "octo"}, headers=self.csrf(u))
        self.assertEqual(r.status_code, 429)
        with mock.patch.object(gh, "_request", self._fake_request(gh.UsuarioNaoEncontrado("nf", 55))):
            r = u.post("/api/github/sincronizar", json={"entrada": "ghost-user"}, headers=self.csrf(u))
        self.assertEqual(r.status_code, 404)
        resultados = [l["resultado"] for l in u.get("/api/github/logs").get_json()["logs"]]
        self.assertEqual(resultados[:3], ["nao_encontrado", "rate_limit", "ok"])
        self.assertEqual(u.post("/api/github/sincronizar", json={"entrada": "http://evil.com/x"}, headers=self.csrf(u)).status_code, 400)
        # escopo dos logs: usuário não enxerga "todos"; admin enxerga
        self.assertEqual(u.get("/api/github/logs?escopo=todos").get_json()["escopo"], "proprios")
        self.assertEqual(a.get("/api/github/logs?escopo=todos").get_json()["escopo"], "todos")

    def test_github_http_real_tratamento(self):
        """Traduz respostas HTTP da API (404, rate limit, 5xx, timeout) sem acessar a rede."""
        import requests
        def resp(status, headers=None, body=None, text=""):
            m = mock.Mock(status_code=status, headers=headers or {}, text=text)
            m.json.return_value = body
            return m
        with self.app.test_request_context():
            with mock.patch("requests.get", return_value=resp(404)):
                with self.assertRaises(gh.UsuarioNaoEncontrado): gh._request("/users/x/repos")
            with mock.patch("requests.get", return_value=resp(403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1893456000"})):
                with self.assertRaises(gh.RateLimitExcedido) as c: gh._request("/users/x/repos")
                self.assertIn("Novo limite", c.exception.mensagem)
            with mock.patch("requests.get", return_value=resp(503)):
                with self.assertRaises(gh.GitHubErro): gh._request("/x")
            with mock.patch("requests.get", side_effect=requests.Timeout()):
                with self.assertRaises(gh.GitHubErro) as c: gh._request("/x")
                self.assertIn("a tempo", c.exception.mensagem)
            with mock.patch("requests.get", return_value=resp(200, {"X-RateLimit-Remaining": "42"}, [{"a": 1}])):
                self.assertEqual(gh._request("/x"), ([{"a": 1}], 42))


if __name__ == "__main__":
    unittest.main()

