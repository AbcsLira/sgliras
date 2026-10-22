# S.G. Lira's — Sistema de Gestão

Sistema de gestão desenvolvido sob medida para uma lanchonete, cobrindo controle de estoque, inventário físico, fichas de custo e um módulo financeiro completo. Construído como uma aplicação web local, acessível pela rede interna do estabelecimento.

## Tela de Login
<img width="1600" height="950" alt="00_login" src="https://github.com/user-attachments/assets/36301319-9932-463b-8235-7cd06c995212" />


## Dashboard
<img width="1600" height="950" alt="01_dashboard" src="https://github.com/user-attachments/assets/6e491f6e-2a51-4c1a-9b0c-8e9378476eec" />


## ✨ Funcionalidades

### 📦 Estoque
- Cadastro de produtos com categorias, unidades e conversão para fardo/caixa
- Movimentações de entrada, saída e ajuste, com histórico completo
- Entrada e saída em lote (múltiplos produtos de uma vez)
- Alertas automáticos de estoque baixo e produtos próximos do vencimento
- Listagem para impressão com filtros por categoria, nome e situação de estoque

<img width="1600" height="950" alt="02_produtos" src="https://github.com/user-attachments/assets/f5e615a2-cbd3-45f2-b398-fa75ffc20405" />

### 🔢 Inventário Físico
- Contagem estruturada por categoria, com progresso salvo a qualquer momento
- Histórico completo de inventários, com divergências registradas
- Ajuste automático do estoque ao finalizar

<img width="1600" height="950" alt="05_inventario" src="https://github.com/user-attachments/assets/3fe44a70-c6b7-46af-9a17-b26db96b4685" />


### 🧾 Fichas de Custo
- Cálculo de custo de produção por receita/ficha
- Vínculo com custos fixos e histórico de variação de preço
- Comparativo entre fichas

<img width="1600" height="950" alt="04_fichas" src="https://github.com/user-attachments/assets/e67a9d14-4fe3-4b7f-a927-a402cc000035" />


### 🏢 Fornecedores
- Cadastro com vínculo a produtos e preços específicos
- Geração de lista de compras por fornecedor

### 💰 Financeiro
- Fechamento diário de caixa (cartões, PIX, dinheiro, delivery, frete)
- Contas a pagar e a receber, com categorias personalizáveis e parcelamento
- Controle de fornecimento e pagamento de itens recorrentes (ex: pães, insumos por peso)
- Metas mensais de venda com acompanhamento visual
- Relatórios: resumo mensal, comparativo mês a mês, comparativo de finais de semana, resultado do período
- Cartões e recebíveis independente do fechamento diário: Cielo, Rede e Sipag,
  com taxas por vigência, conciliação manual e relatório para impressão/PDF.

<img width="1600" height="950" alt="06_fechamento_diario" src="https://github.com/user-attachments/assets/5071b4df-61bb-47c5-a0fe-9d83d2c7ac5a" />

### 🔐 Administração
- Perfis de usuário com permissões (admin, estoquista, caixa)
- Log de auditoria de ações administrativas
- Backup automático diário com verificação de integridade

## 🛠️ Stack Tecnológica

| Camada | Tecnologia |
|---|---|
| Backend | Python 3 + Flask |
| Banco de dados | SQLite (modo WAL) |
| Frontend | HTML + CSS + JavaScript (vanilla, sem frameworks) |
| Servidor de produção | Waitress |

## 🚀 Como rodar localmente

```bash
# Clonar o repositório
git clone https://github.com/seu-usuario/sg-liras.git
cd sg-liras

# Instalar dependências
pip install flask waitress

# Iniciar o servidor
python app.py
```

O sistema ficará disponível em `http://localhost:8888` (ou na porta configurada em `config.ini`).

Na primeira execução, o banco de dados e as tabelas são criados automaticamente,
junto com o usuário `admin` e uma senha aleatória. A senha aparece no terminal
somente nessa primeira criação: anote-a antes de fechar a janela e altere-a na
aplicação após entrar. Atualizações e reinicializações preservam os usuários e
as senhas existentes.

