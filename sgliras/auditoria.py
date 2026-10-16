"""Auditoria na mesma transação da operação."""
from datetime import datetime
from flask import session

def registrar_auditoria(db, acao, entidade, entidade_id=None, entidade_nome=None, detalhes=None):
    """Registra uma ação administrativa no log de auditoria.
    Usa a mesma conexão db já aberta na rota, sem abrir/fechar conexão própria,
    para que o registro entre na mesma transação da ação principal."""
    db.execute(
        "INSERT INTO log_auditoria (usuario_id,acao,entidade,entidade_id,entidade_nome,detalhes,criado_em) VALUES (?,?,?,?,?,?,?)",
        (session.get("usuario_id"), acao, entidade, entidade_id, entidade_nome, detalhes, datetime.now().isoformat())
    )

def fmt_rs_log(v):
    return "—" if v in (None,0) else f"R${float(v):.2f}"
