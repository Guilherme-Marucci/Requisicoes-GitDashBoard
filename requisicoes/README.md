   # Painel de Requisições — Supersonic

Dashboard corporativo e monitoramento em tempo real do ciclo de vida das requisições de compras e materiais integradas ao ERP corporativo (SQL Server).

O sistema provê visibilidade operacional através de interfaces responsivas para desktop e telas dedicadas para **TVs corporativas** (Painel TV), com atualização contínua, tolerância a oscilações de rede e zero impacto na performance do banco de dados.

---

## 1. Arquitetura do Sistema

A aplicação foi projetada sob o princípio de **alta disponibilidade e isolamento de processos**, desacoplando a camada de visualização Web da extração de dados no ERP:

```
┌─────────────────────────┐
│   ERP SQL Server        │  (Leitura estrita: SELECT ... WITH(NOLOCK))
└───────────┬─────────────┘
            │  Execução autônoma via sincronizar.py
            ▼
┌─────────────────────────┐
│   Snapshots JSON        │  (storage/requisicoes.json, storage/tv_situac.json)
│   (Escrita atômica)     │  Tolerância a falhas e cache local persistente
└───────────┬─────────────┘
            │  Leitura desacoplada sem conexão ao banco
            ▼
┌─────────────────────────┐
│   Backend Flask         │  (app.py / APIs REST)
│   (Modo somente-leitura)│  Endpoints: /api/requisicoes, /api/tv/dataset, /api/rankings
└───────────┬─────────────┘
            │  Consumo assíncrono via fetch()
            ▼
┌─────────────────────────┐
│   Interface do Usuário  │  - Painel Desktop: Kanban, Setores e Rankings
│   (HTML5 / CSS / JS)    │  - Painel TV: Resumo, Tabela Priorizada e Gráficos
└─────────────────────────┘
```

### Princípios Arquiteturais Canônicos

1. **Desacoplamento Total (SELECT → JSON Privado → Flask → Página):**
   Navegar pelo painel, alternar abas, aplicar filtros de busca ou recarregar a página no navegador **nunca dispara consultas ao SQL Server**.
2. **Leitura Segura no ERP:**
   Todas as consultas SQL no banco de produção utilizam a diretiva `WITH(NOLOCK)` e janelas temporais otimizadas (`DATATU >= DATEADD(month, -3, ...)`), garantindo tempo de execução em milissegundos sem retenção de locks ou impacto nas operações concorrentes do ERP.
3. **Resiliência e Tolerância a Falhas:**
   Caso o banco de dados sofra instabilidades temporárias ou oscilações de rede, a camada de sincronização retém o último snapshot válido íntegro. O painel continua operando sem interrupção de tela, indicando visualmente o estado e a data/hora da última coleta no cabeçalho.
4. **Identidade Visual Supersonic:**
   Tokens semânticos de cores para temas claro e escuro definidos em `static/CSS/supersonic.css`, com suporte nativo a contraste, ícones Lucide locais e responsividade para dispositivos móveis e grandes telas de TV.

---

## 2. Estrutura de Diretórios

A estrutura do projeto foi padronizada e consolidada na pasta principal `requisicoes/`, com os scripts de inicialização acessíveis diretamente na raiz:

