"""Fábrica da aplicação S.G. Lira's."""
from flask import Flask
from .config import ROOT_DIR, DB_PATH, BACKUP_DIR, load_secret_key

def create_app(test_config=None):
    app = Flask(__name__, template_folder=str(ROOT_DIR / 'templates'), static_folder=str(ROOT_DIR / 'static'))
    app.config.update(DATABASE=DB_PATH, BACKUP_DIR=BACKUP_DIR)
    if test_config:
        app.config.update(test_config)
    if not app.config.get('SECRET_KEY'):
        app.config['SECRET_KEY'] = load_secret_key()
    from .routes import register_routes
    register_routes(app)
    return app
