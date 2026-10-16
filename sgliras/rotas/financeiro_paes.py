"""Preços, contas e pagamentos de pães."""
from contextlib import closing
from datetime import datetime
from decimal import Decimal, localcontext

from flask import request, jsonify, session

from ..banco_dados import get_db
from ..seguranca import login_requerido, somente_admin
from ..validacao import ValidationError, iso_date, json_object, number


def _money(value, label="Valor"):
    return round(number(value, label, minimum=0), 2)


def _cents(value):
    with localcontext() as context:
        context.prec = 330
        return int(Decimal(str(value)) * 100)


def _dates(value):
    if not isinstance(value, list) or not value:
        raise ValidationError("Selecione ao menos um dia")
    dates = [iso_date(day, "Data") for day in value]
    if len(set(dates)) != len(dates):
        raise ValidationError("Não repita datas no mesmo pagamento")
    return sorted(dates)


def _month(value):
    if value:
        iso_date(f"{value}-01", "Mês")
    return value


def _paid_dates(db):
    dates = set()
    for row in db.execute("SELECT datas FROM fin_paes_pagamento"):
        dates.update(day.strip() for day in (row["datas"] or "").split(",") if day.strip())
    # Contas também podem ser quitadas pela tela geral do financeiro.
    prefix = "Pães — "
    for row in db.execute("SELECT descricao FROM fin_contas_pagar WHERE status='pago'"):
        if row["descricao"].startswith(prefix):
            dates.add(row["descricao"][len(prefix):])
    return dates


def _day_accounts(db, day):
    return db.execute("SELECT * FROM fin_contas_pagar WHERE descricao=? ORDER BY id",
                      (f"Pães — {day}",)).fetchall()


@login_requerido
def listar_precos_pao():
    err = somente_admin()
    if err:
        return err
    with closing(get_db()) as db:
        rows = db.execute("SELECT * FROM fin_preco_pao ORDER BY vigente_de DESC").fetchall()
    return jsonify([dict(row) for row in rows])


@login_requerido
def salvar_preco_pao():
    err = somente_admin()
    if err:
        return err
    data = json_object()
    price = _money(data.get("preco"), "Preço")
    day = iso_date(data.get("vigente_de"), "Data de vigência")
    with closing(get_db()) as db, db:
        db.execute("""INSERT INTO fin_preco_pao (preco,vigente_de,usuario_id,criado_em)
                      VALUES (?,?,?,?) ON CONFLICT(vigente_de) DO UPDATE SET
                      preco=excluded.preco, usuario_id=excluded.usuario_id,
                      criado_em=excluded.criado_em""",
                   (price, day, session["usuario_id"], datetime.now().isoformat()))
    return jsonify({"ok": True}), 201


@login_requerido
def deletar_preco_pao(data):
    err = somente_admin()
    if err:
        return err
    day = iso_date(data, "Data de vigência")
    with closing(get_db()) as db, db:
        db.execute("DELETE FROM fin_preco_pao WHERE vigente_de=?", (day,))
    return jsonify({"ok": True})


@login_requerido
def preco_pao_vigente(data):
    err = somente_admin()
    if err:
        return err
    day = iso_date(data, "Data")
    with closing(get_db()) as db:
        row = db.execute("SELECT * FROM fin_preco_pao WHERE vigente_de<=? ORDER BY vigente_de DESC LIMIT 1",
                         (day,)).fetchone()
    return jsonify(dict(row) if row else {})


@login_requerido
def relatorio_paes():
    err = somente_admin()
    if err:
        return err
    month = _month(request.args.get("mes"))
    with closing(get_db()) as db:
        if month:
            closings = db.execute("""SELECT data,paes_qtd FROM fin_fechamento_diario
                                     WHERE data LIKE ? AND paes_qtd>0 ORDER BY data""",
                                  (f"{month}%",)).fetchall()
        else:
            closings = db.execute("""SELECT data,paes_qtd FROM fin_fechamento_diario
                                     WHERE paes_qtd>0 ORDER BY data DESC LIMIT 60""").fetchall()
        prices = db.execute("SELECT * FROM fin_preco_pao ORDER BY vigente_de DESC").fetchall()
        paid = _paid_dates(db)
    result = []
    for row in closings:
        price = next((p["preco"] for p in prices if p["vigente_de"] <= row["data"]), 0)
        result.append({"data": row["data"], "paes_qtd": row["paes_qtd"], "preco": price,
                       "valor": round(row["paes_qtd"] * price, 2), "pago": row["data"] in paid})
    return jsonify(result)


@login_requerido
def paes_historico_pagamentos():
    err = somente_admin()
    if err:
        return err
    with closing(get_db()) as db:
        rows = db.execute("SELECT * FROM fin_paes_pagamento ORDER BY pago_em DESC").fetchall()
    return jsonify([dict(row) for row in rows])


