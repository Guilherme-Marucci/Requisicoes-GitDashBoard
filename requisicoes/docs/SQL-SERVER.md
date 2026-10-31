# Preparação para SELECT no SQL Server

O projeto está preparado para receber consultas revisadas, sem SQL de tabelas presumido e sem conectar automaticamente. O fluxo do painel permanece coleta independente → JSON privado → Flask → página. O SELECT recebido em 09/10/2026 está no catálogo com o nome requisicoes. O coletor aceita somente ERP, valida a chave configurada antes de conectar e publica apenas os campos permitidos. CODREQ foi confirmado pelo usuário como identificador único; os demais vínculos exigem as confirmações abaixo; nenhuma consulta real foi executada nesta entrega.

## Arquivos e responsabilidades

| Arquivo | Responsabilidade |
| --- | --- |
| `.env` | Configuração privada local, criada com campos vazios e banco desabilitado |
| `.env.example` | Modelo versionável, sem credenciais |
| `core/config.py` | Leitura do .env, precedência das variáveis do processo e validação técnica |
| `core/consultas.py` | Catálogo interno de SELECTs nomeados e parâmetros posicionais |
| `core/database.py` | Conexão, execução parametrizada, limites, fechamento e erros sanitizados |
| `core/erp.py` | Conversão de tipos, identidade, campos permitidos e classificação; configurações ainda a confirmar |
| `core/requisicoes.py` | Validação e publicação atômica do JSON, preservadas |
| `sincronizar.py` | Coleta ERP e comandos manuais de verificação |

O Flask não importa o coletor SQL nem executa consultas ao receber GET. Preencher o .env não habilita a publicação de dados reais na API. Não foi criada rota para executar SQL.

## Configurar

1. Use um ambiente Python próprio do projeto e instale `python -m pip install -r requirements-sqlserver.txt`. Esse arquivo inclui as dependências web e o pyodbc. O driver indicado em `DB_DRIVER` deve estar instalado no sistema; o padrão solicitado é `ODBC Driver 13 for SQL Server`. Ele não é instalado pelo pip.
2. Edite o `.env` da raiz de `requisicoes`. Em uma nova cópia, crie-o a partir de `.env.example` somente se não existir.
3. Preencha servidor, banco de teste e a autenticação autorizada. Use uma conta com permissões limitadas a SELECT nos objetos homologados. Nunca envie a senha pelo chat nem coloque credenciais em código, JSON, HTML ou commits.
4. Para validar a conexão manualmente, altere `SQLSERVER_ENABLED=true`. A aplicação web continua sem consultar o banco.

| Variável | Uso |
| --- | --- |
| `SQLSERVER_ENABLED` | `false` por padrão; bloqueia qualquer conexão do adaptador |
| `DB_DRIVER` | Driver instalado; padrão ODBC Driver 13 for SQL Server. Diferenças de maiúsculas são aceitas |
| `DB_SERVER` | Servidor/instância ou host,porta fornecido pelo responsável pelo banco |
| `DB_DATABASE` | Banco de teste autorizado |
| `SQLSERVER_AUTH` | `sql` para usuário/senha ou `windows` para identidade do processo |
| `DB_USERNAME`, `DB_RD_PASSWORD` | Usuário e senha exigidos apenas na autenticação SQL |
| `SQLSERVER_CONNECT_TIMEOUT` | Limite positivo de conexão; padrão 10 segundos |
| `SQLSERVER_QUERY_TIMEOUT` | Limite positivo da consulta; padrão 30 segundos |
| `SQLSERVER_MAX_ROWS` | Limite técnico de coleta; padrão 10000 linhas |
| `REQUISICOES_STORAGE_DIR` | JSON privado, padrão `storage` |
| `REQUISICOES_MAX_AGE_SECONDS` | Limite de atualização, padrão 900 segundos |

