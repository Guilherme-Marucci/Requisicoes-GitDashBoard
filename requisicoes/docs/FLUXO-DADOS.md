# SELECT → JSON privado → Flask → página

Estado de 15/10/2026: SELECT homologado para o Painel TV (Opção B); CODREQ como chave; colunas CODFIL (filial), OBSERV (observação), DATATU (referência), CODFUN (solicitante), SITUAC (situação) e PRI_CODPRO (primeiro produto) vinculadas em FIELD_COLUMNS; códigos da situação SITUAC (A, B, C, D, L, P, R) homologados e mapeados para os status do painel.

## Responsabilidades

| Parte | Responsabilidade |
| --- | --- |
| core/database.sql e core/consultas.py | SELECT recebido, registrado com o nome requisicoes; diagnóstico separado |
| core/config.py e .env | Configuração privada SQL Server; nomes DB_SERVER, DB_DATABASE, DB_USERNAME, DB_RD_PASSWORD e DB_DRIVER |
| core/database.py | Leitura ODBC, parâmetros, limite de linhas, fechamento e erros sanitizados |
| core/erp.py | Chave e mapeamento permitido do resultado SQL para o painel |
| sincronizar.py | Coleta independente do servidor web |
| core/requisicoes.py | Validação, lock, publicação atômica e leitura do JSON |
| storage/requisicoes.json | Última coleta ERP válida, privada e fora de static |
| app.py | Páginas e GET /api/requisicoes, sem importar ou chamar o coletor |
| static/js/app.js e tv.js | Filtros, cartões, indicadores e TV, lendo apenas a API |
| tests/fixtures | Massa isolada de testes; nunca utilizada pela aplicação |

Abrir páginas, filtrar e recarregar a API não executam SELECT. Dados externos não definem CSS, HTML, logos ou cores. Preservados global.css, supersonic.css, components e layout.js. E-mails continuam descontinuados; nova requisição permanece descontinuada, com seus arquivos preservados.

## Preparar a primeira coleta

1. Configure uma conta SELECT no .env privado, usando as dependências próprias de requirements-sqlserver.txt e o driver instalado em DB_DRIVER. Não sobrescreva o arquivo existente com o modelo.
2. A chave está configurada em core/erp.py: KEY_COLUMNS = ("CODREQ",), conforme confirmação do usuário. Chaves ausentes ou duplicadas rejeitam a coleta inteira.
3. FIELD_COLUMNS e STATUS_MAP preenchidos com os campos da Opção B e códigos de SITUAC homologados pelo usuário.
4. Configure SQLSERVER_ENABLED=true no ambiente de teste e execute o coletor separadamente do Flask.

Na raiz do projeto, com o Python das dependências desta aplicação:

```powershell
python sincronizar.py --verificar-config
python sincronizar.py --fonte erp
python app.py
```

--verificar-config verifica apenas a configuração da conexão, sem acesso à rede. --testar-conexao é um diagnóstico manual opcional que executa somente SELECT CAST(1 AS int) AS conexao_ok; não consulta tabelas nem publica dados. --fonte demonstracao não existe mais. A origem ERP não torna o login demonstrativo um controle de acesso para produção.

## Contrato de apresentação, versão 3

A API entrega meta (schemaVersion, source, generatedAt, lastAttemptAt, lastAttemptOk, stale, maxAgeSeconds) e requests. A origem é sempre erp. Datas de coleta são ISO com fuso UTC. A saúde /api/health informa somente o processo HTTP, com mode somente_leitura.

Cada registro contém:

- id: identidade interna estável derivada da chave confirmada; não é o código exibido.
- code: código textual usado nos cartões, TV e busca; conserva zeros à esquerda.
- sector e status: identificadores do catálogo local, definidos somente por mapeamento explícito. Sem vínculo: unclassified e unmapped.
- branch, title, description, reference, deadline e item: campos de apresentação. Sem origem confirmada, mostram “Não informado/a”; o título padrão usa apenas o código da própria requisição.
- requester, firstProduct e createdAt: opcionais, nulos se ausentes. createdAt exige instante/fuso confirmado; uma data SQL sem fuso não é convertida supondo o horário local.
- workflow: extensão opcional para etapa, motivo de atenção, valor e histórico reais, conforme descrito abaixo. O adaptador atual não fabrica nem preenche esses dados.

REQ.* nunca é enviado à API: somente essa lista permitida é publicada. Colunas NULL omitidas no SELECT continuam sem informação no adaptador. NULL não é convertido em zero. Decimal mantém precisão textual, sem float; objetos sem conversão conhecida rejeitam a coleta.

Snapshots v1/v2 e qualquer origem demonstrativa são rejeitados. Não existe migração que renomeie dados fictícios como ERP.

