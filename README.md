                ESTE README TEM COMO OBJETIVO DEFINIR AS CARACTERISTICAS DO PROJETO

  
  Sistema funcional para abertura de chamados:
  tecnologias: HTML, Bootstrap, JavaScript, Ajax PHP e PostgreeSQL;
  Contendo um banco de dados local;
  Possui campo de login e cadastro;

  Página inicial
  
• Criar uma página utilizando HTML + Bootstrap.
• A tela inicial deve apresentar duas opções: Login e Cadastro de usuário.
Tela de Login
Campos:
• E-mail
• Senha
O login deve ser realizado utilizando o e-mail como identificador.
Tela de Cadastro

Campos obrigatórios:

• Nome
• E-mail
• Telefone
• CPF
• Senha (Adicionem confirmar senha)

Validações em JavaScript (apenas no frontend):

• Verificar se todos os campos obrigatórios estão preenchidos.
• Validar o formato do e-mail (presença de @ e domínio).
• Utilizar PostgreeSQL para armazenamento usando PDO

Regra de identação:
• Comentarios para manutenção futuras
• Layout responsivo com o BOOTSTRAP
• Validar apenas o formato do CPF (máscara 000.000.000-00 ou 11 dígitos numéricos). Não é necessário
validar dígitos verificadores.
• Interface simples, clara e funcional.
• Uso de AJAX para as requisições com BD
• Estrutura básica do banco de dados com pelo menos duas tabelas: 
o usuarios (sem acento, para evitar problemas de codificação)
o chamados (com chave estrangeira referenciando usuarios)
• Não é necessário implementar segurança avançada (manter nível introdutório), mas o uso de hash 
de senha é recomendado.

A principio o codigo tera duas versões, uma sem uso de A.I e outra refatorada com A.I

01/05/2026