Valores do processo prevalecem sobre o arquivo. A leitura procura somente o .env desta aplicação, independentemente do diretório atual, e não expande referências `${...}`. Para valores contendo espaços ou `#`, use as regras de aspas do python-dotenv. A senha não é removida de espaços nem registrada em mensagens/repr da configuração.

Padrão solicitado em 09/10/2026:

```dotenv
# CONFIGURAÇÃO DO BANCO DE DADOS MYSQL (reservada; não usada pelo coletor):
DB_USER=
DB_PASSWORD=
DB_HOST=
DB_PORT=
DB_NAME=

# CONFIGURAÇÃO DO BANCO DE DADOS SQL SERVER:
DB_SERVER=
DB_DATABASE=
DB_USERNAME=
DB_RD_PASSWORD=
DB_DRIVER=ODBC Driver 13 for SQL Server
```

O projeto continua usando SQL Server. As cinco variáveis do bloco MySQL são apenas reservadas; não são aliases das credenciais SQL Server nem ativam outro banco. Para SQL Server com porta explícita, use `DB_SERVER=host,porta`; `DB_PORT` pertence ao bloco MySQL.

Os nomes anteriores `SQLSERVER_SERVER`, `SQLSERVER_DATABASE`, `SQLSERVER_USERNAME`, `SQLSERVER_PASSWORD` e `SQLSERVER_DRIVER` continuam aceitos como aliases de compatibilidade. Dentro da mesma fonte, o nome novo prevalece, inclusive se vazio. O processo continua prevalecendo sobre o arquivo mesmo usando nomes antigos. Habilitação, autenticação Windows/SQL e limites mantêm as variáveis `SQLSERVER_ENABLED`, `SQLSERVER_AUTH`, `SQLSERVER_CONNECT_TIMEOUT`, `SQLSERVER_QUERY_TIMEOUT` e `SQLSERVER_MAX_ROWS`.

A conexão exige criptografia e validação do certificado (`Encrypt=yes;TrustServerCertificate=no`). Configure o certificado/nome correto com a infraestrutura. `readonly=True` e `ApplicationIntent=ReadOnly` indicam a intenção de leitura; a restrição efetiva de escrita deve ser garantida pelas permissões da conta SQL Server.

## Comandos

Na pasta do projeto:

```powershell
python sincronizar.py --verificar-config
python sincronizar.py --testar-conexao
```

O primeiro valida os valores sem acessar a rede; não confirma driver, credenciais nem permissões. O segundo executa apenas `SELECT CAST(1 AS int) AS conexao_ok`, fecha a conexão e não publica JSON. Ele não confirma acesso às tabelas do ERP. Não foi executado contra servidor real nesta entrega.

Com CODREQ configurado como chave, após preparar a conexão e revisar os campos em core/erp.py:

```powershell
python sincronizar.py --fonte erp
python app.py
```

O modo `--fonte demonstracao` foi removido. O modo ERP exige `KEY_COLUMNS` preenchido e conexão habilitada; uma falha inicial não publica uma lista vazia de sucesso. Os testes usam conexões simuladas e pastas isoladas, sem acessar o banco.

## Receber o SELECT

Inclua o SQL revisado no catálogo de `core/consultas.py` com um nome estável. Use `?` para valores variáveis e declare a ordem em `Consulta.parametros`. `consultar(nome, parametros)` recebe apenas o nome e os valores; nunca aceita SQL do frontend, de e-mails ou do .env. O catálogo é código confiável, revisado por desenvolvedores: não é um filtro capaz de tornar SQL arbitrário seguro. Revise cada entrada para conter somente SELECT, sem SELECT INTO, comandos adicionais ou procedimentos de escrita.

O catálogo contém o diagnóstico técnico e o SELECT de Requisições fornecido. Para ativar a coleta no ambiente de teste, confirmar:

