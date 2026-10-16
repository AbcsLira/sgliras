"""Rotas: auth."""
from flask import render_template, request, jsonify, session, redirect
from ..banco_dados import get_db
from ..seguranca import PERFIS, hash_senha, verificar_senha, login_requerido

def login_page():
    if "usuario_id" in session: return redirect("/")
    return render_template("entrar.html")

@login_requerido
def index(): return render_template("principal.html")

def api_login():
    d = request.get_json(silent=True)
    session.clear()
    if not isinstance(d, dict) or not all(isinstance(d.get(k), str) for k in ("usuario", "senha")):
        return jsonify({"erro":"Informe usuário e senha"}),400
    db = get_db()
    try:
        u = db.execute("SELECT * FROM usuarios WHERE usuario=? AND ativo=1", (d["usuario"],)).fetchone()
        if not u or u["perfil"] not in PERFIS or not verificar_senha(u["senha"], d["senha"]):
            return jsonify({"erro":"Usuário ou senha inválidos"}),401
        # Atualiza hashes antigos somente após autenticação válida.
        if not u["senha"].startswith(("pbkdf2:", "scrypt:")):
            db.execute("UPDATE usuarios SET senha=? WHERE id=?", (hash_senha(d["senha"]), u["id"]))
            db.commit()
    finally:
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
    d = request.get_json(silent=True)
    if not isinstance(d, dict) or not all(isinstance(d.get(k), str) for k in ("senha_atual", "senha_nova")) or not d["senha_nova"]:
        return jsonify({"erro":"Informe a senha atual e a nova senha"}),400
    db = get_db()
    try:
        u = db.execute("SELECT senha FROM usuarios WHERE id=?", (session["usuario_id"],)).fetchone()
        if not u:
            session.clear()
            return jsonify({"erro":"Não autenticado"}),401
        if not verificar_senha(u["senha"], d["senha_atual"]):
            return jsonify({"erro":"Senha atual incorreta"}),400
        db.execute("UPDATE usuarios SET senha=? WHERE id=?", (hash_senha(d["senha_nova"]), session["usuario_id"]))
        db.commit()
        return jsonify({"ok":True})
    finally:
        db.close()


def register_routes(app):
    app.route("/login")(login_page)
    app.route("/")(index)
    app.route("/api/auth/login", methods=["POST"])(api_login)
    app.route("/api/auth/logout",methods=["POST"])(api_logout)
    app.route("/api/auth/me")(api_me)
    app.route("/api/auth/senha",methods=["PUT"])(alterar_senha)