## Atualização e falhas

A coleta usa um lock exclusivo .coleta.lock e publica por arquivo temporário no mesmo volume, fsync e substituição atômica. O leitor recebe o JSON anterior ou o novo inteiro. Limite de linhas, chave duplicada, tipos inválidos e falhas SQL rejeitam o lote completo.

Se já houver uma coleta ERP válida, a falha preserva registros e generatedAt, atualiza lastAttemptAt e sinaliza lastAttemptOk=false. Uma falha inicial não publica um resultado vazio de sucesso: a API responde 503 e a interface aguarda dados. Somente um SELECT concluído sem registros publica uma lista vazia válida, com HTTP 200. GET nunca repara ou escreve arquivos.

Após interrupção forçada, pode restar .coleta.lock. Antes de removê-lo manualmente, confirme que nenhum coletor está em execução. storage deve permanecer privado, fora de static; cada ambiente usa sua própria configuração.

## Atualização a cada minuto

Em Git Bash/Bash:

```bash
# Use o Python com as dependências deste projeto.
export PYTHON_BIN="/c/caminho/do/projeto/.venv/Scripts/python.exe"
bash atualizar-requisicoes.sh erp --uma-vez
bash atualizar-requisicoes.sh erp
```

O script chama o mesmo coletor, desconta o tempo de execução do intervalo de 60 segundos e evita sobreposição. Coletas demoradas pulam intervalos perdidos. Falhas preservam a última versão ERP válida e permitem nova tentativa. Ctrl+C interrompe a espera ou aguarda a coleta em andamento liberar o lock. Nenhum serviço de inicialização do Windows foi instalado ou iniciado. O Bash não executa .env como código; quem lê a configuração é o Python.

## Painel e TV

O painel conserva Kanban, setores, busca por código, filtros combinados e expansão independente. O filtro de setor lista apenas classificações presentes na coleta. Sem etapa, os cartões aparecem em Etapa não informada. Situações não mapeadas têm indicação neutra, preservando todas as cores anteriores. O indicador de pendentes não mostra uma contagem completa enquanto houver situações não mapeadas; informa quantas já foram classificadas e quantas ainda não.

/tv alterna automaticamente resumo → tabela → gráfico, com 90 segundos por tela, sem pausa ou botões de avanço. A tabela avança seis linhas a cada 15 segundos visíveis. A leitura da API ocorre a cada 60 segundos, sem coletar. /tv/grafico reutiliza o mesmo gráfico por endereço direto. Mantidos temas, tela cheia, barra sutil e respeito a movimento reduzido.

A tabela usa code, branch, firstProduct, primeiro nome de requester, description e status. O resumo identifica a última cadastrada por createdAt somente quando todos os registros possuem data válida. Não há fallback por código. “Sem requisições pendentes” permanece verde apenas em uma coleta válida com zero pendentes e nenhuma situação não mapeada; indisponibilidade nunca vira sucesso. Pedidos e Finalizados / NF continuam somente com títulos.

O layout atende resoluções de televisão e telas menores; distância, zoom e overscan exigem conferência no equipamento. Falhas preservam a última leitura ERP válida com aviso de atualização/idade.

## Etapas e histórico

Etapa e situação são independentes. workflow pode ser omitido ou nulo. Suas propriedades opcionais:

- stage: request, approval, quotation, execution, invoice, payment ou closed.
- attention: motivo textual de revisão; combinado com status pending no filtro de atenção.
- estimatedValue: decimal textual não negativo, com duas casas e até 12 dígitos inteiros; o painel apresenta BRL. Origem e moeda reais precisam de confirmação antes de mapear.
- history: lista de eventos com exatamente at (instante ISO com fuso), action (texto), actor (texto ou nulo) e stage (etapa válida). A interface ordena pelo instante sem modificar o retrato.

Sem auditoria, aparece “Histórico não disponível nesta coleta”. Não criar eventos por comparação de snapshots nem presumir conferência de NF, pagamento ou encerramento pela situação atual. Não há arrastar cartões nem gravação no ERP.

## Verificar

```powershell
python -m unittest discover -s tests -v
node --check static/js/layout.js
node --check static/js/app.js
node --check static/js/login.js
node --check static/js/tv.js
node tests/tv.test.cjs
node tests/requisicoes-fluxo.test.cjs
node tests/requisicao-modelo.test.cjs
```

Testes usam consultas simuladas e pastas isoladas sob tests/.runtime, sem alterar storage nem acessar o SQL Server. Cobrem mapeamento, campos permitidos, chaves, preservação em falhas, retratos legados, estados vazios, separação HTTP/coleta e regras da TV. Configuração e pendências específicas do SELECT em [SQL-SERVER.md](SQL-SERVER.md).
