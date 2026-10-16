"""Preços e entregas de massas com contas a pagar sincronizadas."""
from contextlib import closing
from datetime import datetime

from flask import request, jsonify, session

from ..database import get_db
from ..security import login_requerido, somente_admin
from ..validation import ValidationError, iso_date, json_object, number, text


MASSA_TIPOS = ["p", "m", "g", "gg", "burg"]


def _money(value, label="Valor"):
    return round(number(value, label, minimum=0), 2)


def _delivery_values(data, existing=None):
    previous = dict(existing) if existing else {}
    values = {"data": iso_date(data.get("data", previous.get("data")), "Data")}
    for size in MASSA_TIPOS:
        field = f"qtd_{size}"
        values[field] = number(data.get(field, previous.get(field, 0)), f"Quantidade {size}",
                               minimum=0, integer=True)
    values["valor_total"] = _money(data.get("valor_total", previous.get("valor_total", 0)))
    values["observacao"] = text(data.get("observacao", previous.get("observacao") or ""),
                                 "Observação", required=False)
    return values


def _account(db, delivery):
    if not delivery["conta_pagar_id"]:
        return None
    return db.execute("SELECT * FROM fin_contas_pagar WHERE id=?",
                      (delivery["conta_pagar_id"],)).fetchone()


def _conflict(db, delivery):
    account = _account(db, delivery)
    if delivery["pago"] or (account and account["status"] == "pago"):
        return "Entrega já paga; não é possível alterar, excluir ou pagar novamente"
    if account and account["status"] != "aberto":
        return "A conta vinculada não está em aberto"
    if account and db.execute("SELECT id FROM fin_massa_entregas WHERE conta_pagar_id=? AND id<>?",
                              (account["id"], delivery["id"])).fetchone():
        return "A conta está vinculada a mais de uma entrega"
    return None


def _sync_account(db, delivery, now):
    """Atualiza a conta ou recupera o vínculo de entregas antigas sem conta."""
    account = _account(db, delivery)
    values = (f"Massas — {delivery['data']}", delivery["valor_total"], delivery["data"],
              delivery["observacao"] or "")
    if account:
        db.execute("""UPDATE fin_contas_pagar SET descricao=?,valor=?,vencimento=?,observacao=?
                      WHERE id=?""", (*values, account["id"]))
        return account["id"]
    cursor = db.execute("""INSERT INTO fin_contas_pagar
                           (descricao,valor,vencimento,observacao,status,categoria,usuario_id,criado_em)
                           VALUES (?,?,?,?,'aberto','Fornecedor',?,?)""",
                        (*values, session["usuario_id"], now))
    db.execute("UPDATE fin_massa_entregas SET conta_pagar_id=? WHERE id=?",
               (cursor.lastrowid, delivery["id"]))
    return cursor.lastrowid


@login_requerido
def listar_massa_precos():
    err = somente_admin()
    if err:
        return err
    with closing(get_db()) as db:
        rows = db.execute("SELECT * FROM fin_massa_precos ORDER BY vigente_de DESC,id DESC").fetchall()
    return jsonify([dict(row) for row in rows])


@login_requerido
def salvar_massa_preco():
    err = somente_admin()
    if err:
        return err
    data = json_object()
    day = iso_date(data.get("vigente_de"), "Data de vigência")
    prices = [_money(data.get(f"preco_{size}", 0), f"Preço {size}") for size in MASSA_TIPOS]
    now = datetime.now().isoformat()
    with closing(get_db()) as db, db:
        # vigente_de não possui UNIQUE nos bancos legados: REPLACE inseria outra linha.
        db.execute("BEGIN IMMEDIATE")
        updated = db.execute("""UPDATE fin_massa_precos SET preco_p=?,preco_m=?,preco_g=?,
                                preco_gg=?,preco_burg=?,usuario_id=?,criado_em=? WHERE vigente_de=?""",
                             (*prices, session["usuario_id"], now, day)).rowcount
        if not updated:
            db.execute("""INSERT INTO fin_massa_precos
                          (preco_p,preco_m,preco_g,preco_gg,preco_burg,usuario_id,criado_em,vigente_de)
                          VALUES (?,?,?,?,?,?,?,?)""", (*prices, session["usuario_id"], now, day))
    return jsonify({"ok": True}), 201


@login_requerido
def deletar_massa_preco(data):
    err = somente_admin()
    if err:
        return err
    day = iso_date(data, "Data de vigência")
    with closing(get_db()) as db, db:
        db.execute("DELETE FROM fin_massa_precos WHERE vigente_de=?", (day,))
    return jsonify({"ok": True})