```
Painel_Requisicao/
├── .github/
│   └── workflows/
├── .gitignore                      # Regras globais (cache, .env, snapshots json)
├── AGENTS.md                       # Diretrizes de desenvolvimento do projeto
├── MEMORY.md                       # Registro histórico de decisões técnicas
├── README.md                       # Documentação principal do repositório
├── iniciar.bat                     # Inicializador do serviço em 1 clique
├── powershell.bat                  # Inicializador auxiliar do PowerShell
└── requisicoes/                    # Diretório da aplicação
    ├── components/                 # Fragmentos de layout Jinja/HTML (sidebar, topbar, footer)
    ├── core/                       # Módulos centrais de negócio e banco de dados
    │   ├── config.py               # Carregamento e validação de configurações / .env
    │   ├── consultas.py            # Catálogo interno de consultas SQL homologadas
    │   ├── database.py             # Pool de conexão e retentativa com SQL Server
    │   ├── database.sql            # Query principal de requisições
    │   ├── erp.py                  # Mapeamento e canonização de dados do ERP
    │   ├── rankings.py             # Consultas e cálculos analíticos de rankings
    │   ├── requisicoes.py          # Validação, leitura e publicação atômica de snapshots
    │   ├── TV_nf.sql               # Query de notas fiscais para TV
    │   ├── TV_pedidos.sql          # Query de pedidos para TV
    │   └── TV_situac.sql           # Query de situações para TV
    ├── docs/                       # Documentação técnica detalhada
    │   ├── FLUXO-DADOS.md          # Especificação do fluxo de snapshots e integridade
    │   ├── MEMORY.md               # Histórico técnico e registros de performance
    │   └── SQL-SERVER.md           # Dicionário de dados e consultas ODBC
    ├── fixtures/                   # Massas de dados para testes isolados
    ├── static/                     # Ativos visuais servidos localmente
    │   ├── CSS/                    # Folhas de estilo (global.css, styles.css, tv.css, supersonic.css)
    │   ├── img/                    # Logotipos oficiais Supersonic (SVG e PNG)
    │   └── js/                     # Scripts clientes (app.js, tv.js, rankings.js, layout.js, etc.)
    ├── storage/                    # Armazenamento privado dos arquivos JSON (.gitkeep)
    ├── templates/                  # Templates Jinja das telas (index.html, tv.html, login.html)
    ├── tests/                      # Bateria de testes unitários automatizados (unittest)
    ├── .env.example                # Modelo das variáveis de ambiente e banco
    ├── app.py                      # Ponto de entrada e servidor HTTP Flask
    ├── atualizar-requisicoes.bat   # Script de loop de sincronização contínua (60s)
    ├── requirements.txt            # Dependências básicas da aplicação Web
    ├── requirements-sqlserver.txt  # Dependências de integração com o driver ODBC
    └── sincronizar.py              # Script executável de coleta e publicação de dados
```

---

## 3. Mapeamentos e Integração com o ERP

### A. Tabela Oficial de Setores (`OSESET`)
A aplicação integra diretamente com o cadastro de centros de custo e setores do ERP:
```sql
LEFT JOIN OSESET AS SETOR WITH(NOLOCK)
    ON REQ.CODSET = SETOR.CODSET
    AND SETOR.CODPAD IN (1)
    AND ISNULL(SETOR.INATIV, 'N') <> 'S'
```
São reconhecidos e mapeados com ícones dedicados os 17 setores oficiais:
*Compras, Crédito e Cobrança, Financeiro, Administrativo Matriz, SAC, Jurídico, T.I, RH, Armazém, Projetos, Recebimento, Limpeza, Reintegração, Manutenção, Transporte, Expedição e Fiscal.*

### B. Situações Oficiais e Fluxo por Etapas (Kanban)
O fluxo visual segue a sequência das situações homologadas do ERP:
1. **Pendente (`P`):** Aguardando análise/aprovação inicial.
2. **Cadastrado (`D`):** Registrado no sistema.
3. **Parcial (`L`):** Atendido parcialmente *(exibido apenas quando houver $\ge 1$ item ativo)*.
4. **Em cotação (`quotation`):** Em processo de cotação com fornecedores *(exibido quando $\ge 1$ item ativo)*.
5. **Aprovado (`A`):** Aprovado para compra/execução.
6. **Reprovado (`R`):** Rejeitado.
7. **Baixado (`B`):** Concluído/entregue.
8. **Cancelado (`C`):** Cancelado no ERP.

### C. Data Original de Inclusão (`DATINC`) e Formatação Estrita
- A data original de inclusão do registro no banco é extraída diretamente via `REQ.DATINC` e mapeada com fuso horário local (`-03:00`).
- Todas as datas na interface (Abertura e Referência) seguem a formatação padronizada:
  $$\text{DD/MM/AAAA, HH:MM (ex: 12/08/2026, 15:07)}$$

### D. Rankings Analíticos
O painel inclui agregação dinâmica por ocorrências servida pela rota `/api/rankings`:
- **Top Requerentes:** Volume de requisições agrupadas por código de solicitante (`CODFUN`).
- **Top Setores:** Volume de requisições agrupadas por setor (`OSESET.DESCRI`).
- **Top Itens:** Frequência de itens e produtos demandados (`PRI_CODPRO`).

