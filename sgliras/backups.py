"""Backup consistente e verificação de integridade SQLite."""
import os
import glob
import sqlite3
from contextlib import closing
from datetime import datetime
from flask import current_app

def fazer_backup(motivo="automatico"):
    """Cria uma cópia do banco de dados na pasta backups/.
    Mantém os últimos 30 arquivos, removendo os mais antigos."""
    os.makedirs(current_app.config["BACKUP_DIR"], exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    nome_backup = f"estoque_{timestamp}_{motivo}.db"
    destino = os.path.join(current_app.config["BACKUP_DIR"], nome_backup)
    try:
        # Usa a API nativa de backup do SQLite em vez de copiar o arquivo
        # diretamente: em modo WAL, uma cópia de arquivo pode capturar o
        # banco num estado inconsistente (dados recentes podem estar só
        # no -wal e ainda não gravados no .db principal). src.backup(dst)
        # garante uma cópia íntegra e consistente da transação em curso.
        # O contexto da conexão SQLite só encerra a transação. closing também
        # libera os arquivos, inclusive se abrir o destino ou copiar falhar.
        with closing(sqlite3.connect(current_app.config["DATABASE"])) as src:
            with closing(sqlite3.connect(destino)) as dst, dst:
                src.backup(dst)
    except Exception as e:
        current_app.logger.warning('Falha ao criar backup: %s', e)
        return None

    # Limpeza: mantém só os 30 backups mais recentes
    arquivos = sorted(glob.glob(os.path.join(current_app.config["BACKUP_DIR"], "estoque_*.db")), key=os.path.getmtime)
    while len(arquivos) > 30:
        mais_antigo = arquivos.pop(0)
        try:
            os.remove(mais_antigo)
        except Exception:
            pass

    return nome_backup


def backup_diario_necessario():
    """Verifica se já existe um backup automático feito hoje."""
    os.makedirs(current_app.config["BACKUP_DIR"], exist_ok=True)
    hoje = datetime.now().strftime("%Y-%m-%d")
    for arq in glob.glob(os.path.join(current_app.config["BACKUP_DIR"], f"estoque_{hoje}_*_automatico.db")):
        return False  # já existe backup de hoje
    return True


def verificar_integridade_banco():
    """Roda PRAGMA integrity_check no banco. Retorna (ok, mensagem)."""
    try:
        with closing(sqlite3.connect(current_app.config["DATABASE"])) as conn:
            with closing(conn.execute("PRAGMA integrity_check")) as cursor:
                resultado = cursor.fetchone()
        if resultado and resultado[0] == "ok":
            return True, "ok"
        return False, str(resultado[0] if resultado else "resultado vazio")
    except Exception as e:
        return False, str(e)
