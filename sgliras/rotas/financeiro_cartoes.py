"""API administrativa de cartões e recebíveis, independente do fechamento."""
from contextlib import closing, contextmanager
from datetime import date
from functools import wraps

from flask import jsonify, request, session

from .. import cartoes
from ..banco_dados import get_db
from ..operacoes import run_operation
from ..seguranca import login_requerido, somente_admin
from ..validacao import json_object


def _administrador(funcao):
    @login_requerido
    @wraps(funcao)
    def rota(*args, **kwargs):
        erro = somente_admin()
        return erro if erro else funcao(*args, **kwargs)
    return rota


@contextmanager
def _transacao():
    with closing(get_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        yield db


@_administrador
def cartoes_configuracao():
    with closing(get_db()) as db:
        return jsonify(cartoes.configuracao(db))


@_administrador
def cartoes_salvar_condicao():
    dados = cartoes.dados_condicao(json_object())
    with _transacao() as db:
        resultado = cartoes.salvar_condicao(db, dados, session["usuario_id"])
    return jsonify(resultado), 201


@_administrador
def cartoes_listar_vendas():
    with closing(get_db()) as db:
        return jsonify(cartoes.listar_vendas(db, request.args.get("mes", ""), request.args.get("operadora", "")))


@_administrador
def cartoes_inserir_venda():
    body = json_object()
    dados = cartoes.dados_venda(body)
    resultado, status = run_operation(body, lambda db: cartoes.inserir_venda(db, dados, session["usuario_id"]))
    return jsonify(resultado), status


@_administrador
def cartoes_editar_venda(vid):
    dados = cartoes.dados_venda(json_object())
    with _transacao() as db:
        resultado = cartoes.editar_venda(db, vid, dados, session["usuario_id"])
    return jsonify(resultado)


@_administrador
def cartoes_excluir_venda(vid):
    with _transacao() as db:
        resultado = cartoes.excluir_venda(db, vid, session["usuario_id"])
    return jsonify(resultado)


@_administrador
def cartoes_calcular_pendentes():
    with _transacao() as db:
        resultado = cartoes.calcular_pendentes(db, session["usuario_id"])
    return jsonify(resultado)


@_administrador
def cartoes_registrar_recebimento(pid):
    body = json_object()
    with _transacao() as db:
        resultado = cartoes.registrar_recebimento(db, pid, body, session["usuario_id"])
    return jsonify(resultado)


@_administrador
def cartoes_estornar_recebimento(pid):
    with _transacao() as db:
        resultado = cartoes.estornar_recebimento(db, pid, session["usuario_id"])
    return jsonify(resultado)


@_administrador
def cartoes_alterar_previsao(pid):
    body = json_object()
    with _transacao() as db:
        resultado = cartoes.alterar_previsao(db, pid, body, session["usuario_id"])
    return jsonify(resultado)


@_administrador
def cartoes_relatorio():
    mes = request.args.get("mes", date.today().isoformat()[:7])
    with closing(get_db()) as db, db:
        db.execute("BEGIN")
        return jsonify(cartoes.relatorio(db, mes, request.args.get("operadora", "")))


def register_routes(app):
    prefixo = "/api/fin/cartoes"
    for caminho, metodos, funcao in (
        ("/configuracao", ["GET"], cartoes_configuracao),
        ("/condicoes", ["POST"], cartoes_salvar_condicao),
        ("/vendas", ["GET"], cartoes_listar_vendas),
        ("/vendas", ["POST"], cartoes_inserir_venda),
        ("/vendas/<int:vid>", ["PUT"], cartoes_editar_venda),
        ("/vendas/<int:vid>", ["DELETE"], cartoes_excluir_venda),
        ("/vendas/calcular-pendentes", ["POST"], cartoes_calcular_pendentes),
        ("/parcelas/<int:pid>/recebimento", ["POST"], cartoes_registrar_recebimento),
        ("/parcelas/<int:pid>/recebimento", ["DELETE"], cartoes_estornar_recebimento),
        ("/parcelas/<int:pid>/previsao", ["PUT"], cartoes_alterar_previsao),
        ("/relatorio", ["GET"], cartoes_relatorio),
    ):
        app.add_url_rule(prefixo + caminho, view_func=funcao, methods=metodos)
