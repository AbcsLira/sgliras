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
    if hash_armazenado.startswith(("pbkdf2:", "scrypt:")):
        return check_password_hash(hash_armazenado, senha_fornecida)
    # Hash no formato legado (sha256 hex puro, sem salt)
    return hash_armazenado == _hash_legado_sha256(senha_fornecida)

def login_requerido(f):
    @wraps(f)
    def dec(*a,**kw):
        if "usuario_id" not in session:
            if request.path.startswith("/api/"): return jsonify({"erro":"Não autenticado"}),401
            return redirect(url_for("login_page"))
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
