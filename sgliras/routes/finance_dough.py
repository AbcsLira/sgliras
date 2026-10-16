"""Rotas: finance dough."""
from datetime import datetime
from flask import request, jsonify, session
from ..database import get_db
from ..security import login_requerido, somente_admin

# ── Massas de Pizza ───────────────────────────────────────────────────────────
MASSA_TIPOS = ["p","m","g","gg","burg"]

@login_requerido
def listar_massa_precos():
    err = somente_admin()
    if err: return err
    db = get_db()
    rows = db.execute("SELECT * FROM fin_massa_precos ORDER BY vigente_de DESC").fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@login_requerido
def salvar_massa_preco():
    err = somente_admin()
    if err: return err
    d = request.get_json(silent=True) or {}
    vigente_de = d.get("vigente_de")
    if not vigente_de:
        return jsonify({"erro": "Data de vigência obrigatória"}), 400
    db = get_db()
    db.execute(
        """INSERT OR REPLACE INTO fin_massa_precos
           (vigente_de,preco_p,preco_m,preco_g,preco_gg,preco_burg,usuario_id,criado_em)
           VALUES (?,?,?,?,?,?,?,?)""",
        (vigente_de,
         float(d.get("preco_p",0)), float(d.get("preco_m",0)),
         float(d.get("preco_g",0)), float(d.get("preco_gg",0)),
         float(d.get("preco_burg",0)),
         session.get("usuario_id"), datetime.now().isoformat())
    )
    db.commit(); db.close()
    return jsonify({"ok": True}), 201

@login_requerido
def deletar_massa_preco(data):
    err = somente_admin()
    if err: return err
    db = get_db()
    db.execute("DELETE FROM fin_massa_precos WHERE vigente_de=?", (data,))
    db.commit(); db.close()
    return jsonify({"ok": True})

@login_requerido
def listar_massa_entregas():
    err = somente_admin()
    if err: return err
    mes = request.args.get("mes")
    db = get_db()
    if mes:
        rows = db.execute(
            "SELECT * FROM fin_massa_entregas WHERE data LIKE ? ORDER BY data DESC",
            (f"{mes}%",)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM fin_massa_entregas ORDER BY data DESC LIMIT 60"
        ).fetchall()
    precos = db.execute(
        "SELECT * FROM fin_massa_precos ORDER BY vigente_de DESC"
    ).fetchall()
    db.close()

    def preco_vigente(data):
        for p in precos:
            if p["vigente_de"] <= data:
                return dict(p)
        return {"preco_p":0,"preco_m":0,"preco_g":0,"preco_gg":0,"preco_burg":0}

    resultado = []
    for r in rows:
        rd = dict(r)
        p = preco_vigente(rd["data"])
        rd["preco_p"]    = p.get("preco_p",0)
        rd["preco_m"]    = p.get("preco_m",0)
        rd["preco_g"]    = p.get("preco_g",0)
        rd["preco_gg"]   = p.get("preco_gg",0)
        rd["preco_burg"] = p.get("preco_burg",0)
        rd["valor_calculado"] = round(
            rd["qtd_p"]*rd["preco_p"] + rd["qtd_m"]*rd["preco_m"] +
            rd["qtd_g"]*rd["preco_g"] + rd["qtd_gg"]*rd["preco_gg"] +
            rd["qtd_burg"]*rd["preco_burg"], 2)
        resultado.append(rd)
    return jsonify(resultado)

