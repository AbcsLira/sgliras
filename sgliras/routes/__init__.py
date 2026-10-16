"""Registro dos módulos, preservando URLs e nomes dos endpoints."""
from . import auth, users, stock, dashboard, recipes, backups, suppliers, inventory, reports, finance_daily, finance_accounts, finance_bread, finance_dough, finance_reports

def register_routes(app):
    auth.register_routes(app)
    users.register_routes(app)
    stock.register_routes(app)
    dashboard.register_routes(app)
    recipes.register_routes(app)
    backups.register_routes(app)
    suppliers.register_routes(app)
    inventory.register_routes(app)
    reports.register_routes(app)
    finance_daily.register_routes(app)
    finance_accounts.register_routes(app)
    finance_bread.register_routes(app)
    finance_dough.register_routes(app)
    finance_reports.register_routes(app)
