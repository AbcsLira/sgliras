# Organização do projeto

O comando de inicialização continua sendo `python app.py`. No Windows, os
arquivos `iniciar.bat` e `iniciar_segundo_plano.bat` continuam usando essa entrada.
Execute os comandos na raiz do checkout.

Os módulos do backend, os módulos JavaScript e os testes usam nomes em português,
sem acentos ou espaços. Os arquivos HTML, CSS e o script de login mantêm os nomes
convencionais `index.html`, `login.html`, `index.css`, `login.css` e `login.js`.
Os nomes convencionais das ferramentas, como `app.py`, `__init__.py`,
`requirements.txt`, `README.md` e os diretórios `static/` e `templates/`, são
preservados. Os arquivos de teste usam o prefixo `teste_`, compatível com o
padrão `test*.py` do unittest. A padronização dos arquivos não altera as URLs
das APIs nem os nomes e caminhos dos dados locais.

## Backend

- `app.py`: entrada do servidor, inicialização do banco e backup diário.
- `sgliras/__init__.py`: `create_app()`, configuração Flask e registro das rotas.
- `sgliras/configuracao.py`: caminhos, leitura de `config.ini` e chave de sessão.
- `sgliras/banco_dados.py`: schema, migrações existentes e conexões SQLite.
- `sgliras/seguranca.py`: perfis, hashes de senha e controle de acesso.
- `sgliras/auditoria.py`: registro de auditoria dentro da transação da operação.
- `sgliras/copias_seguranca.py`: backup SQLite e verificação de integridade.
- `backup_banco.py` e `backup_externo.bat`: backup consistente para destino externo.
- `sgliras/rotas/`: autenticação, usuários, estoque, dashboard, receitas,
  fornecedores, inventário, relatórios e administração de backups.
- `sgliras/rotas/financeiro_*.py`: fechamento diário, contas, pães, massas e relatórios.
- `sgliras/cartoes.py`: condições, vendas e parcelas de cartões, em centavos.
- `sgliras/rotas/financeiro_cartoes.py`: API administrativa de cartões e recebíveis.

Cada módulo de rotas declara suas funções e expõe `register_routes(app)`.
O registro mantém as URLs e os nomes dos endpoints existentes, incluindo
`url_for('login_page')`. As regras de negócio existentes permanecem nas rotas;
a separação em serviços menores pode ser feita conforme cada funcionalidade evoluir.

`create_app()` aceita configuração adicional para testes. `DATABASE` e
`BACKUP_DIR` pertencem à instância Flask, evitando compartilhar dados entre
aplicações de teste. `init_db()` e as funções de banco/backup precisam de um
contexto Flask (`with app.app_context():` fora de uma requisição).

## Interface

- `templates/index.html`: estrutura da aplicação e modais.
- `templates/login.html`: formulário de autenticação.
- `static/css/`: estilos separados da aplicação e do login.
- `static/js/login.js`: autenticação da tela de login.
- `static/js/modules/`: scripts separados por área funcional.
- `templates/financeiro_cartoes.html`, `static/css/cartoes.css` e
  `static/js/modules/financeiro_cartoes.js`: tela independente de cartões.
- `static/js/modules/relatorio_cartoes.js`: relatório de cartões para impressão/PDF.

Os scripts são carregados na ordem declarada em `templates/index.html`.
Continuam sendo scripts clássicos: os manipuladores usados por `onclick` e o
estado compartilhado da interface foram preservados. `nucleo.js` contém o estado
comum e `navegacao.js`, carregado por último, chama `init()`. Não use `async`, nem
altere a ordem sem revisar as dependências. Os estilos e scripts das janelas
de impressão continuam nos templates de impressão gerados pelo JavaScript.
Não há etapa de build do frontend.

As buscas locais agrupam a digitação por 150 ms. Os seletores mostram até 50
resultados e continuam pesquisando o catálogo completo; scanners, categorias
e abertura dos modais respondem imediatamente. A tabela de produtos oferece
paginação de 25, 50 ou 100 linhas e preserva os filtros ao atualizar os dados.
Tabela e seletores procuram todas as palavras digitadas em qualquer ordem,
ignorando acentos e maiúsculas, nos campos nome, código e código de barras.
Por exemplo, `molho pizza` encontra `Molho de Pizza`. A prévia e a API da
listagem para impressão aplicam a mesma regra ao filtro por nome. A leitura
do scanner continua exigindo o código de barras exato.

No inventário, editar uma contagem atualiza apenas sua diferença e os
contadores, preservando foco e rolagem. Campo apagado ou quantidade inválida
exige correção antes de salvar; zero continua sendo uma contagem válida.

Contas a pagar e a receber compartilham leituras e aplicam filtros localmente.
O cache dura até 30 segundos e é revalidado na próxima interação, na entrada
da tela, pelo botão Atualizar ou após uma alteração. Respostas substituídas
são descartadas. Falhas preservam os dados visíveis e oferecem nova tentativa.
Os dados continuam sendo obtidos das APIs existentes; o cache não altera os
registros no banco. A fonte Inter é servida localmente de `static/fonts/`, com
licença OFL incluída; funciona sem internet e mantém fontes do sistema como
alternativa.

## Instalação e testes

```sh
python -m venv venv
# Linux/macOS: source venv/bin/activate
# Windows: venv\Scripts\activate
python -m pip install -r requirements.txt
python -m unittest discover -s testes -v
# Opcional para rodar o sistema, necessário para verificar os testes da interface:
node testes/executar_interface.cjs
python app.py
```