@login_requerido
def registrar_massa_entrega():
    err = somente_admin()
    if err: return err
    d = request.get_json(silent=True) or {}
    if not d.get("data"):
        return jsonify({"erro": "Data obrigatória"}), 400
    agora = datetime.now().isoformat()
    db = get_db()
    # Inserir entrega
    cur = db.execute(
        """INSERT INTO fin_massa_entregas
           (data,qtd_gg,qtd_g,qtd_m,qtd_p,qtd_burg,valor_total,observacao,pago,usuario_id,criado_em)
           VALUES (?,?,?,?,?,?,?,?,0,?,?)""",
        (d["data"],
         int(d.get("qtd_gg",0)), int(d.get("qtd_g",0)),
         int(d.get("qtd_m",0)), int(d.get("qtd_p",0)),
         int(d.get("qtd_burg",0)),
         float(d.get("valor_total",0)),
         d.get("observacao",""),
         session.get("usuario_id"), agora)
    )
    entrega_id = cur.lastrowid
    # Criar conta a pagar em aberto
    valor = float(d.get("valor_total",0))
    data_fmt = new_data = d["data"]
    descricao = f"Massas — {data_fmt}"
    conta_cur = db.execute(
        """INSERT INTO fin_contas_pagar
           (descricao,valor,vencimento,status,categoria,observacao,usuario_id,criado_em)
           VALUES (?,?,?,?,?,?,?,?)""",
        (descricao, valor, data_fmt, "aberto", "Fornecedor",
         d.get("observacao",""), session.get("usuario_id"), agora)
    )
    conta_id = conta_cur.lastrowid
    # Vincular conta à entrega
    db.execute("UPDATE fin_massa_entregas SET conta_pagar_id=? WHERE id=?", (conta_id, entrega_id))
    db.commit(); db.close()
    return jsonify({"ok": True, "entrega_id": entrega_id, "conta_pagar_id": conta_id}), 201

@login_requerido
def atualizar_massa_entrega(eid):
    err = somente_admin()
    if err: return err
    d = request.get_json(silent=True) or {}
    db = get_db()
    db.execute(
        """UPDATE fin_massa_entregas SET
           qtd_p=?,qtd_m=?,qtd_g=?,qtd_gg=?,qtd_burg=?,valor_total=?,observacao=?
           WHERE id=?""",
        (int(d.get("qtd_p",0)), int(d.get("qtd_m",0)),
         int(d.get("qtd_g",0)), int(d.get("qtd_gg",0)),
         int(d.get("qtd_burg",0)),
         float(d.get("valor_total",0)),
         d.get("observacao",""), eid)
    )
    db.commit(); db.close()
    return jsonify({"ok": True})

@login_requerido
def deletar_massa_entrega(eid):
    err = somente_admin()
    if err: return err
    db = get_db()
    entrega = db.execute("SELECT conta_pagar_id FROM fin_massa_entregas WHERE id=? AND pago=0", (eid,)).fetchone()
    if entrega:
        if entrega["conta_pagar_id"]:
            db.execute("DELETE FROM fin_contas_pagar WHERE id=?", (entrega["conta_pagar_id"],))
        db.execute("DELETE FROM fin_massa_entregas WHERE id=?", (eid,))
    db.commit(); db.close()
    return jsonify({"ok": True})

@login_requerido
def registrar_pagamento_massa():
    err = somente_admin()
    if err: return err
    d = request.get_json(silent=True) or {}
    ids = d.get("ids", [])
    if not ids:
        return jsonify({"erro": "Selecione ao menos uma entrega"}), 400
    agora = datetime.now().isoformat()
    db = get_db()
    ph = ",".join("?" for _ in ids)
    entregas = db.execute(
        f"SELECT id, conta_pagar_id, valor_total FROM fin_massa_entregas WHERE id IN ({ph})", ids
    ).fetchall()
    # Marcar cada conta a pagar vinculada como paga
    for e in entregas:
        if e["conta_pagar_id"]:
            db.execute(
                "UPDATE fin_contas_pagar SET status='pago', pago_em=? WHERE id=?",
                (agora, e["conta_pagar_id"])
            )
    # Marcar entregas como pagas
    db.execute(f"UPDATE fin_massa_entregas SET pago=1 WHERE id IN ({ph})", ids)
    db.commit(); db.close()
    total = sum(e["valor_total"] for e in entregas)
    return jsonify({"ok": True, "valor_total": total}), 201



def register_routes(app):
    app.route("/api/fin/massa-precos", methods=["GET"])(listar_massa_precos)
    app.route("/api/fin/massa-precos", methods=["POST"])(salvar_massa_preco)
    app.route("/api/fin/massa-precos/<string:data>", methods=["DELETE"])(deletar_massa_preco)
    app.route("/api/fin/massa-entregas", methods=["GET"])(listar_massa_entregas)
    app.route("/api/fin/massa-entregas", methods=["POST"])(registrar_massa_entrega)
    app.route("/api/fin/massa-entregas/<int:eid>", methods=["PUT"])(atualizar_massa_entrega)
    app.route("/api/fin/massa-entregas/<int:eid>", methods=["DELETE"])(deletar_massa_entrega)
    app.route("/api/fin/massa-pagamento", methods=["POST"])(registrar_pagamento_massa)
