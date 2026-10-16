"""Perfis, senhas e controle de acesso."""
import hashlib
from functools import wraps
from flask import session, request, jsonify, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash


PERFIS = {
    "admin":      {"label":"Administrador","permissoes":["dashboard","produtos","movimentacoes","fichas","usuarios","financeiro"]},
    "estoquista": {"label":"Estoquista",   "permissoes":["dashboard","produtos","movimentacoes"]},
    "caixa":      {"label":"Caixa",        "permissoes":["dashboard","movimentacoes"]},
}

def hash_senha(s): return generate_password_hash(s)

def _hash_legado_sha256(s): return hashlib.sha256(s.encode()).hexdigest()

def verificar_senha(hash_armazenado, senha_fornecida):
    """Verifica a senha contra o hash salvo. Suporta tanto o formato novo
    (werkzeug, com salt) quanto o formato antigo (SHA-256 puro, sem salt),
    para não travar o acesso de usuários criados antes da migração."""
    if not isinstance(hash_armazenado, str) or not isinstance(senha_fornecida, str):
        return False
    if hash_armazenado.startswith(("pbkdf2:", "scrypt:")):
        try:
            return check_password_hash(hash_armazenado, senha_fornecida)
        except (ValueError, TypeError):
            return False
    # Hash no formato legado (sha256 hex puro, sem salt)
    return hash_armazenado == _hash_legado_sha256(senha_fornecida)

def login_requerido(f):
    @wraps(f)
    def dec(*a,**kw):
        # A sessão identifica o usuário, mas seu perfil e situação atuais vêm
        # sempre do banco: uma alteração administrativa vale no próximo acesso.
        from .banco_dados import get_db

        usuario_id = session.get("usuario_id")
        usuario = None
        if isinstance(usuario_id, int) and not isinstance(usuario_id, bool) and usuario_id > 0:
            db = get_db()
            try:
                usuario = db.execute(
                    "SELECT id,nome,usuario,perfil,ativo FROM usuarios WHERE id=?",
                    (usuario_id,),
                ).fetchone()
            finally:
                db.close()
        if usuario is None or usuario["ativo"] != 1 or usuario["perfil"] not in PERFIS:
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"erro":"Não autenticado"}),401
            return redirect(url_for("login_page"))
        session.update({
            "usuario_id": usuario["id"], "usuario": usuario["usuario"],
            "nome": usuario["nome"], "perfil": usuario["perfil"],
        })
        return f(*a,**kw)
    return dec

def permissao_requerida(perm):
    def decorator(f):
        @wraps(f)
        def dec(*a,**kw):
            if perm not in PERFIS.get(session.get("perfil",""),{}).get("permissoes",[]):
                return jsonify({"erro":"Sem permissão"}),403
            return f(*a,**kw)
        return dec
    return decorator

def somente_admin():
    """Retorna erro 403 se o usuário não for admin, ou None se ok."""
    if session.get("perfil") != "admin":
        return jsonify({"erro": "Apenas o administrador pode acessar o módulo financeiro"}), 403
    return None
