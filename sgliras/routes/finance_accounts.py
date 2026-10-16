"""Rotas: finance accounts."""
from datetime import datetime
from flask import request, jsonify, session
from ..database import get_db
from ..security import login_requerido, somente_admin

@login_requerido
def listar_contas_pagar():
    err = somente_admin()
    if err: return err
    db = get_db()
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
        where.append("cp.fornecedor_id=?"); params.append(int(fornecedor_id))

    rows = db.execute(f"""
        SELECT cp.*, f.nome AS fornecedor_nome
        FROM fin_contas_pagar cp
        LEFT JOIN fornecedores f ON f.id=cp.fornecedor_id
        WHERE {' AND '.join(where)}
        ORDER BY cp.vencimento ASC
    """, params).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@login_requerido
def editar_conta_pagar(cid):
    err = somente_admin()
    if err: return err
    d = request.get_json(silent=True) or {}
    if not d.get("descricao") or not d.get("valor") or not d.get("vencimento"):
        return jsonify({"erro": "Descrição, valor e vencimento são obrigatórios"}), 400
    db = get_db()
    db.execute("""UPDATE fin_contas_pagar SET
        descricao=?, valor=?, vencimento=?, categoria=?,
        fornecedor_id=?, observacao=? WHERE id=?""",
        (d["descricao"], float(d["valor"]), d["vencimento"],
         d.get("categoria", "Outros"),
         d.get("fornecedor_id") or None,
         d.get("observacao", ""), cid))
    db.commit(); db.close()
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
    d = request.get_json(silent=True) or {}
    if not d.get("descricao") or not d.get("valor") or not d.get("vencimento"):
        return jsonify({"erro": "Descrição, valor e vencimento são obrigatórios"}), 400
    db = get_db()
    db.execute(
        """INSERT INTO fin_contas_pagar
           (descricao,valor,vencimento,status,categoria,fornecedor_id,observacao,usuario_id,criado_em)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (d["descricao"], float(d["valor"]), d["vencimento"],
         "aberto", d.get("categoria", "Outros"),
         d.get("fornecedor_id") or None, d.get("observacao", ""),
         session.get("usuario_id"), datetime.now().isoformat())
    )
    db.commit(); db.close()
    return jsonify({"ok": True}), 201

@login_requerido
def pagar_conta(cid):
    err = somente_admin()
    if err: return err
    db = get_db()
    conta = db.execute("SELECT * FROM fin_contas_pagar WHERE id=?", (cid,)).fetchone()
    if not conta:
        db.close(); return jsonify({"erro": "Conta não encontrada"}), 404
    agora = datetime.now().isoformat()
    db.execute("UPDATE fin_contas_pagar SET status='pago', pago_em=? WHERE id=?", (agora, cid))
    db.commit(); db.close()
    return jsonify({"ok": True})

@login_requerido
def deletar_conta_pagar(cid):
    err = somente_admin()
    if err: return err
    db = get_db()
    db.execute("DELETE FROM fin_contas_pagar WHERE id=?", (cid,))
    db.commit(); db.close()
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
    d = request.get_json(silent=True) or {}
    if not d.get("descricao") or not d.get("valor") or not d.get("vencimento"):
        return jsonify({"erro": "Descrição, valor e vencimento são obrigatórios"}), 400
    db = get_db()
    db.execute(
        """INSERT INTO fin_contas_receber
           (descricao,valor,vencimento,status,categoria,observacao,usuario_id,criado_em)
           VALUES (?,?,?,?,?,?,?,?)""",
        (d["descricao"], float(d["valor"]), d["vencimento"],
         "aberto", d.get("categoria", "Outros"),
         d.get("observacao", ""), session.get("usuario_id"), datetime.now().isoformat())
    )
    db.commit(); db.close()
    return jsonify({"ok": True}), 201

@login_requerido
def receber_conta(cid):
    err = somente_admin()
    if err: return err
    db = get_db()
    conta = db.execute("SELECT * FROM fin_contas_receber WHERE id=?", (cid,)).fetchone()
    if not conta:
        db.close(); return jsonify({"erro": "Conta não encontrada"}), 404
    agora = datetime.now().isoformat()
    db.execute("UPDATE fin_contas_receber SET status='recebido', recebido_em=? WHERE id=?", (agora, cid))
    db.commit(); db.close()
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
    d = request.get_json(silent=True) or {}
    nome = (d.get("nome") or "").strip()
    if not nome:
        return jsonify({"erro": "Nome obrigatório"}), 400
    db = get_db()
    try:
        db.execute("INSERT INTO fin_categorias_pagar (nome,criado_em) VALUES (?,?)",
                   (nome, datetime.now().isoformat()))
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({"erro": "Categoria já existe"}), 400
    finally:
        db.close()
    return jsonify({"ok": True}), 201

@login_requerido
def renomear_categoria_pagar(cid):
    err = somente_admin()
    if err: return err
    d = request.get_json(silent=True) or {}
    nome = (d.get("nome") or "").strip()
    if not nome:
        return jsonify({"erro": "Nome obrigatório"}), 400
    db = get_db()
    try:
        # Atualizar o nome nas contas a pagar existentes também
        cat_atual = db.execute("SELECT nome FROM fin_categorias_pagar WHERE id=?", (cid,)).fetchone()
        if cat_atual:
            db.execute("UPDATE fin_contas_pagar SET categoria=? WHERE categoria=?",
                       (nome, cat_atual["nome"]))
        db.execute("UPDATE fin_categorias_pagar SET nome=? WHERE id=?", (nome, cid))
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({"erro": "Categoria já existe com esse nome"}), 400
    finally:
        db.close()
    return jsonify({"ok": True})

@login_requerido
def excluir_categoria_pagar(cid):
    err = somente_admin()
    if err: return err
    db = get_db()
    cat = db.execute("SELECT nome FROM fin_categorias_pagar WHERE id=?", (cid,)).fetchone()
    if not cat:
        db.close()
        return jsonify({"erro": "Categoria não encontrada"}), 404
    # Verificar se há contas vinculadas
    vinculadas = db.execute(
        "SELECT COUNT(*) AS total FROM fin_contas_pagar WHERE categoria=?",
        (cat["nome"],)
    ).fetchone()["total"]
    if vinculadas > 0:
        db.close()
        return jsonify({"erro": f"Não é possível excluir: {vinculadas} conta(s) vinculada(s) a esta categoria. Reatribua-as primeiro."}), 400
    db.execute("DELETE FROM fin_categorias_pagar WHERE id=?", (cid,))
    db.commit(); db.close()
    return jsonify({"ok": True})

@login_requerido
def categorias_receber():
    return jsonify(CATS_RECEBER)


def register_routes(app):
    app.route("/api/fin/contas-pagar", methods=["GET"])(listar_contas_pagar)
    app.route("/api/fin/contas-pagar/<int:cid>", methods=["PUT"])(editar_conta_pagar)
    app.route("/api/fin/contas-pagar/resumo-categorias", methods=["GET"])(resumo_categorias_pagar)
    app.route("/api/fin/contas-pagar", methods=["POST"])(criar_conta_pagar)
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
