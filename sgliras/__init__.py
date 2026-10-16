"""Fábrica da aplicação S.G. Lira's."""
import sqlite3
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException
from .config import ROOT_DIR, DB_PATH, BACKUP_DIR, load_secret_key
from .validation import ValidationError

def create_app(test_config=None):
    app = Flask(__name__, template_folder=str(ROOT_DIR / 'templates'), static_folder=str(ROOT_DIR / 'static'))
    app.config.update(DATABASE=DB_PATH, BACKUP_DIR=BACKUP_DIR)
    if test_config:
        app.config.update(test_config)
    if not app.config.get('SECRET_KEY'):
        app.config['SECRET_KEY'] = load_secret_key()
    from .routes import register_routes
    from .database import close_connections
    register_routes(app)
    app.teardown_appcontext(close_connections)

    @app.errorhandler(ValidationError)
    def invalid_input(error):
        return jsonify(erro=str(error)), 400

    @app.errorhandler(sqlite3.IntegrityError)
    def integrity_error(error):
        app.logger.warning('Operação recusada por integridade do banco: %s', error)
        return jsonify(erro='O registro está duplicado ou possui vínculos que impedem esta operação.',
                       codigo='integridade'), 409

    @app.errorhandler(sqlite3.OperationalError)
    def database_error(error):
        code = getattr(error, 'sqlite_errorcode', 0)
        if (code & 0xff) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            return jsonify(erro='O banco está ocupado. Aguarde e tente novamente.'), 503, {'Retry-After': '2'}
        app.logger.exception('Falha na operação do banco')
        return jsonify(erro='Não foi possível concluir a operação. Consulte o log do servidor.'), 500

    @app.errorhandler(HTTPException)
    def http_error(error):
        if request.path.startswith('/api/'):
            return jsonify(erro=error.description), error.code
        return error

    return app