Para backup externo no Windows, use `backup_externo.bat` (ajuste a unidade de
destino no arquivo). Ele chama `backup_banco.py`, que usa a API de backup do
SQLite e inclui os dados confirmados que ainda estão no WAL, mesmo com o
servidor em uso. Para escolher um destino manualmente, execute
`python backup_banco.py "caminho/do/backup.db"`.
O destino deve ser um arquivo novo. Para gerar automaticamente um nome com
data, hora e microssegundos, use `python backup_banco.py --pasta "caminho/da/pasta"`.

## 📁 Estrutura do projeto

```
sg-liras/
├── app.py                   # Entrada do servidor
├── sgliras/                 # Backend dividido por responsabilidade
│   ├── rotas/               # Rotas separadas por módulo
│   ├── banco_dados.py       # Schema, migrações e conexões
│   ├── seguranca.py         # Autenticação e permissões
│   └── copias_seguranca.py  # Backup e integridade
├── templates/               # HTML da aplicação e do login
├── static/                  # CSS e JavaScript por módulo
├── testes/                   # Testes de regressão com bancos temporários
├── config.ini               # Configuração local (não versionada)
└── backups/                 # Backups locais (não versionados)
```

Veja [ARQUITETURA.md](ARQUITETURA.md) para o mapa dos módulos e os comandos de teste.

## Cartões e recebíveis

No menu Financeiro, abra **Cartões e recebíveis**. O módulo é acessível aos
administradores e funciona mesmo sem preencher o fechamento diário. Os
lançamentos não são somados automaticamente às contas ou ao fechamento,
evitando duplicar os valores já registrados nesses módulos.

1. Em **Taxas e prazos**, cadastre as condições contratadas: operadora,
   modalidade, taxa, início da vigência e prazo de repasse. A bandeira é
   opcional; em branco, a condição serve como padrão. Uma condição específica
   vigente tem prioridade sobre o padrão.
2. Em **Vendas**, informe o total bruto por dia, operadora, modalidade e
   bandeira. São aceitos débito, crédito à vista, crédito em 2x e voucher,
   sem antecipação. Em 2x, informe também o intervalo contratado entre parcelas.
3. Em **Recebíveis**, acompanhe a agenda mensal, registre o valor e a data
   realmente recebidos e confira diferenças. Um recebimento com diferença
   liquida a parcela e aparece destacado; para corrigir, estorne e registre
   novamente. Vendas com recebimentos exigem estorno antes de editar ou excluir.

Taxas e prazos não são presumidos. É possível lançar vendas antes de configurá-los:
elas ficam sinalizadas e não entram na previsão até usar **Calcular vendas
pendentes**. Vendas já calculadas preservam a condição aplicada na época;
cadastrar uma nova taxa não muda o histórico. Editar explicitamente uma venda
ainda não recebida recalcula sua previsão. Taxa zero também é válida.

O filtro mensal das parcelas usa a **data prevista**; o total **recebido no mês**
usa a data real de recebimento, inclusive de parcelas previstas em outros meses.
A agenda mostra todos os meses com previsões ou recebimentos da operadora
selecionada. Dias úteis consideram segunda a sexta, sem calendário de feriados;
a data prevista de uma parcela em aberto pode ser ajustada conforme a operadora.

Use **Gerar PDF** e escolha **Salvar como PDF** no diálogo de impressão do
navegador. O relatório inclui resumo, parcelas, diferenças, agenda mensal e
pendências de configuração, identificando Cielo em azul, Rede em laranja e
Sipag em verde, sempre acompanhadas dos nomes. O preenchimento é manual;
nesta versão não há importação de planilhas ou de arquivos das operadoras.

## 📌 Sobre o projeto

Desenvolvido de forma incremental para atender necessidades reais de operação de uma lanchonete de pequeno porte — sem dependência de serviços externos, rodando inteiramente na rede local do estabelecimento.

## 🤖 Sobre o desenvolvimento

Este projeto foi desenvolvido com apoio de IA (Claude, da Anthropic) para a implementação de código, com especificação de requisitos, testes, validação e decisões de produto conduzidos por mim ao longo de todo o processo.

## 📄 Licença

Este projeto é disponibilizado publicamente apenas para fins de portfólio e demonstração técnica. Todos os direitos reservados — consulte o arquivo [LICENSE](LICENSE) para mais detalhes.

A fonte Inter incluída em `static/fonts/` segue sua própria licença SIL Open
Font License; consulte os arquivos de licença e origem nessa pasta.

---

<p align="center">Feito com Lira's Lanche🍔 para a gestão do dia a dia.</p>
