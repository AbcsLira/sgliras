"""Configuração e caminhos locais da aplicação."""
import configparser
import os
import secrets
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = str(ROOT_DIR / 'estoque.db')
CFG_PATH = str(ROOT_DIR / 'config.ini')
BACKUP_DIR = str(ROOT_DIR / 'backups')

def load_config():
    cfg = configparser.ConfigParser()
    cfg.read(CFG_PATH, encoding="utf-8")
    return {
        "host":  cfg.get("servidor","host",  fallback="127.0.0.1"),
        "porta": cfg.getint("servidor","porta", fallback=5000),
        "debug": cfg.getboolean("servidor","debug", fallback=False),
    }

def load_secret_key():
    cfg = configparser.ConfigParser()
    cfg.read(CFG_PATH, encoding='utf-8')
    key = cfg.get('servidor', 'secret_key', fallback=None)
    if not key:
        key = secrets.token_hex(32)
        if not cfg.has_section('servidor'):
            cfg.add_section('servidor')
        cfg.set('servidor', 'secret_key', key)
        with open(CFG_PATH, 'w', encoding='utf-8') as f:
            cfg.write(f)
        os.chmod(CFG_PATH, 0o600)
    return key