- Banco/ambiente e objetos autorizados; colunas com aliases únicos.
- Chave simples ou composta, granularidade e recorte de filiais autorizado.
- Parâmetros/filtros, ordenação e volume esperado.
- Tratamento de nulos, datas, valores decimais, zeros iniciais e situações ERP.
- Mapeamento de apresentação e acesso aos dados reais; o login atual é demonstrativo.

O adaptador preserva os tipos do driver (`None`, `Decimal`, datas e textos), sem converter tudo para string ou float. A transformação pertence a `core/erp.py`, conforme o contrato real. Aliases duplicados e excesso de linhas são erros; nunca se publica um resultado truncado como coleta completa. Os limites técnicos não substituem filtros e índices adequados no SQL homologado.

## SELECT homologado para Painel TV — 15/10/2026 (Opção B)

O SQL fica em `core/database.sql` e é registrado em `core/consultas.py::REQUISICOES`.

```sql
SELECT
    REQ.CODREQ,
    REQ.CODFIL,
    REQ.DATATU,
    LEFT(REQ.OBSERV, 30) AS OBSERV,
    REQ.CODFUN,
    REQ.SITUAC,
    (
        SELECT TOP 1 IRQ.CODPROD
        FROM ESTIRQ AS IRQ
        WHERE REQ.CODREQ = IRQ.CODREQ
    ) AS PRI_CODPRO
FROM ESTREQ AS REQ
WHERE REQ.CODPAD IN (1)
  AND REQ.DATATU > '2026-02-01'
ORDER BY REQ.CODREQ DESC;
```

Mapeamento homologado em `core/erp.py`:

- `KEY_COLUMNS = ("CODREQ",)`: identificador único da requisição.
- `FIELD_COLUMNS`:
  - `code` ← `CODREQ`
  - `branch` ← `CODFIL`
  - `description` ← `OBSERV`
  - `reference` ← `DATATU`
  - `requester` ← `CODFUN`
  - `firstProduct` ← `PRI_CODPRO`
- `STATUS_COLUMNS = ("SITUAC",)` e `STATUS_MAP`:
  - `A` → `approved` (Aprovado)
  - `B` → `closed` (Baixado)
  - `C` → `canceled` (Cancelado)
  - `D` → `registered` (Cadastrada)
  - `L` → `partial` (Parcial)
  - `P` → `pending` (Pendente)
  - `R` → `rejected` (Reprovado)
  - `NULL` / outros → `unmapped` (Não mapeada)

Os exemplos antigos existem somente em `tests/fixtures`. A aplicação e o coletor nunca os leem; snapshots demonstrativos v1/v2 não são aceitos na API nem usados como reserva após falha. A autenticação do portal continua na camada futura; esta preparação não libera exposição do banco em produção.

Fundamento da ordenação: [TOP no SQL Server — documentação Microsoft](https://learn.microsoft.com/en-us/sql/t-sql/queries/top-transact-sql?view=sql-server-ver15).

Projeção dinâmica: [metadados do primeiro resultado](https://learn.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-objects/sys-dm-exec-describe-first-result-set-transact-sql), [QUOTENAME](https://learn.microsoft.com/en-us/sql/t-sql/functions/quotename-transact-sql) e [sp_executesql](https://learn.microsoft.com/en-us/sql/relational-databases/system-stored-procedures/sp-executesql-transact-sql).

## Referências técnicas

- [Configuração python-dotenv](https://bbc2.github.io/python-dotenv/reference/)
- [Conexão, timeout e fechamento do pyodbc](https://github.com/mkleehammer/pyodbc/wiki/Connection)
- [Parâmetros de conexão pyodbc](https://github.com/mkleehammer/pyodbc/wiki/The-pyodbc-Module)
- [Intenção de leitura no driver SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/odbc-driver-support-for-high-availability-disaster-recovery)
- [Nomes dos drivers ODBC registrados no Windows](https://learn.microsoft.com/en-us/sql/connect/odbc/windows/system-requirements-installation-and-driver-files)