---

## 4. Modos de Operação e Telas

### 1. Painel Geral (`/`)
- **Visão por Etapas (Kanban):** Colunas organizadas no fluxo oficial, com filtros de busca textual em tempo real, filtro por setor e situação.
- **Visão por Setor:** Agrupamento sanfonado por departamento.
- **Visão Rankings:** Cartões com barras de progresso proporcionais para análise de gargalos e demandas recorrentes.
- **Alternador de Tema:** Suporte nativo a Tema Claro e Escuro.

### 2. Painel TV (`/tv` e `/tv/grafico`)
Interface desenvolvida para monitores operacionais em áreas comuns:
- **Tela 1 — Resumo:** Exibe em destaque a **última requisição cadastrada** (`CODREQ — SETOR` com data de cadastro via `DATINC`) e a contagem total de requisições pendentes.
- **Tela 2 — Acompanhamento Priorizado:** Tabela com paginação automática a cada 10 segundos, priorizando requisições pendentes no topo da fila.
- **Tela 3 — Gráfico de Situações:** Visão gráfica da distribuição de status do período.

---

## 5. Como Executar

### Pré-requisitos
- **Sistema Operacional:** Windows 10/11 ou Windows Server.
- **Python:** 3.11 ou superior instalado (disponível no PATH).
- **Driver ODBC:** Microsoft ODBC Driver 17 for SQL Server instalado para conexões com o ERP.

### Inicialização Rápida (1 Clique)
Na raiz do projeto (`Painel_Requisicao/`), dê dois cliques em:
```bat
iniciar.bat
```
O script verifica o ambiente, inicia o servidor Flask em segundo plano na porta 5000 (se ainda não estiver ativo) e abre o console de sincronização contínua com o ERP em intervalos de 60 segundos.

---

### Execução Manual / Desenvolvimento

1. **Instalar Dependências:**
   ```powershell
   cd requisicoes
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   pip install -r requirements-sqlserver.txt
   ```

2. **Configurar Credenciais do ERP:**
   Crie o arquivo `requisicoes/.env` a partir do modelo `.env.example`:
   ```env
   SQLSERVER_ENABLED=true
   SQLSERVER_HOST=192.168.0.xxx
   SQLSERVER_PORT=1433
   SQLSERVER_DATABASE=db_visual_ssonic
   SQLSERVER_USER=SEU_USUARIO
   SQLSERVER_PASSWORD=SUA_SENHA
   SQLSERVER_DRIVER=ODBC Driver 17 for SQL Server
   REQUISICOES_SNAPSHOT_MAX_AGE_SECONDS=120
   ```

3. **Validar Conexão com o Banco:**
   ```powershell
   python sincronizar.py --verificar-config
   ```

4. **Executar Coleta Manual:**
   ```powershell
   python sincronizar.py --fonte erp --alvo tv
   ```

5. **Iniciar a Aplicação Web:**
   ```powershell
   python app.py
   ```
   Acesse no navegador:
   - Painel de Gestão: `http://localhost:5000/`
   - Painel para TV Corporativa: `http://localhost:5000/tv`

---

## 6. Validação e Qualidade de Código

Para garantir a estabilidade das rotas, do sincronizador e dos contratos da API:

```powershell
# Execução da suíte completa de testes unitários (35 testes)
cd requisicoes
python -m unittest discover -s tests -v

# Checagem de sintaxe dos scripts JavaScript do frontend
node --check static/js/app.js
node --check static/js/tv.js
node --check static/js/rankings.js
node --check static/js/layout.js
node --check static/js/login.js
node --check static/js/requisicoes-fluxo.js
node --check static/js/requisicoes-status.js
```

---

## 7. Remoção de Travas de Execução (Troubleshooting)

Caso um processo de coleta seja interrompido abruptamente e deixe uma trava de arquivo temporária em `storage/`:
```powershell
python -c "import pathlib; [f.unlink() for f in pathlib.Path('requisicoes/storage').glob('*lock*') if f.is_file()]; print('Travas liberadas com sucesso!')"
```
