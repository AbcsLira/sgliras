"""Rotas: auth."""
from flask import render_template, request, jsonify, session, redirect
from ..database import get_db
from ..security import PERFIS, hash_senha, verificar_senha, login_requerido

def login_page():
    if "usuario_id" in session: return redirect("/")
    return render_template("login.html")

@login_requerido
def index(): return render_template("index.html")

def api_login():
    d=request.get_json(silent=True) or {}; db=get_db()
    u=db.execute("SELECT * FROM usuarios WHERE usuario=? AND ativo=1",(d.get("usuario",""),)).fetchone()
    if not u or not verificar_senha(u["senha"], d.get("senha","")):
        db.close()
        return jsonify({"erro":"Usuário ou senha inválidos"}),401
    # Migração preguiçosa: se a senha ainda está no formato antigo (sem salt),
    # já reescreve para o formato seguro agora que sabemos que a senha está correta.
    if not u["senha"].startswith(("pbkdf2:", "scrypt:")):
        db.execute("UPDATE usuarios SET senha=? WHERE id=?", (hash_senha(d.get("senha","")), u["id"]))
        db.commit()
    db.close()
    session.update({"usuario_id":u["id"],"usuario":u["usuario"],"nome":u["nome"],"perfil":u["perfil"]})
    perms=PERFIS.get(u["perfil"],{}).get("permissoes",[])
    return jsonify({"ok":True,"nome":u["nome"],"perfil":u["perfil"],"perfil_label":PERFIS[u["perfil"]]["label"],"permissoes":perms})

def api_logout(): session.clear(); return jsonify({"ok":True})

@login_requerido
def api_me():
    pf=session.get("perfil",""); perms=PERFIS.get(pf,{}).get("permissoes",[])
    return jsonify({"id":session["usuario_id"],"nome":session["nome"],"usuario":session["usuario"],"perfil":pf,
                    "perfil_label":PERFIS[pf]["label"],"permissoes":perms})

@login_requerido
def alterar_senha():
    d=request.get_json(silent=True) or {}; db=get_db()
    u=db.execute("SELECT senha FROM usuarios WHERE id=?",(session["usuario_id"],)).fetchone()
    if not verificar_senha(u["senha"], d.get("senha_atual","")): db.close(); return jsonify({"erro":"Senha atual incorreta"}),400
    db.execute("UPDATE usuarios SET senha=? WHERE id=?",(hash_senha(d["senha_nova"]),session["usuario_id"]))
    db.commit(); db.close(); return jsonify({"ok":True})


def register_routes(app):
    app.route("/login")(login_page)
    app.route("/")(index)
    app.route("/api/auth/login", methods=["POST"])(api_login)
    app.route("/api/auth/logout",methods=["POST"])(api_logout)
    app.route("/api/auth/me")(api_me)
    app.route("/api/auth/senha",methods=["PUT"])(alterar_senha)
