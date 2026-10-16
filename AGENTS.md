# Orientações do projeto

- No backend, use português nos nomes de novos arquivos e módulos, sem acentos
  ou espaços, preferindo `snake_case`: `estoque.py`, `financeiro_contas.py`.
- Na interface, preserve os nomes em inglês: `index.html`, `login.html`,
  `index.css`, `login.css` e `login.js`.
- Os módulos em `static/js/modules/` usam nomes em português, como `produtos.js`,
  `movimentacoes.js` e `inventario.js`. Preserve o nome da pasta `modules/`.
- Preserve os nomes convencionais das ferramentas: `app.py`, `__init__.py`,
  `requirements.txt`, `README.md`, `static/`, `templates/` e `.github/workflows/`.
- Escreva mensagens de commit em português.
- Uma renomeação de arquivos deve atualizar imports, referências da interface,
  mocks, comandos da CI e documentação; preserve as APIs e os dados existentes.
- Os testes ficam em `testes/`; use `teste_*.py`, descoberto pelo padrão
  `test*.py` do unittest. Comandos na raiz do repositório:
  - `python -m unittest discover -s testes -v`
  - `node testes/estabilidade_interface.cjs`
- Consulte `ARQUITETURA.md` para o mapa de módulos e o fluxo de desenvolvimento.
