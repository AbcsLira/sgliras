# Organização do projeto

O comando de inicialização continua sendo `python app.py`. No Windows, os
arquivos `iniciar.bat` e `iniciar_segundo_plano.bat` continuam usando essa entrada.
Execute os comandos na raiz do checkout.

## Backend

- `app.py`: entrada do servidor, inicialização do banco e backup diário.
- `sgliras/__init__.py`: `create_app()`, configuração Flask e registro das rotas.
- `sgliras/config.py`: caminhos, leitura de `config.ini` e chave de sessão.
- `sgliras/database.py`: schema, migrações existentes e conexões SQLite.
- `sgliras/security.py`: perfis, hashes de senha e controle de acesso.
- `sgliras/audit.py`: registro de auditoria dentro da transação da operação.
- `sgliras/backups.py`: backup SQLite e verificação de integridade.
- `sgliras/routes/`: autenticação, usuários, estoque, dashboard, receitas,
  fornecedores, inventário, relatórios e administração de backups.
- `sgliras/routes/finance_*.py`: fechamento diário, contas, pães, massas e relatórios.

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

Os scripts são carregados na ordem declarada em `templates/index.html`.
Continuam sendo scripts clássicos: os manipuladores usados por `onclick` e o
estado compartilhado da interface foram preservados. `core.js` contém o estado
comum e `shell.js`, carregado por último, chama `init()`. Não use `async`, nem
altere a ordem sem revisar as dependências. Os estilos e scripts das janelas
de impressão continuam nos templates de impressão gerados pelo JavaScript.
Não há etapa de build do frontend.

## Instalação e testes

```sh
python -m venv venv
# Linux/macOS: source venv/bin/activate
# Windows: venv\Scripts\activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python app.py
```

Os testes usam diretórios temporários, sem acessar o banco real. A referência
`tests/fixtures/legacy_http.json` foi capturada antes da refatoração: cobre o
mapa de rotas e 180 consultas GET, incluindo acesso anônimo e os três perfis.
Somente os campos de horário de criação/geração são normalizados. Outros testes
cobrem login, sessão, arquivos estáticos, estoque, custo de receita, pagamento,
backup íntegro, reinicialização do schema e isolamento entre aplicações.

O banco `estoque.db`, seus arquivos WAL/SHM, `config.ini` e `backups/` permanecem
na raiz e são ignorados pelo Git. Não apague WAL/SHM manualmente.
