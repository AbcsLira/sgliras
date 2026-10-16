"""Rotas: finance accounts."""
from contextlib import closing
from datetime import datetime
import sqlite3
from flask import abort, request, jsonify, session
from ..banco_dados import get_db
from ..operacoes import run_operation
from ..seguranca import login_requerido, somente_admin
from ..validacao import ValidationError, iso_date, json_object, number, text


def _dados_conta(d, db, *, receber=False):
    """Valida a conta inteira antes de qualquer escrita, inclusive suas referências."""
    if not isinstance(d, dict):
        raise ValidationError("Cada conta deve ser um objeto JSON.")
    descricao = text(d.get("descricao"), "Descrição")
    valor = number(d.get("valor"), "Valor", minimum=0)
    if valor == 0:
        raise ValidationError("Valor deve ser maior que zero.")
    vencimento = iso_date(d.get("vencimento"), "Vencimento")
    categoria = text(d.get("categoria", "Outros"), "Categoria")
    if receber:
        categoria_existe = categoria in CATS_RECEBER
    else:
        categoria_existe = db.execute(
            "SELECT 1 FROM fin_categorias_pagar WHERE nome=?", (categoria,)
        ).fetchone()
    if not categoria_existe:
        raise ValidationError("Categoria não encontrada.")
    fornecedor_id = d.get("fornecedor_id")
    if fornecedor_id is None or fornecedor_id == "":
        fornecedor_id = None
    else:
        fornecedor_id = number(fornecedor_id, "Fornecedor", minimum=1, integer=True)
        if not db.execute("SELECT 1 FROM fornecedores WHERE id=?", (fornecedor_id,)).fetchone():
            raise ValidationError("Fornecedor não encontrado.")
    return (descricao, valor, vencimento, categoria, fornecedor_id,
            text(d.get("observacao"), "Observação", required=False))


