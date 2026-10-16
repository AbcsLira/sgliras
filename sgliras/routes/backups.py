"""Rotas: backups."""
import os
import glob
from datetime import datetime
from flask import jsonify, session, send_file, current_app
from ..security import login_requerido, permissao_requerida
from ..backups import fazer_backup, backup_diario_necessario, verificar_integridade_banco

@login_requerido
@permissao_requerida("usuarios")
def listar_backups():
    os.makedirs(current_app.config["BACKUP_DIR"], exist_ok=True)
    arquivos = sorted(glob.glob(os.path.join(current_app.config["BACKUP_DIR"], "estoque_*.db")), key=os.path.getmtime, reverse=True)
    res = []
    for a in arquivos:
        nome = os.path.basename(a)
        tamanho_kb = round(os.path.getsize(a) / 1024, 1)
        modificado = datetime.fromtimestamp(os.path.getmtime(a)).strftime("%d/%m/%Y %H:%M:%S")
        res.append({"nome": nome, "tamanho_kb": tamanho_kb, "criado_em": modificado})
    return jsonify(res)


@login_requerido
@permissao_requerida("usuarios")
def criar_backup_manual():
    nome = fazer_backup(motivo="manual")
    if not nome:
        return jsonify({"erro": "Falha ao criar backup"}), 500
    return jsonify({"ok": True, "nome": nome}), 201


@login_requerido
@permissao_requerida("usuarios")
def baixar_backup(nome):
    # Proteção contra path traversal
    nome_seguro = os.path.basename(nome)
    caminho = os.path.join(current_app.config["BACKUP_DIR"], nome_seguro)
    if not os.path.isfile(caminho) or not nome_seguro.startswith("estoque_"):
        return jsonify({"erro": "Backup não encontrado"}), 404
    return send_file(caminho, as_attachment=True, download_name=nome_seguro)


@login_requerido
def status_backup():
    """Retorna status atual dos backups e integridade do banco."""
    if session.get("perfil") != "admin":
        return jsonify({"erro": "Apenas administradores"}), 403
    banco_ok, banco_msg = verificar_integridade_banco()
    arquivos_backup = sorted(
        glob.glob(os.path.join(current_app.config["BACKUP_DIR"], "estoque_*.db")),
        key=os.path.getmtime, reverse=True
    )
    ultimo_backup = None
    if arquivos_backup:
        mtime = os.path.getmtime(arquivos_backup[0])
        ultimo_backup = datetime.fromtimestamp(mtime).isoformat()
    tamanho_banco = os.path.getsize(current_app.config["DATABASE"]) if os.path.exists(current_app.config["DATABASE"]) else 0
    return jsonify({
        "banco_ok": banco_ok,
        "banco_msg": banco_msg,
        "tamanho_banco_kb": round(tamanho_banco / 1024, 1),
        "total_backups_internos": len(arquivos_backup),
        "ultimo_backup": ultimo_backup,
        "backup_hoje": not backup_diario_necessario(),
    })



def register_routes(app):
    app.route("/api/backups")(listar_backups)
    app.route("/api/backups", methods=["POST"])(criar_backup_manual)
    app.route("/api/backups/<nome>")(baixar_backup)
    app.route("/api/status-backup")(status_backup)
