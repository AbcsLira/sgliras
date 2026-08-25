# S.G. Lira's — Sistema de Gestão

Sistema de gestão desenvolvido sob medida para uma lanchonete, cobrindo controle de estoque, inventário físico, fichas de custo e um módulo financeiro completo. Construído como uma aplicação web local, acessível pela rede interna do estabelecimento.

## ✨ Funcionalidades

### 📦 Estoque
- Cadastro de produtos com categorias, unidades e conversão para fardo/caixa
- Movimentações de entrada, saída e ajuste, com histórico completo
- Entrada e saída em lote (múltiplos produtos de uma vez)
- Alertas automáticos de estoque baixo e produtos próximos do vencimento
- Listagem para impressão com filtros por categoria, nome e situação de estoque

### 🔢 Inventário Físico
- Contagem estruturada por categoria, com progresso salvo a qualquer momento
- Histórico completo de inventários, com divergências registradas
- Ajuste automático do estoque ao finalizar

### 🧾 Fichas de Custo
- Cálculo de custo de produção por receita/ficha
- Vínculo com custos fixos e histórico de variação de preço
- Comparativo entre fichas

### 🏢 Fornecedores
- Cadastro com vínculo a produtos e preços específicos
- Geração de lista de compras por fornecedor

### 💰 Financeiro
- Fechamento diário de caixa (cartões, PIX, dinheiro, delivery, frete)
- Contas a pagar e a receber, com categorias personalizáveis e parcelamento
- Controle de fornecimento e pagamento de itens recorrentes (ex: pães, insumos por peso)
- Metas mensais de venda com acompanhamento visual
- Relatórios: resumo mensal, comparativo mês a mês, comparativo de finais de semana, resultado do período

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

Na primeira execução, o banco de dados e as tabelas são criados automaticamente, junto com um usuário administrador padrão — configure a senha em `config.ini` antes do primeiro acesso.

## 📁 Estrutura do projeto

```
sg-liras/
├── app.py                  # Aplicação Flask (rotas, lógica de negócio, banco)
├── config.ini               # Configurações do servidor
├── templates/
│   ├── index.html            # Interface principal (SPA)
│   └── login.html            # Tela de login
├── static/
│   └── fonts/                # Fontes tipográficas
└── backups/                # Backups automáticos do banco
```

## 📌 Sobre o projeto

Desenvolvido de forma incremental para atender necessidades reais de operação de uma lanchonete de pequeno porte — sem dependência de serviços externos, rodando inteiramente na rede local do estabelecimento.

## 🤖 Sobre o desenvolvimento

Este projeto foi desenvolvido com apoio de IA (Claude, da Anthropic) para a implementação de código, com especificação de requisitos, testes, validação e decisões de produto conduzidos por mim ao longo de todo o processo.

## 📄 Licença

Este projeto é disponibilizado publicamente apenas para fins de portfólio e demonstração técnica. Todos os direitos reservados — consulte o arquivo [LICENSE](LICENSE) para mais detalhes.

---

<p align="center">Feito com 🍔 para a gestão do dia a dia.</p>