Os testes usam diretórios temporários, sem acessar o banco real. A referência
`testes/dados_referencia/http_anterior.json` foi capturada antes da refatoração: cobre o
mapa de rotas e 180 consultas GET, incluindo acesso anônimo e os três perfis.
Somente os campos de horário de criação/geração são normalizados. Outros testes
cobrem login, sessão, arquivos estáticos, estoque, custo de receita, pagamento,
backup íntegro, reinicialização do schema e isolamento entre aplicações.

O banco `estoque.db`, seus arquivos WAL/SHM, `config.ini` e `backups/` permanecem
na raiz e são ignorados pelo Git. Não apague WAL/SHM manualmente.

## Garantias de gravação e validação

`sgliras/validacao.py` valida objetos JSON, textos, números finitos e datas.
Produtos, movimentações, contagens, usuários, contas a pagar/receber e os fluxos
de pães e massas validam os dados antes de gravar. Falhas de integridade retornam conflito e
o log do servidor registra a causa; banco temporariamente ocupado retorna 503.

`sgliras/operacoes.py` executa lotes de estoque e contas a pagar dentro de uma
transação `BEGIN IMMEDIATE`. O cliente envia `operacao_id`; a chave, o usuário,
a rota, o conteúdo e a resposta ficam em `operacoes_idempotentes`, na mesma
transação dos dados. Repetir a mesma operação retorna a resposta salva, sem
aplicar os itens novamente. Reusar a chave com conteúdo diferente retorna 409.
Não exclua essas chaves para tentar reenviar um lote; uma gravação nova deve
ter um novo identificador. Os endpoints individuais antigos são preservados.

Os formulários bloqueiam envios concorrentes. Se a resposta se perder, a
tentativa original fica pendente e é reenviada com a mesma chave antes de
enviar dados editados. A tela informa essa confirmação; os dados novos não
são enviados junto. A pendência é conservada na sessão da aba por usuário e
tipo de formulário, inclusive após atualizar a página. Se o navegador bloquear
o armazenamento, essa proteção permanece em memória até sair da página.

O backend reconsulta o usuário a cada requisição autenticada. Desativar ou
remover um usuário invalida a sessão no próximo acesso; mudar seu perfil vale
imediatamente nas permissões. O último administrador ativo é protegido contra
remoção, desativação e mudança de perfil.

Pagamentos repetidos ou sobrepostos de pães retornam 409. O estorno reabre as
contas preservando seus valores. Entregas de massas e contas vinculadas são
atualizadas juntas; entregas já pagas não podem ser editadas ou excluídas.
Use os módulos de origem para editar ou excluir contas vinculadas.

As migrações são transacionais e só acrescentam colunas ausentes. Falhas
inesperadas interrompem a inicialização e desfazem a migração; consulte o erro
e preserve o banco para diagnóstico. Conexões esquecidas são fechadas ao fim
do contexto Flask, desfazendo gravações não confirmadas.

O backup externo usa a API SQLite, verifica a integridade antes de publicar o
arquivo e preserva destinos existentes. O nome automático é gerado em Python,
independente do idioma do Windows. O batch interrompe em falha, e a retenção
considera a data no nome dos arquivos, preservando as 60 cópias mais recentes.

Os testes de estabilidade exercitam validação, repetição, concorrência e
rollback usando bancos temporários. Os testes Node executam os scripts reais
com DOM e rede simulados, sem dependências adicionais. O workflow
`.github/workflows/testes.yml` configura a execução de ambos em Linux e Windows.
O backend é verificado com Python 3.12 e 3.14.
Isso não substitui testar impressão e interação visual no navegador utilizado
na operação.

Em um banco sem usuários, `init_db()` gera uma senha aleatória para o primeiro
administrador e a retorna apenas após confirmar a transação. `app.py` mostra
essa senha uma única vez no terminal. Reinicializar um banco com usuários
preserva senhas e logins, inclusive se o administrador tiver sido renomeado.

## Cartões e recebíveis

As tabelas `fin_cartoes_condicoes`, `fin_cartoes_vendas` e `fin_cartoes_parcelas`
são acrescentadas na inicialização, dentro da transação de migração. A API
fica em `/api/fin/cartoes/` e exige administrador em todas as operações.
O módulo não grava no fechamento diário nem nas contas a receber existentes.

Valores monetários são inteiros em centavos, calculados com Decimal. Em 2x,
a taxa total é arredondada antes da divisão; as parcelas preservam o bruto,
a taxa e o líquido totais. A venda mantém uma cópia da condição aplicada,
mesmo se as condições comerciais mudarem. Sem condição vigente, a venda fica
pendente e não gera datas ou valores líquidos estimados.

O total diário é único por data, operadora, modalidade e bandeira normalizada.
A inclusão usa `run_operation` e a interface conserva a chave da tentativa
quando a resposta se perde, inclusive após recarregar a aba. Gravações e
auditoria compartilham a mesma transação. Recebimento de zero também é um
recebimento: protege a venda contra edição/exclusão até ser estornado.

Parcelas são filtradas pelo mês previsto; recebido no mês usa a data real,
mesmo para parcelas previstas em outro mês. Diferenças em parcelas recebidas
não permanecem no saldo em aberto. A agenda agrega todas as datas do filtro
de operadora. Dias úteis excluem somente fins de semana; feriados podem ser
ajustados manualmente na previsão. O relatório PDF usa a impressão do navegador,
com Inter local e texto escapado. Não há dependências de Excel ou importação.
