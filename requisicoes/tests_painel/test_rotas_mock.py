"""Testes de rotas/templates/RBAC/CSRF com a camada de modelos simulada (rodam sem MySQL)."""

import re
import sys
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from painel import create_app  # noqa: E402
from painel.services.auth_service import hash_senha  # noqa: E402

SENHA = "Teste#Senha123"
HASH = hash_senha(SENHA)


def user(uid, role, username):
    return {"id": uid, "username": username, "nome": username.title(), "email": f"{username}@x.l", "senha_hash": HASH,
            "ativo": 1, "tema": "dark-green", "github_username": None, "tentativas_falhas": 0, "bloqueado_ate": None,
            "ultimo_login": None, "role": role, "role_nivel": 10}


USERS = {1: user(1, "super-admin", "superadmin"), 2: user(2, "admin", "admin"), 3: user(3, "usuario", "usuario")}
BY_NAME = {u["username"]: u for u in USERS.values()}


def req(rid=1, dono=3, status="registered"):
    return {"id": rid, "codigo": f"REQ-2026-{rid:06d}", "titulo": "Compra de cabos", "descricao": "Cabos de rede", "setor": "ti",
            "filial": "Matriz", "item": "Cabo", "quantidade": Decimal("10.000"), "unidade": "UN", "valor_estimado": Decimal("150.00"),
            "prioridade": "alta", "status": status, "prazo": date.today() + timedelta(days=5), "referencia": None,
            "requerente_id": dono, "responsavel_id": None, "criado_em": datetime.now(), "atualizado_em": datetime.now(),
            "requerente_nome": "Usuario", "responsavel_nome": None}


METRICAS = {"total": 1, "valor_estimado": 150.0, "atrasadas": 0, "por_status": {"registered": 1}, "por_setor": [{"setor": "ti", "total": 1}]}


class RotasTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True})
        p = []
        for alvo, fn in {
            "painel.models.usuarios.buscar_por_login": lambda i: BY_NAME.get(i),
            "painel.models.usuarios.buscar_por_id": lambda i: USERS.get(i),
            "painel.models.usuarios.bloqueado": lambda i: False,
            "painel.models.usuarios.registrar_sucesso": lambda i: None,
            "painel.models.usuarios.registrar_falha": lambda *a: None,
            "painel.models.usuarios.listar": lambda: [{**u, "ultimo_login": None} for u in USERS.values()],
            "painel.models.usuarios.atualizar_tema": mock.Mock(),
            "painel.models.requisicoes.listar": lambda f, esc, pg, pp: ([req()], 1),
            "painel.models.requisicoes.metricas": lambda f, esc: METRICAS,
            "painel.models.requisicoes.opcoes_filtro": lambda esc: {"setores": ["ti"], "filiais": ["Matriz"]},
            "painel.models.requisicoes.buscar": lambda rid: req(rid) if rid == 1 else (req(rid, dono=2) if rid == 2 else None),
            "painel.models.requisicoes.historico": lambda rid: [{"acao": "criada", "status_anterior": None, "status_novo": "registered",
                                                                "comentario": None, "criado_em": datetime.now(), "usuario_nome": "Usuario"}],
            "painel.models.requisicoes.criar": lambda d, uid: (9, "REQ-2026-000009"),
            "painel.models.requisicoes.alterar_status": mock.Mock(),
            "painel.models.requisicoes.excluir": mock.Mock(),
            "painel.models.github.listar_logs": lambda uid, limite=30: [],
            "painel.models.github.listar_projetos": lambda uid, username=None: [],
            "painel.models.github.ultimo_log_ok": lambda uid, u: None,
        }.items():
            patcher = mock.patch(alvo, fn)
            patcher.start(); p.append(patcher); self.addCleanup(patcher.stop)

    def cliente(self, username=None):
        c = self.app.test_client()
        tok = re.search(r'name="csrf-token" content="([^"]+)"', c.get("/login").get_data(as_text=True)).group(1)
        if username:
            r = c.post("/login", data={"identificador": username, "senha": SENHA, "csrf_token": tok})
            self.assertEqual(r.status_code, 302)
        return c

    def tok(self, c):
        return re.search(r'name="csrf-token" content="([^"]+)"', c.get("/configuracoes").get_data(as_text=True)).group(1)

    def test_login_logout_csrf(self):
        c = self.app.test_client()
        self.assertEqual(c.post("/login", data={"identificador": "admin", "senha": SENHA}).status_code, 400)  # sem CSRF
        c = self.cliente()
        tok = re.search(r'name="csrf-token" content="([^"]+)"', c.get("/login").get_data(as_text=True)).group(1)
        r = c.post("/login", data={"identificador": "admin", "senha": "errada", "csrf_token": tok})
        self.assertEqual(r.status_code, 401); self.assertIn("Usuário ou senha inválidos.", r.get_data(as_text=True))
        r = c.post("/login", data={"identificador": "ghost", "senha": "x", "csrf_token": tok})
        self.assertIn("Usuário ou senha inválidos.", r.get_data(as_text=True))  # mesma mensagem: sem enumeração
        c = self.cliente("admin")
        self.assertEqual(c.post("/logout", data={"csrf_token": self.tok(c)}).status_code, 302)
        self.assertEqual(c.get("/").status_code, 302)

    def test_paginas_renderizam_e_nao_vazam_segredos(self):
        for nome in ("superadmin", "admin", "usuario"):
            c = self.cliente(nome)
            for url in ("/", "/requisicoes/nova", "/requisicoes/1", "/projetos", "/configuracoes"):
                r = c.get(url); html = r.get_data(as_text=True)
                self.assertEqual(r.status_code, 200, (nome, url))
                self.assertNotIn("pbkdf2", html); self.assertNotIn(SENHA, html)
                self.assertIn('data-theme="dark-green"', html)
            self.assertIn("REQ-2026-000001", c.get("/").get_data(as_text=True))
            self.assertIn("Cadastrar nova requisição", c.get("/").get_data(as_text=True))
        # menu: só super-admin vê Usuários; só quem tem permissão vê o resto
        self.assertIn("Usuários", self.cliente("superadmin").get("/").get_data(as_text=True))
        self.assertNotIn("☰ Usuários", self.cliente("admin").get("/").get_data(as_text=True))

    def test_rbac(self):
        self.assertEqual(self.cliente("usuario").get("/admin/usuarios").status_code, 403)
        self.assertEqual(self.cliente("admin").get("/admin/usuarios").status_code, 403)
        self.assertEqual(self.cliente("superadmin").get("/admin/usuarios").status_code, 200)
        u = self.cliente("usuario")
        self.assertEqual(u.get("/requisicoes/2").status_code, 404)  # de terceiros
        self.assertEqual(u.post("/requisicoes/1/status",
                                data={"status": "approved", "csrf_token": self.tok(u)}).status_code, 403)
        self.assertEqual(u.delete("/api/requisicoes/1", headers={"X-CSRF-Token": self.tok(u)}).status_code, 403)
        a = self.cliente("admin")
        self.assertEqual(a.delete("/api/requisicoes/1", headers={"X-CSRF-Token": self.tok(a)}).status_code, 403)
        s = self.cliente("superadmin")
        self.assertEqual(s.delete("/api/requisicoes/1", headers={"X-CSRF-Token": self.tok(s)}).status_code, 204)
        self.assertEqual(self.app.test_client().get("/api/requisicoes").status_code, 401)

    def test_api_validacao_422_e_criacao(self):
        u = self.cliente("usuario"); h = {"X-CSRF-Token": self.tok(u)}
        r = u.post("/api/requisicoes", json={"titulo": "x"}, headers=h)
        self.assertEqual(r.status_code, 422); self.assertIn("descricao", r.get_json()["erro"]["campos"])
        r = u.post("/api/requisicoes", json={"titulo": "x"})  # sem CSRF
        self.assertEqual(r.status_code, 400)
        html = u.post("/requisicoes/nova", data={"titulo": "x", "csrf_token": self.tok(u)}).get_data(as_text=True)
        self.assertIn("field__erro", html)

    def test_tema(self):
        c = self.cliente("usuario"); h = {"X-CSRF-Token": self.tok(c)}
        self.assertEqual(c.post("/api/preferencias/tema", json={"tema": "dark-pink"}, headers=h).status_code, 200)
        self.assertEqual(c.post("/api/preferencias/tema", json={"tema": "light"}, headers=h).status_code, 422)
        html = c.get("/configuracoes").get_data(as_text=True)
        for t in ("dark", "dark-pink", "dark-green", "dark-blue", "dark-red", "dark-purple"):
            self.assertIn(f'data-theme-choice="{t}"', html)

    def test_cabecalhos(self):
        r = self.app.test_client().get("/login")
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertNotIn("<script>", r.get_data(as_text=True))  # sem JS inline (CSP)


if __name__ == "__main__":
    unittest.main()
