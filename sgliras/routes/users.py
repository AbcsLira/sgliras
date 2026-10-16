"""Rotas: users."""
import sqlite3
from datetime import datetime
from flask import request, jsonify, session
from ..database import get_db
from ..security import hash_senha, login_requerido, permissao_requerida
from ..audit import registrar_auditoria

@login_requerido
@permissao_requerida("usuarios")
def listar_usuarios():
    db=get_db(); rows=db.execute("SELECT id,nome,usuario,perfil,ativo,criado_em FROM usuarios ORDER BY nome").fetchall(); db.close()
    return jsonify([dict(r) for r in rows])

@login_requerido
@permissao_requerida("usuarios")
def criar_usuario():
    d=request.get_json(silent=True) or {}; db=get_db()
    try:
        db.execute("INSERT INTO usuarios (nome,usuario,senha,perfil,ativo,criado_em) VALUES (?,?,?,?,?,?)",
                   (d["nome"],d["usuario"],hash_senha(d["senha"]),d.get("perfil","caixa"),1,datetime.now().isoformat()))
        novo_id=db.execute("SELECT id FROM usuarios WHERE usuario=?",(d["usuario"],)).fetchone()["id"]
        registrar_auditoria(db,"criou","usuario",novo_id,d["nome"],f"login: {d['usuario']}; perfil: {d.get('perfil','caixa')}")
        db.commit(); return jsonify({"ok":True}),201
    except sqlite3.IntegrityError: return jsonify({"erro":"Nome de usuário já existe"}),400
    finally: db.close()

@login_requerido
@permissao_requerida("usuarios")
def atualizar_usuario(uid):
    d=request.get_json(silent=True) or {}; db=get_db()
    anterior=db.execute("SELECT nome,usuario,perfil,ativo FROM usuarios WHERE id=?",(uid,)).fetchone()
    if d.get("senha"):
        db.execute("UPDATE usuarios SET nome=?,usuario=?,perfil=?,ativo=?,senha=? WHERE id=?",
                   (d["nome"],d["usuario"],d["perfil"],d.get("ativo",1),hash_senha(d["senha"]),uid))
    else:
        db.execute("UPDATE usuarios SET nome=?,usuario=?,perfil=?,ativo=? WHERE id=?",
                   (d["nome"],d["usuario"],d["perfil"],d.get("ativo",1),uid))
    if anterior:
        mudancas=[]
        if anterior["nome"]!=d["nome"]:
            mudancas.append(f"nome: {anterior['nome']} → {d['nome']}")
        if anterior["usuario"]!=d["usuario"]:
            mudancas.append(f"login: {anterior['usuario']} → {d['usuario']}")
        if anterior["perfil"]!=d["perfil"]:
            mudancas.append(f"perfil: {anterior['perfil']} → {d['perfil']}")
        if anterior["ativo"]!=d.get("ativo",1):
            mudancas.append(f"ativo: {'sim' if anterior['ativo'] else 'não'} → {'sim' if d.get('ativo',1) else 'não'}")
        if d.get("senha"):
            mudancas.append("senha alterada")
        if mudancas:
            registrar_auditoria(db,"editou","usuario",uid,d["nome"],"; ".join(mudancas))
    db.commit(); db.close(); return jsonify({"ok":True})

@login_requerido
@permissao_requerida("usuarios")
def deletar_usuario(uid):
    if uid==session["usuario_id"]: return jsonify({"erro":"Não pode excluir seu próprio usuário"}),400
    db=get_db()
    try:
        usuario=db.execute("SELECT nome FROM usuarios WHERE id=?",(uid,)).fetchone()
        db.execute("DELETE FROM usuarios WHERE id=?",(uid,))
        if usuario:
            registrar_auditoria(db,"excluiu","usuario",uid,usuario["nome"])
        db.commit()
        return jsonify({"ok":True})
    except Exception as e:
        db.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        db.close()


def register_routes(app):
    app.route("/api/usuarios")(listar_usuarios)
    app.route("/api/usuarios",methods=["POST"])(criar_usuario)
    app.route("/api/usuarios/<int:uid>",methods=["PUT"])(atualizar_usuario)
    app.route("/api/usuarios/<int:uid>",methods=["DELETE"])(deletar_usuario)
