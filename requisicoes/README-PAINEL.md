# Painel de Requisições · MySQL + RBAC + GitHub + tema Cyberpunk

Aplicação Flask em camadas (`painel/`), com persistência em MySQL local. O código legado (`app.py`, `core/`, snapshots JSON) foi mantido apenas como referência; o novo ponto de entrada é `run.py`.

## Estrutura

```
requisicoes/
├─ schema.sql            DDL completo (roles, usuarios, requisicoes, historico, github_*)
├─ users_seed.json       usuários iniciais (somente hashes PBKDF2)
├─ seed.py               --init-db executa o schema.sql e carrega o seed
├─ gerar_seed.py         regera o seed com novas senhas temporárias
├─ run.py                entrada (http://127.0.0.1:5000)
└─ painel/
   ├─ __init__.py        fábrica da app, CSRF, cabeçalhos/CSP, handlers de erro
   ├─ config.py, db.py   configuração e acesso PyMySQL
   ├─ security.py        sessão, matriz de permissões (RBAC), CSRF, redirect seguro
   ├─ routes/            Blueprints: auth, main, requisicoes, github, config
   ├─ services/          regras de negócio: auth, validação de requisições, GitHub
   ├─ models/            queries SQL parametrizadas
   ├─ templates/         Jinja2
   └─ static/            css/cyber.css (temas), js/ (app, theme, charts, github)
```

## Executar

```powershell
cd requisicoes
pip install -r requirements.txt
# opcional: crie .env com PAINEL_DB_HOST/PORT/USER/PASSWORD/NAME e GITHUB_TOKEN
python seed.py --init-db
python run.py
```

Variáveis (`.env`, nunca versionado): `PAINEL_DB_HOST` (127.0.0.1), `PAINEL_DB_PORT` (3306), `PAINEL_DB_USER` (root), `PAINEL_DB_PASSWORD`, `PAINEL_DB_NAME` (painel_requisicoes), `PAINEL_SECRET_KEY` (opcional; senão é gerada em `storage/.painel_secret`), `GITHUB_TOKEN` (opcional; eleva o limite da API de 60 para 5000 req/h e nunca é enviado ao navegador).

## Permissões (RBAC)

| Permissão | usuario | admin | super-admin |
| --- | :-: | :-: | :-: |
| Criar requisição / ver e editar as próprias (enquanto Registrada/Pendente) | ✔ | ✔ | ✔ |
| Ver e editar todas; alterar status | | ✔ | ✔ |
| Excluir requisição; reabrir estados finais; gerir usuários | | | ✔ |
| Sincronizar projetos GitHub; ver os próprios logs | ✔ | ✔ | ✔ |
| Ver logs de todos os usuários | | ✔ | ✔ |

## Principais endpoints

`GET /` (listagem, filtros, métricas) · `GET|POST /requisicoes/nova` · `GET /requisicoes/<id>` · `POST /requisicoes/<id>/status|excluir` ·
API JSON: `GET|POST /api/requisicoes`, `GET|PUT|DELETE /api/requisicoes/<id>`, `PATCH /api/requisicoes/<id>/status` ·
`GET /projetos`, `POST /api/github/sincronizar`, `GET /api/github/projetos|logs` · `GET /configuracoes`, `POST /api/preferencias/tema` · `GET /admin/usuarios`.

Toda escrita exige token CSRF (`X-CSRF-Token` ou campo `csrf_token`).

## Testes

```powershell
python -m unittest discover -s tests_painel -v
```

Rotas/RBAC/CSRF/validação/GitHub rodam sem banco (modelos simulados). Os testes de integração com MySQL (`IntegrationTests`) são executados quando há um servidor acessível via `PAINEL_DB_*` e usam o banco descartável `painel_test`.

