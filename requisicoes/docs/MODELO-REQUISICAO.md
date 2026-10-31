# Modelo estrutural de nova requisição

Página: `GET /nova-requisicao`. Documento de trabalho para revisão da interface e do futuro contrato. **Não é o schema Rodopar, um endpoint de escrita ou uma autorização de gravação.**

Referências: quatro capturas fornecidas em 01/10/2026 e a árvore `Campos preenchimento requisição de compras.html`, em `Pictures/nova requisição`. As capturas orientam a composição; valores redigidos/ocultos não foram reconstruídos. Catálogos são exemplos locais, sem consulta a cadastros reais.

## Organização e responsabilidades

- `templates/nova_requisicao.html`: seis abas, campos, tabelas e diálogos; macro `lookup` padroniza os campos consultáveis. Reutiliza os fragmentos de `components` por `layout.js`.
- `static/CSS/requisicao.css`: composição da página sobre `global.css` e tokens Supersonic.
- `static/js/requisicao.js`: catálogo demonstrativo, árvore recursiva de detalhes, interações e apresentação segura por `textContent`.
- `static/js/requisicao-modelo.js`: modelo independente do DOM; cria/edita/remove linhas e exporta uma cópia do rascunho. Testes com Node, sem dependências adicionais.
- `docs/requisicao.exemplo.json`: exemplo preenchido, compatível com a estrutura exportada pela página.

## Estrutura proposta

| Campo | Tipo / propósito |
| --- | --- |
| `versaoModelo` | Número de versão do modelo local; atualmente 1 |
| `demonstrativo` | `true`; impede confundir o arquivo de exemplo com registro homologado |
| `idLocal` | UUID do rascunho; nunca usado como chave ERP |
| `estadoPortal` | `rascunho`; separado de `situacaoERP` |
| `codigoERP`, `situacaoERP` | `null` até integração confirmada |
| `geral` | Referências de filial, tarefa, funcionário, fornecedor, setor, aprovador, liberador, filial da OS; datas ISO `AAAA-MM-DD`, observação, OS, tipo e tipo de requisição |
| `classificacao` | Unidade de negócio, centro de gasto, centro de custo, classes sintética e analítica |
| `itens` | Linhas independentes; estrutura abaixo |
| `localizacoes` | Relações com item por `itemIdLocal`, referência da localização e quantidade |
| `anexos` | Metadados: ID local, nome, tamanho em bytes, tipo informado e `enviado: false`; não contém binários nem caminho privado |
| `baixas`, `cotacoes` | `null`: estrutura ainda não fornecida, sem inferência de campos ou operações |
| `auditoriaERP` | Datas/usuários de inclusão, atualização, aprovação e liberação; todos `null` |

Referências usam `{codigo: string, descricao: string}`. Produto acrescenta `unidade`. A descrição permite revisar o rascunho, mas **o backend deverá consultar e validar a referência real**. Zeros à esquerda de códigos são preservados. A árvore completa de consulta não é copiada para o rascunho; por exemplo, CPF/CNPJ e regras de acesso não são transportados com a indicação do fornecedor/aprovador.

Cada item possui `idLocal`, `sequencia`, `produto`, `quantidade`, `unidade`, `veiculo`, `critico`, `valorInformado`, `mediaConsumo`, `aplicacao`, `observacao`, `situacaoERP`, `cotado` e `pedido`. Campos ausentes são `null`; zero informado continua zero. Quantidades e valores decimais são strings, sem conversão monetária ou arredondamento. O significado de “Valor” na captura não permite concluir se é preço unitário ou total; por isso o modelo não calcula totais.

## Comportamentos disponíveis

1. Preencher Geral, consultando os rótulos azuis ou o campo correspondente. Busca por código/descrição; detalhes hierárquicos do fornecedor, funcionário, filial, unidade de negócio, aprovador e liberador seguem a árvore fornecida. Opções de situação são referências visuais, sem conferir permissões.
2. Incluir, editar e remover itens. A sequência não é reutilizada após exclusão; a edição mantém o ID local e a sequência. O código da requisição fica no nível superior e não é repetido em cada linha.
3. Vincular localizações a itens existentes. A troca de produto com localizações exige removê-las antes. Excluir um item com localizações pede confirmação e remove os vínculos; não deixa linhas órfãs.
4. Selecionar PDF, PNG e JPEG, até 10 MB por arquivo (limite apenas demonstrativo da interface), visualizar e remover anexos. Não existe upload. PDF é mostrado em iframe isolado; o visualizador depende do navegador, com opção de baixar o original.
5. Revisar o rascunho, visualizar seu JSON e baixar o modelo. Campos de item/localização ainda não incorporados à tabela bloqueiam a exportação até inclusão ou limpeza. Dados incompletos de Geral podem ser exportados como modelo para trabalho; a revisão mostra o que falta.

O estado dura somente enquanto a página permanece aberta. A página solicita confirmação do navegador ao sair com alterações; não é salvamento. Um download iniciado não é garantia de arquivo salvo pelo navegador. Anexos não acompanham o JSON; mantenha os originais.

Para revisar este protótipo, a interface solicita filial, tarefa, funcionário, data de referência, observação e pelo menos um item com produto e quantidade positiva. Quantidades/valores opcionais não podem ser negativos. **São validações do modelo de interface, sujeitas à revisão, não regras homologadas do ERP.** Classificação e distribuição entre localizações não têm dependências/saldos presumidos.

## Pendências para integrar

- Endpoint, autenticação, permissões, chaves compostas, nomes reais de tabelas/colunas, obrigatoriedade e nulabilidade.
- Origem e filtros dos catálogos; vínculo entre filial, funcionário, classificações e permissões de aprovador/liberador.
- Confirmação do uso de Setor (a própria árvore pergunta se é usado), Tipo de requisição e Filial/OS.
- Semântica de Valor, escala/unidade, saldos de localização, duplicidade de produto, transições de situação e tratamento de falhas.
- Conteúdo das abas Baixas e Cotações; nenhuma captura interna dessas abas foi recebida.
- Contrato de upload/armazenamento, tipos/tamanhos permitidos, geração de códigos e auditoria pelo servidor.
- Persistência/autorização/validação no backend antes de qualquer inclusão em tabela real.

## Verificação

Execute `node tests/requisicao-modelo.test.cjs` e `python -m unittest discover -s tests -v`, além de `node --check` nos cinco scripts próprios de `static/js`. O teste Node direto evita criar subprocessos em ambientes Windows restritos. Verifique também temas, navegação entre páginas, edição/vínculos das tabelas, diálogos, anexos e telas estreitas.