@login_requerido
def desfazer_pagamento_paes(pid):
    """Estorna o histórico e reabre as contas sem apagar seu valor original."""
    err = somente_admin()
    if err:
        return err
    pid = number(pid, "Pagamento", minimum=1, integer=True)
    with closing(get_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        payment = db.execute("SELECT * FROM fin_paes_pagamento WHERE id=?", (pid,)).fetchone()
        if not payment:
            return jsonify({"erro": "Registro não encontrado"}), 404
        dates = [day.strip() for day in (payment["datas"] or "").split(",") if day.strip()]
        db.execute("DELETE FROM fin_paes_pagamento WHERE id=?", (pid,))
        remaining = set()
        for row in db.execute("SELECT datas FROM fin_paes_pagamento"):
            remaining.update(day.strip() for day in (row["datas"] or "").split(","))
        released = [day for day in dates if day not in remaining]
        for day in released:
            db.execute("""UPDATE fin_contas_pagar SET status='aberto',pago_em=NULL
                          WHERE descricao=? AND status='pago'""", (f"Pães — {day}",))
    return jsonify({"ok": True, "datas_liberadas": released})


@login_requerido
def paes_lancar_contas():
    """Lança cada dia uma única vez, inclusive entre requisições concorrentes."""
    err = somente_admin()
    if err:
        return err
    data = json_object()
    days = data.get("dias")
    if not isinstance(days, list) or not days:
        raise ValidationError("Nenhum dia informado")
    normalized = []
    for item in days:
        if not isinstance(item, dict):
            raise ValidationError("Cada dia deve ser um objeto")
        normalized.append((iso_date(item.get("data"), "Data"),
                           _money(item.get("valor")),
                           _money(item.get("preco", 0), "Preço"),
                           number(item.get("paes_qtd", 0), "Quantidade de pães", minimum=0, integer=True)))
    if len({item[0] for item in normalized}) != len(normalized):
        raise ValidationError("Não repita datas no mesmo lançamento")
    created = 0
    now = datetime.now().isoformat()
    with closing(get_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        paid = _paid_dates(db)
        for day, amount, price, quantity in normalized:
            if day in paid or _day_accounts(db, day):
                continue
            db.execute("""INSERT INTO fin_contas_pagar
                          (descricao,valor,vencimento,status,categoria,observacao,usuario_id,criado_em)
                          VALUES (?,?,?,'aberto','Fornecedor',?,?,?)""",
                       (f"Pães — {day}", amount, day, f"{quantity} pães × R${price:.2f}",
                        session["usuario_id"], now))
            created += 1
    return jsonify({"ok": True, "criadas": created}), 201


@login_requerido
def registrar_pagamento_paes():
    """Rejeita a seleção inteira se qualquer dia já estiver pago."""
    err = somente_admin()
    if err:
        return err
    data = json_object()
    dates = _dates(data.get("datas"))
    amount = _money(data.get("valor"))
    now = datetime.now().isoformat()
    with closing(get_db()) as db, db:
        # A leitura dos pagamentos e as escritas pertencem à mesma transação.
        db.execute("BEGIN IMMEDIATE")
        overlap = set(dates) & _paid_dates(db)
        if overlap:
            return jsonify({"erro": "Há dias já pagos na seleção", "datas": sorted(overlap)}), 409
        accounts = {}
        for day in dates:
            rows = _day_accounts(db, day)
            if len(rows) > 1 or (rows and rows[0]["status"] != "aberto"):
                return jsonify({"erro": "Há contas inconsistentes para um dos dias selecionados"}), 409
            accounts[day] = rows[0] if rows else None
        existing_cents = sum(_cents(_money(row["valor"])) for row in accounts.values() if row)
        missing = [day for day, row in accounts.items() if row is None]
        remaining_cents = _cents(amount) - existing_cents
        if remaining_cents < 0 or (not missing and remaining_cents):
            return jsonify({"erro": "O valor informado difere das contas dos dias selecionados"}), 409
        # Distribui apenas o saldo ainda sem conta; o centavo residual não se perde.
        shares = divmod(remaining_cents, len(missing)) if missing else (0, 0)
        new_amounts = {day: (shares[0] + (index < shares[1])) / 100
                       for index, day in enumerate(missing)}
        for day, account in accounts.items():
            if account:
                db.execute("UPDATE fin_contas_pagar SET status='pago',pago_em=? WHERE id=?",
                           (now, account["id"]))
            else:
                db.execute("""INSERT INTO fin_contas_pagar
                              (descricao,valor,vencimento,status,categoria,pago_em,usuario_id,criado_em)
                              VALUES (?,?,?,'pago','Fornecedor',?,?,?)""",
                           (f"Pães — {day}", new_amounts[day], day, now, session["usuario_id"], now))
        db.execute("""INSERT INTO fin_paes_pagamento
                      (descricao,valor,datas,pago_em,usuario_id,criado_em) VALUES (?,?,?,?,?,?)""",
                   (f"Pães — {', '.join(dates)}", amount, ",".join(dates), now, session["usuario_id"], now))
    return jsonify({"ok": True}), 201


def register_routes(app):
    app.route("/api/fin/preco-pao", methods=["GET"])(listar_precos_pao)
    app.route("/api/fin/preco-pao", methods=["POST"])(salvar_preco_pao)
    app.route("/api/fin/preco-pao/<string:data>", methods=["DELETE"])(deletar_preco_pao)
    app.route("/api/fin/preco-pao-vigente/<string:data>", methods=["GET"])(preco_pao_vigente)
    app.route("/api/fin/relatorio-paes", methods=["GET"])(relatorio_paes)
    app.route("/api/fin/paes-historico-pagamentos", methods=["GET"])(paes_historico_pagamentos)
    app.route("/api/fin/paes-pagamento/<int:pid>", methods=["DELETE"])(desfazer_pagamento_paes)
    app.route("/api/fin/paes-lancar-contas", methods=["POST"])(paes_lancar_contas)
    app.route("/api/fin/paes-pagamento", methods=["POST"])(registrar_pagamento_paes)
