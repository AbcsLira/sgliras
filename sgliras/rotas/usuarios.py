"""Rotas: users."""
from datetime import datetime
from flask import jsonify, session
from ..banco_dados import get_db
from ..seguranca import PERFIS, hash_senha, login_requerido, permissao_requerida
from ..auditoria import registrar_auditoria
from ..validacao import ValidationError, json_object, text


def _dados_usuario(criando=False):
    recebido = json_object()
    dados = {
        "nome": text(recebido.get("nome"), "Nome"),
        "usuario": text(recebido.get("usuario"), "Usuário"),
        "perfil": recebido.get("perfil", "caixa" if criando else None),
        "ativo": recebido.get("ativo", 1),
    }
    if not isinstance(dados["perfil"], str) or dados["perfil"] not in PERFIS:
        raise ValidationError("Selecione um perfil válido.")
    if type(dados["ativo"]) not in (bool, int) or dados["ativo"] not in (0, 1):
        raise ValidationError("Ativo deve ser verdadeiro, falso, 0 ou 1.")
    dados["ativo"] = int(dados["ativo"])
    if criando or "senha" in recebido:
        senha = recebido.get("senha")
        if not isinstance(senha, str) or not senha.strip():
            raise ValidationError("Senha deve ser um texto não vazio.")
        dados["senha"] = hash_senha(senha)
    return dados


def _ultimo_admin_ativo(db, usuario):
    return (usuario["perfil"] == "admin" and usuario["ativo"] == 1 and
            db.execute("SELECT COUNT(*) FROM usuarios WHERE perfil='admin' AND ativo=1").fetchone()[0] <= 1)


def _bloqueio_ultimo_admin():
    return jsonify({"erro": "Mantenha pelo menos um administrador ativo."}), 409

@login_requerido
@permissao_requerida("usuarios")
def listar_usuarios():
    db = get_db()
    try:
        rows = db.execute("SELECT id,nome,usuario,perfil,ativo,criado_em FROM usuarios ORDER BY nome").fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()

@login_requerido
@permissao_requerida("usuarios")
def criar_usuario():
    d = _dados_usuario(criando=True)
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        novo_id = db.execute("INSERT INTO usuarios (nome,usuario,senha,perfil,ativo,criado_em) VALUES (?,?,?,?,?,?)",
                   (d["nome"],d["usuario"],d["senha"],d["perfil"],d["ativo"],datetime.now().isoformat())).lastrowid
        registrar_auditoria(db,"criou","usuario",novo_id,d["nome"],f"login: {d['usuario']}; perfil: {d['perfil']}")
        db.commit(); return jsonify({"ok":True}),201
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@login_requerido
@permissao_requerida("usuarios")
def atualizar_usuario(uid):
    d = _dados_usuario()
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        anterior = db.execute("SELECT nome,usuario,perfil,ativo FROM usuarios WHERE id=?", (uid,)).fetchone()
        if anterior is None:
            db.rollback()
            return jsonify({"erro": "Usuário não encontrado"}), 404
        if (d["perfil"] != "admin" or d["ativo"] != 1) and _ultimo_admin_ativo(db, anterior):
            db.rollback()
            return _bloqueio_ultimo_admin()
        if "senha" in d:
            db.execute("UPDATE usuarios SET nome=?,usuario=?,perfil=?,ativo=?,senha=? WHERE id=?",
                       (d["nome"],d["usuario"],d["perfil"],d["ativo"],d["senha"],uid))
        else:
            db.execute("UPDATE usuarios SET nome=?,usuario=?,perfil=?,ativo=? WHERE id=?",
                       (d["nome"],d["usuario"],d["perfil"],d["ativo"],uid))
        mudancas=[]
        if anterior["nome"]!=d["nome"]:
            mudancas.append(f"nome: {anterior['nome']} → {d['nome']}")
        if anterior["usuario"]!=d["usuario"]:
            mudancas.append(f"login: {anterior['usuario']} → {d['usuario']}")
        if anterior["perfil"]!=d["perfil"]:
            mudancas.append(f"perfil: {anterior['perfil']} → {d['perfil']}")
        if anterior["ativo"]!=d["ativo"]:
            mudancas.append(f"ativo: {'sim' if anterior['ativo'] else 'não'} → {'sim' if d['ativo'] else 'não'}")
        if "senha" in d:
            mudancas.append("senha alterada")
        if mudancas:
            registrar_auditoria(db,"editou","usuario",uid,d["nome"],"; ".join(mudancas))
        db.commit()
        return jsonify({"ok":True})
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@login_requerido
@permissao_requerida("usuarios")
def deletar_usuario(uid):
    db=get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        usuario=db.execute("SELECT nome,perfil,ativo FROM usuarios WHERE id=?",(uid,)).fetchone()
        if usuario is None:
            db.rollback()
            return jsonify({"erro": "Usuário não encontrado"}), 404
        if _ultimo_admin_ativo(db, usuario):
            db.rollback()
            return _bloqueio_ultimo_admin()
        if uid==session["usuario_id"]:
            db.rollback()
            return jsonify({"erro":"Não pode excluir seu próprio usuário"}),400
        db.execute("DELETE FROM usuarios WHERE id=?",(uid,))
        registrar_auditoria(db,"excluiu","usuario",uid,usuario["nome"])
        db.commit()
        return jsonify({"ok":True})
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def register_routes(app):
    app.route("/api/usuarios")(listar_usuarios)
    app.route("/api/usuarios",methods=["POST"])(criar_usuario)
    app.route("/api/usuarios/<int:uid>",methods=["PUT"])(atualizar_usuario)
    app.route("/api/usuarios/<int:uid>",methods=["DELETE"])(deletar_usuario)
