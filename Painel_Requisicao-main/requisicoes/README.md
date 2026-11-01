# Painel de Requisições · MySQL + RBAC + GitHub + Tema Cyberpunk

Aplicação Full-Stack moderna em Python/Flask estruturada em camadas limpas, com persistência em MySQL local, autenticação RBAC com 3 perfis, integração com a GitHub REST API e interface Dark Neon Cyberpunk.

---

## 🚀 Arquitetura e Estrutura do Projeto

```
Painel_Requisicao-main/
└─ requisicoes/
   ├─ run.py                # Ponto de entrada da aplicação (http://127.0.0.1:5000)
   ├─ schema.sql            # Script DDL completo idempotente (MySQL / MariaDB)
   ├─ seed.py               # Migração e seed inicial de usuários
   ├─ gerar_seed.py         # Utilitário para geração de senhas e seed
   ├─ users_seed.json       # Credenciais iniciais com hash PBKDF2
   ├─ requirements.txt      # Dependências mínimas do projeto
   ├─ .env.example          # Exemplo de variáveis de ambiente
   ├─ painel/
   │  ├─ __init__.py        # Fábrica Flask, proteção CSRF e cabeçalhos CSP
   │  ├─ config.py          # Configurações e variáveis de ambiente
   │  ├─ db.py              # Camada de conexão e transações PyMySQL
   │  ├─ security.py        # RBAC, controle de sessão e tokens de segurança
   │  ├─ routes/            # Blueprints (Auth, Main, Requisições, GitHub, Config)
   │  ├─ services/          # Regras de negócio e integração GitHub API
   │  ├─ models/            # Queries SQL parametrizadas
   │  ├─ templates/         # Templates Jinja2
   │  └─ static/            # CSS Neon Cyberpunk e JS (Charts, Tema, App)
   └─ tests_painel/         # Testes automatizados (Unitários, Rotas, Concorrência e Idempotência)
```

---

## 🛠️ Como Executar

### 1. Pré-requisitos
* Python 3.10+
* MySQL 8.0+ ou MariaDB 10.4+

### 2. Instalação das dependências
```powershell
cd requisicoes
pip install -r requirements.txt
```

### 3. Configuração do Banco de Dados
Copie `.env.example` para `.env` se desejar customizar credenciais locais (padrão: `127.0.0.1:3306`, usuário `root`, senha vazia).

Execute o script de inicialização do schema e criação dos usuários de teste:
```powershell
python seed.py --init-db
```

### 4. Iniciar a Aplicação
```powershell
python run.py
```
Acesse: [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## 👥 Perfis de Acesso (RBAC)

| Perfil | Nível | Permissões |
| :--- | :---: | :--- |
| **usuario** | 10 | Cria e acompanha as próprias requisições; sincroniza seus próprios projetos GitHub. |
| **admin** | 50 | Visualiza todas as requisições, altera status e consulta histórico e logs globais. |
| **super-admin** | 90 | Acesso total: exclusão de requisições, reabertura de finalizadas e gestão de usuários. |

---

## 🎨 Temas Disponíveis

Na aba **Configurações do Usuário**, é possível selecionar dinamicamente entre as 6 variantes Dark Neon Cyberpunk sem recarregar a página:
* `dark` (padrão ciano neon)
* `dark-pink` (magenta neon)
* `dark-green` (verde neon)
* `dark-blue` (azul cobalto neon)
* `dark-red` (vermelho neon)
* `dark-purple` (roxo neon)

---

## 🧪 Testes Automatizados

Para executar todos os testes da suíte (unitários, rotas, regras de negócio, concorrência e idempotência):
```powershell
cd requisicoes
python -m unittest discover -s tests_painel -v
```
