# ▲ REQ//PAINEL · Gestão de Requisições & Portfólio GitHub

Painel corporativo e centralizador de requisições de compras e materiais com integração à GitHub REST API, arquitetura moderna em camadas limpas sobre **MySQL local**, controle de acesso baseado em papéis (**RBAC**) e identidade visual **Dark Neon Cyberpunk**.

---

## ⚡ Visão Geral e Recursos

* **Módulo de Requisições Completo (CRUD):**
  * Cadastro de requisições com validação rigorosa de payload e tipos no backend.
  * Acompanhamento por código anual gerado pelo servidor (`REQ-AAAA-NNNNNN`).
  * Histórico de auditoria e máquina de estados com operações atômicas condicionais (prevenção de *race conditions* concorrentes).
  * Filtros dinâmicos por situação, setor, filial, prioridade, período e busca textual.
* **Centralizador de Projetos GitHub & Métricas:**
  * Sincronização via link ou username com a GitHub REST API (tratando erros, status 404 e rate limits com auto-recuperação).
  * Painel com gráficos dinâmicos em Canvas (commits dos últimos 30 dias, linguagens, estrelas e forks por repositório).
  * Log de auditoria persistido no MySQL a cada sincronização.
  * Mecanismo de **idempotência no banco** para evitar duplicidade de chamadas por duplo clique.
* **Controle de Acesso RBAC com 3 Perfis:**
  * `usuario`: Criação e gestão das próprias requisições; sincronização dos próprios projetos GitHub.
  * `admin`: Visualização e edição ampla de requisições, alteração de status e consulta aos logs de todos os usuários.
  * `super-admin`: Exclusão definitiva de requisições, reabertura de chamados fechados e gestão de contas de usuários.
* **Identidade Visual Dark Neon Cyberpunk:**
  * Estilização vetorial em CSS moderno com temas dinâmicos via atributos `[data-theme]`:
    * `dark` (padrão)
    * `dark-pink`
    * `dark-green`
    * `dark-blue`
    * `dark-red`
    * `dark-purple`
  * Preferência salva no perfil do usuário no MySQL e com fallback em `localStorage`.

---

## 📁 Estrutura do Projeto

```text
Painel_Requisicao-main/
├── iniciar.bat             # Inicializador rápido para ambiente Windows
├── README.md               # Documentação geral do sistema
└── requisicoes/
    ├── iniciar.bat         # Inicializador local
    ├── run.py              # Ponto de entrada da aplicação (Flask / WSGI)
    ├── schema.sql          # DDL MySQL idempotente (tabelas, índices e constraints)
    ├── seed.py             # Script de inicialização e seed dos usuários
    ├── gerar_seed.py       # Utilitário para geração de senhas seguras
    ├── users_seed.json     # Seed inicial com hashes PBKDF2 (sem texto claro)
    ├── requirements.txt    # Dependências Python
    ├── .env.example        # Exemplo de configuração de ambiente
    ├── painel/
    │   ├── __init__.py     # Application Factory, CSRF e cabeçalhos de segurança (CSP)
    │   ├── config.py       # Configurações centralizadas
    │   ├── db.py           # Conexão PyMySQL e transações atômicas
    │   ├── security.py     # Matriz RBAC, sessões e proteção contra open redirect
    │   ├── routes/         # Blueprints (Auth, Main, Requisições, GitHub, Config)
    │   ├── services/       # Regras de negócio, validações e GitHub API
    │   ├── models/         # Consultas SQL parametrizadas (anti SQL-Injection)
    │   ├── templates/      # Templates Jinja2
    │   └── static/         # CSS Cyberpunk e scripts (Charts, Tema, App)
    └── tests_painel/       # Suíte de testes (Unitários, Rotas, Concorrência e Idempotência)
```

---

## 🚀 Como Iniciar

### 1. Pré-requisitos
* **Python 3.10+**
* **MySQL 8.0+** ou **MariaDB 10.4+** rodando localmente (porta padrão: `3306`)

### 2. Configuração Rápida
1. No diretório `requisicoes`, instale as dependências:
   ```powershell
   pip install -r requirements.txt
   ```
2. Inicialize o banco de dados e os usuários padrão:
   ```powershell
   python seed.py --init-db
   ```
   *(Executa o `schema.sql` e cadastra os perfis com senhas seguras hash)*.

3. Inicie o servidor:
   * **Opção 1:** Clique duas vezes no script `iniciar.bat` na raiz.
   * **Opção 2:** Execute via terminal dentro de `requisicoes`:
     ```powershell
     python run.py
     ```
   Acesse a interface no navegador: **[http://127.0.0.1:5000](http://127.0.0.1:5000)**.

---

## 🔑 Credenciais Iniciais de Teste

| Perfil | Usuário | Senha Temporária |
| :--- | :--- | :--- |
| **Super Admin** | `superadmin` | `u76MLt8MPr#55` |
| **Administrador** | `admin` | `se3t5D9uDd#46` |
| **Usuário** | `usuario` | `pQvkjVtAmn#53` |

> As senhas temporárias podem ser alteradas a qualquer momento na aba **Configurações do Usuário**.

---

## 🧪 Testes Automatizados

Para executar os testes de blindagem, rotas, regras de negócio e validação:
```powershell
cd requisicoes
python -m unittest discover -s tests_painel -v
```