@login_requerido
def listar_massa_entregas():
    err = somente_admin()
    if err:
        return err
    month = request.args.get("mes")
    if month:
        iso_date(f"{month}-01", "Mês")
    with closing(get_db()) as db:
        if month:
            rows = db.execute("SELECT * FROM fin_massa_entregas WHERE data LIKE ? ORDER BY data DESC",
                              (f"{month}%",)).fetchall()
        else:
            rows = db.execute("SELECT * FROM fin_massa_entregas ORDER BY data DESC LIMIT 60").fetchall()
        prices = db.execute("SELECT * FROM fin_massa_precos ORDER BY vigente_de DESC,id DESC").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        price = next((p for p in prices if p["vigente_de"] <= item["data"]), None)
        for size in MASSA_TIPOS:
            item[f"preco_{size}"] = price[f"preco_{size}"] if price else 0
        item["valor_calculado"] = round(sum(item[f"qtd_{size}"] * item[f"preco_{size}"]
                                             for size in MASSA_TIPOS), 2)
        result.append(item)
    return jsonify(result)


@login_requerido
def registrar_massa_entrega():
    err = somente_admin()
    if err:
        return err
    values = _delivery_values(json_object())
    now = datetime.now().isoformat()
    with closing(get_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        cursor = db.execute("""INSERT INTO fin_massa_entregas
                               (data,qtd_p,qtd_m,qtd_g,qtd_gg,qtd_burg,valor_total,observacao,pago,usuario_id,criado_em)
                               VALUES (?,?,?,?,?,?,?,?,0,?,?)""",
                            (values["data"], *(values[f"qtd_{size}"] for size in MASSA_TIPOS),
                             values["valor_total"], values["observacao"], session["usuario_id"], now))
        delivery = {**values, "id": cursor.lastrowid, "conta_pagar_id": None}
        account_id = _sync_account(db, delivery, now)
    return jsonify({"ok": True, "entrega_id": delivery["id"], "conta_pagar_id": account_id}), 201


@login_requerido
def atualizar_massa_entrega(eid):
    err = somente_admin()
    if err:
        return err
    eid = number(eid, "Entrega", minimum=1, integer=True)
    data = json_object()
    with closing(get_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        delivery = db.execute("SELECT * FROM fin_massa_entregas WHERE id=?", (eid,)).fetchone()
        if not delivery:
            return jsonify({"erro": "Entrega não encontrada"}), 404
        conflict = _conflict(db, delivery)
        if conflict:
            return jsonify({"erro": conflict}), 409
        values = _delivery_values(data, delivery)
        db.execute("""UPDATE fin_massa_entregas SET data=?,qtd_p=?,qtd_m=?,qtd_g=?,qtd_gg=?,
                      qtd_burg=?,valor_total=?,observacao=? WHERE id=?""",
                   (values["data"], *(values[f"qtd_{size}"] for size in MASSA_TIPOS),
                    values["valor_total"], values["observacao"], eid))
        _sync_account(db, {**dict(delivery), **values}, datetime.now().isoformat())
    return jsonify({"ok": True})


@login_requerido
def deletar_massa_entrega(eid):
    err = somente_admin()
    if err:
        return err
    eid = number(eid, "Entrega", minimum=1, integer=True)
    with closing(get_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        delivery = db.execute("SELECT * FROM fin_massa_entregas WHERE id=?", (eid,)).fetchone()
        if not delivery:
            return jsonify({"erro": "Entrega não encontrada"}), 404
        conflict = _conflict(db, delivery)
        if conflict:
            return jsonify({"erro": conflict}), 409
        # Primeiro remove a referência; a FK é verificada imediatamente pelo SQLite.
        db.execute("DELETE FROM fin_massa_entregas WHERE id=?", (eid,))
        if delivery["conta_pagar_id"]:
            db.execute("DELETE FROM fin_contas_pagar WHERE id=?", (delivery["conta_pagar_id"],))
    return jsonify({"ok": True})


@login_requerido
def registrar_pagamento_massa():
    err = somente_admin()
    if err:
        return err
    data = json_object()
    ids = data.get("ids")
    if not isinstance(ids, list) or not ids:
        raise ValidationError("Selecione ao menos uma entrega")
    ids = [number(value, "Entrega", minimum=1, integer=True) for value in ids]
    if len(set(ids)) != len(ids):
        raise ValidationError("Não repita entregas no mesmo pagamento")
    now = datetime.now().isoformat()
    with closing(get_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        placeholders = ",".join("?" for _ in ids)
        deliveries = db.execute(f"SELECT * FROM fin_massa_entregas WHERE id IN ({placeholders})", ids).fetchall()
        if len(deliveries) != len(ids):
            return jsonify({"erro": "Uma ou mais entregas não foram encontradas"}), 404
        # Valida toda a seleção antes da primeira escrita, inclusive o total calculado.
        for delivery in deliveries:
            conflict = _conflict(db, delivery)
            if conflict:
                return jsonify({"erro": conflict}), 409
            _delivery_values({}, delivery)
        total = _money(sum(delivery["valor_total"] for delivery in deliveries))
        for delivery in deliveries:
            account_id = _sync_account(db, delivery, now)
            db.execute("UPDATE fin_contas_pagar SET status='pago',pago_em=? WHERE id=?", (now, account_id))
            db.execute("UPDATE fin_massa_entregas SET pago=1 WHERE id=?", (delivery["id"],))
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
