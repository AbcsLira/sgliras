"""Registro dos módulos, preservando URLs e nomes dos endpoints."""
from . import autenticacao, usuarios, estoque, painel, receitas, copias_seguranca, fornecedores, inventario, relatorios, financeiro_diario, financeiro_contas, financeiro_paes, financeiro_massas, financeiro_relatorios

def register_routes(app):
    autenticacao.register_routes(app)
    usuarios.register_routes(app)
    estoque.register_routes(app)
    painel.register_routes(app)
    receitas.register_routes(app)
    copias_seguranca.register_routes(app)
    fornecedores.register_routes(app)
    inventario.register_routes(app)
    relatorios.register_routes(app)
    financeiro_diario.register_routes(app)
    financeiro_contas.register_routes(app)
    financeiro_paes.register_routes(app)
    financeiro_massas.register_routes(app)
    financeiro_relatorios.register_routes(app)