def _inserir_conta_pagar(db, dados):
    descricao, valor, vencimento, categoria, fornecedor_id, observacao = dados
    return db.execute(
        """INSERT INTO fin_contas_pagar
           (descricao,valor,vencimento,status,categoria,fornecedor_id,observacao,usuario_id,criado_em)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (descricao, valor, vencimento, "aberto", categoria, fornecedor_id, observacao,
         session["usuario_id"], datetime.now().isoformat())
    ).lastrowid


def _conta_pagar(db, cid):
    conta = db.execute("SELECT * FROM fin_contas_pagar WHERE id=?", (cid,)).fetchone()
    if not conta:
        abort(404, description="Conta não encontrada")
    return conta


def _proteger_conta_vinculada(db, conta):
    """Contas geradas por outro módulo devem ser editadas na sua origem."""
    if db.execute("SELECT 1 FROM fin_massa_entregas WHERE conta_pagar_id=?", (conta["id"],)).fetchone():
        abort(409, description="Esta conta está vinculada a uma entrega. Use o módulo de massas.")
    paes = db.execute("SELECT 1 FROM fin_paes_pagamento WHERE conta_pagar_id=?", (conta["id"],)).fetchone()
    # As contas individuais legadas de pães usam a descrição como vínculo.
    if conta["descricao"].startswith("Pães — "):
        try:
            iso_date(conta["descricao"][7:], "Data")
            paes = True
        except ValidationError:
            pass
    if paes:
        abort(409, description="Esta conta está vinculada a pães. Use o módulo de pães.")

@login_requerido
def listar_contas_pagar():
    err = somente_admin()
    if err: return err
    status    = request.args.get("status", "")
    categoria = request.args.get("categoria", "")
    mes       = request.args.get("mes", "")
    fornecedor_id = request.args.get("fornecedor_id", "")

    where, params = ["1=1"], []
    if status:
        where.append("cp.status=?"); params.append(status)
    if categoria:
        where.append("cp.categoria=?"); params.append(categoria)
    if mes:
        where.append("(cp.vencimento LIKE ? OR cp.pago_em LIKE ?)"); params += [f"{mes}%", f"{mes}%"]
    if fornecedor_id:
        where.append("cp.fornecedor_id=?")
        params.append(number(fornecedor_id, "Fornecedor", minimum=1, integer=True))

    with closing(get_db()) as db:
        rows = db.execute(f"""
            SELECT cp.*, f.nome AS fornecedor_nome
            FROM fin_contas_pagar cp
            LEFT JOIN fornecedores f ON f.id=cp.fornecedor_id
            WHERE {' AND '.join(where)}
            ORDER BY cp.vencimento ASC
        """, params).fetchall()
    return jsonify([dict(r) for r in rows])


@login_requerido
def editar_conta_pagar(cid):
    err = somente_admin()
    if err: return err
    d = json_object()
    with closing(get_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        conta = _conta_pagar(db, cid)
        _proteger_conta_vinculada(db, conta)
        dados = _dados_conta(d, db)
        db.execute("""UPDATE fin_contas_pagar SET
            descricao=?, valor=?, vencimento=?, categoria=?,
            fornecedor_id=?, observacao=? WHERE id=?""", (*dados, cid))
    return jsonify({"ok": True})


@login_requerido
def resumo_categorias_pagar():
    """Retorna totais agrupados por categoria para o período/status informado."""
    err = somente_admin()
    if err: return err
    db = get_db()
    mes    = request.args.get("mes", "")
    status = request.args.get("status", "")

    where, params = ["1=1"], []
    if mes:
        where.append("(vencimento LIKE ? OR pago_em LIKE ?)"); params += [f"{mes}%", f"{mes}%"]
    if status:
        where.append("status=?"); params.append(status)

    rows = db.execute(f"""
        SELECT categoria,
               COUNT(*) AS total_contas,
               SUM(valor) AS total_valor,
               SUM(CASE WHEN status='pago' THEN valor ELSE 0 END) AS total_pago,
               SUM(CASE WHEN status='aberto' THEN valor ELSE 0 END) AS total_aberto
        FROM fin_contas_pagar
        WHERE {' AND '.join(where)}
        GROUP BY categoria ORDER BY total_valor DESC
    """, params).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@login_requerido
def criar_conta_pagar():
    err = somente_admin()
    if err: return err
    d = json_object()
    with closing(get_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        _inserir_conta_pagar(db, _dados_conta(d, db))
    return jsonify({"ok": True}), 201


@login_requerido
def criar_contas_pagar_lote():
    """Salva todas as parcelas uma vez, mesmo quando o cliente precisa repetir."""
    err = somente_admin()
    if err: return err
    d = json_object()
    itens = d.get("itens")
    if not isinstance(itens, list) or not itens or len(itens) > 500:
        raise ValidationError("Informe entre 1 e 500 contas.")

    def criar(db):
        contas = [_dados_conta(item, db) for item in itens]
        ids = [_inserir_conta_pagar(db, dados) for dados in contas]
        return {"ok": True, "criadas": len(ids), "ids": ids}

    result, status = run_operation(d, criar)
    return jsonify(result), status

@login_requerido
def pagar_conta(cid):
    err = somente_admin()
    if err: return err
    with closing(get_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        conta = _conta_pagar(db, cid)
        if conta["status"] != "pago":
            db.execute("UPDATE fin_contas_pagar SET status='pago', pago_em=? WHERE id=?",
                       (datetime.now().isoformat(), cid))
        db.execute("UPDATE fin_massa_entregas SET pago=1 WHERE conta_pagar_id=?", (cid,))
    return jsonify({"ok": True})

@login_requerido
def deletar_conta_pagar(cid):
    err = somente_admin()
    if err: return err
    with closing(get_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        conta = _conta_pagar(db, cid)
        _proteger_conta_vinculada(db, conta)
        db.execute("DELETE FROM fin_contas_pagar WHERE id=?", (cid,))
    return jsonify({"ok": True})

# ── Contas a Receber ──────────────────────────────────────────────────────────
@login_requerido
def listar_contas_receber():
    err = somente_admin()
    if err: return err
    db = get_db()
    status = request.args.get("status", "")
    if status:
        rows = db.execute(
            "SELECT * FROM fin_contas_receber WHERE status=? ORDER BY vencimento ASC", (status,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM fin_contas_receber ORDER BY vencimento ASC"
        ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@login_requerido
def criar_conta_receber():
    err = somente_admin()
    if err: return err
    d = json_object()
    with closing(get_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        descricao, valor, vencimento, categoria, _, observacao = _dados_conta(d, db, receber=True)
        db.execute(
            """INSERT INTO fin_contas_receber
               (descricao,valor,vencimento,status,categoria,observacao,usuario_id,criado_em)
               VALUES (?,?,?,?,?,?,?,?)""",
            (descricao, valor, vencimento, "aberto", categoria, observacao,
             session["usuario_id"], datetime.now().isoformat())
        )
    return jsonify({"ok": True}), 201

@login_requerido
def receber_conta(cid):
    err = somente_admin()
    if err: return err
    with closing(get_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        conta = db.execute("SELECT * FROM fin_contas_receber WHERE id=?", (cid,)).fetchone()
        if not conta:
            abort(404, description="Conta não encontrada")
        if conta["status"] != "recebido":
            db.execute("UPDATE fin_contas_receber SET status='recebido', recebido_em=? WHERE id=?",
                       (datetime.now().isoformat(), cid))
    return jsonify({"ok": True})

@login_requerido
def deletar_conta_receber(cid):
    err = somente_admin()
    if err: return err
    db = get_db()
    db.execute("DELETE FROM fin_contas_receber WHERE id=?", (cid,))
    db.commit(); db.close()
    return jsonify({"ok": True})

# ── Categorias financeiras ────────────────────────────────────────────────────
CATS_RECEBER = ["Venda","Serviço","Reembolso","Outros"]

@login_requerido
def categorias_pagar():
    db = get_db()
    rows = db.execute("SELECT id, nome FROM fin_categorias_pagar ORDER BY nome").fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@login_requerido
def criar_categoria_pagar():
    err = somente_admin()
    if err: return err
    d = json_object()
    nome = text(d.get("nome"), "Nome")
    db = get_db()
    try:
        db.execute("INSERT INTO fin_categorias_pagar (nome,criado_em) VALUES (?,?)",
                   (nome, datetime.now().isoformat()))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify({"erro": "Categoria já existe"}), 400
    finally:
        db.close()
    return jsonify({"ok": True}), 201

@login_requerido
def renomear_categoria_pagar(cid):
    err = somente_admin()
    if err: return err
    d = json_object()
    nome = text(d.get("nome"), "Nome")
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        # Atualizar o nome nas contas a pagar existentes também
        cat_atual = db.execute("SELECT nome FROM fin_categorias_pagar WHERE id=?", (cid,)).fetchone()
        if not cat_atual:
            abort(404, description="Categoria não encontrada")
        db.execute("UPDATE fin_contas_pagar SET categoria=? WHERE categoria=?",
                   (nome, cat_atual["nome"]))
        db.execute("UPDATE fin_categorias_pagar SET nome=? WHERE id=?", (nome, cid))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify({"erro": "Categoria já existe com esse nome"}), 400
    finally:
        db.close()
    return jsonify({"ok": True})

@login_requerido
def excluir_categoria_pagar(cid):
    err = somente_admin()
    if err: return err
    with closing(get_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        cat = db.execute("SELECT nome FROM fin_categorias_pagar WHERE id=?", (cid,)).fetchone()
        if not cat:
            abort(404, description="Categoria não encontrada")
        vinculadas = db.execute(
            "SELECT COUNT(*) AS total FROM fin_contas_pagar WHERE categoria=?",
            (cat["nome"],)
        ).fetchone()["total"]
        if vinculadas > 0:
            return jsonify({"erro": f"Não é possível excluir: {vinculadas} conta(s) vinculada(s) a esta categoria. Reatribua-as primeiro."}), 400
        db.execute("DELETE FROM fin_categorias_pagar WHERE id=?", (cid,))
    return jsonify({"ok": True})

@login_requerido
def categorias_receber():
    return jsonify(CATS_RECEBER)


def register_routes(app):
    app.route("/api/fin/contas-pagar", methods=["GET"])(listar_contas_pagar)
    app.route("/api/fin/contas-pagar/<int:cid>", methods=["PUT"])(editar_conta_pagar)
    app.route("/api/fin/contas-pagar/resumo-categorias", methods=["GET"])(resumo_categorias_pagar)
    app.route("/api/fin/contas-pagar", methods=["POST"])(criar_conta_pagar)
    app.route("/api/fin/contas-pagar/lote", methods=["POST"])(criar_contas_pagar_lote)
    app.route("/api/fin/contas-pagar/<int:cid>/pagar", methods=["POST"])(pagar_conta)
    app.route("/api/fin/contas-pagar/<int:cid>", methods=["DELETE"])(deletar_conta_pagar)
    app.route("/api/fin/contas-receber", methods=["GET"])(listar_contas_receber)
    app.route("/api/fin/contas-receber", methods=["POST"])(criar_conta_receber)
    app.route("/api/fin/contas-receber/<int:cid>/receber", methods=["POST"])(receber_conta)
    app.route("/api/fin/contas-receber/<int:cid>", methods=["DELETE"])(deletar_conta_receber)
    app.route("/api/fin/categorias-pagar")(categorias_pagar)
    app.route("/api/fin/categorias-pagar", methods=["POST"])(criar_categoria_pagar)
    app.route("/api/fin/categorias-pagar/<int:cid>", methods=["PUT"])(renomear_categoria_pagar)
    app.route("/api/fin/categorias-pagar/<int:cid>", methods=["DELETE"])(excluir_categoria_pagar)
    app.route("/api/fin/categorias-receber")(categorias_receber)
