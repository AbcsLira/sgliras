"""Rotas: finance daily."""
from datetime import datetime
from flask import request, jsonify, session
from ..banco_dados import get_db
from ..seguranca import login_requerido, somente_admin

@login_requerido
def listar_fechamentos():
    err = somente_admin()
    if err: return err
    db = get_db()
    mes = request.args.get("mes")  # formato YYYY-MM
    if mes:
        rows = db.execute(
            "SELECT * FROM fin_fechamento_diario WHERE data LIKE ? ORDER BY data DESC",
            (f"{mes}%",)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM fin_fechamento_diario ORDER BY data DESC LIMIT 60"
        ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@login_requerido
def obter_fechamento(data):
    err = somente_admin()
    if err: return err
    db = get_db()
    row = db.execute("SELECT * FROM fin_fechamento_diario WHERE data=?", (data,)).fetchone()
    db.close()
    return jsonify(dict(row) if row else {})

@login_requerido
def salvar_fechamento():
    err = somente_admin()
    if err: return err
    d = request.get_json(silent=True) or {}
    data = d.get("data")
    if not data:
        return jsonify({"erro": "Data é obrigatória"}), 400
    db = get_db()
    existente = db.execute("SELECT id FROM fin_fechamento_diario WHERE data=?", (data,)).fetchone()
    agora = datetime.now().isoformat()
    campos = ("credito","debito","voucher","pix","dinheiro",
              "delivery_qtd","delivery_val","frete","paes_qtd",
              "janta","func_val","cortesia","observacao")
    valores = [d.get(c, 0) for c in campos]
    if existente:
        sets = ", ".join(f"{c}=?" for c in campos) + ", atualizado_em=?, usuario_id=?"
        db.execute(f"UPDATE fin_fechamento_diario SET {sets} WHERE data=?",
                   valores + [agora, session.get("usuario_id"), data])
    else:
        cols = "data," + ",".join(campos) + ",usuario_id,criado_em"
        phs  = "?," + ",".join("?" for _ in campos) + ",?,?"
        db.execute(f"INSERT INTO fin_fechamento_diario ({cols}) VALUES ({phs})",
                   [data] + valores + [session.get("usuario_id"), agora])
    db.commit(); db.close()
    return jsonify({"ok": True})

@login_requerido
def deletar_fechamento(data):
    err = somente_admin()
    if err: return err
    db = get_db()
    db.execute("DELETE FROM fin_fechamento_diario WHERE data=?", (data,))
    db.commit(); db.close()
    return jsonify({"ok": True})

@login_requerido
def resumo_mes():
    err = somente_admin()
    if err: return err
    mes = request.args.get("mes", datetime.now().strftime("%Y-%m"))
    db = get_db()
    rows = db.execute(
        "SELECT * FROM fin_fechamento_diario WHERE data LIKE ? ORDER BY data ASC",
        (f"{mes}%",)
    ).fetchall()
    # Buscar todos os preços de pão ordenados (para calcular vigente de cada dia)
    precos_pao = db.execute(
        "SELECT preco, vigente_de FROM fin_preco_pao ORDER BY vigente_de DESC"
    ).fetchall()
    db.close()
    if not rows:
        return jsonify({"mes": mes, "dias": 0, "totais": {}, "por_dia": []})

    def preco_pao_no_dia(data):
        for p in precos_pao:
            if p["vigente_de"] <= data:
                return p["preco"]
        return 0

    totais = {
        "credito": 0, "debito": 0, "voucher": 0, "pix": 0, "dinheiro": 0,
        "delivery_val": 0, "frete": 0, "janta": 0, "func_val": 0, "cortesia": 0,
        "paes_qtd": 0, "delivery_qtd": 0, "custo_paes": 0
    }
    por_dia = []
    for r in rows:
        rd = dict(r)
        venda_dia = rd["credito"] + rd["debito"] + rd["voucher"] + rd["pix"] + rd["dinheiro"]
        rd["venda_total"] = venda_dia
        preco_pao = preco_pao_no_dia(rd["data"])
        rd["preco_pao_vigente"] = preco_pao
        rd["custo_paes"] = round((rd.get("paes_qtd") or 0) * preco_pao, 2)
        por_dia.append(rd)
        for k in totais:
            if k == "custo_paes":
                totais[k] += rd["custo_paes"]
            else:
                totais[k] += rd.get(k, 0) or 0
    totais["venda_total"] = (totais["credito"] + totais["debito"] + totais["voucher"]
                             + totais["pix"] + totais["dinheiro"])
    totais["cartao_total"] = totais["credito"] + totais["debito"] + totais["voucher"]
    return jsonify({"mes": mes, "dias": len(rows), "totais": totais, "por_dia": por_dia})


def register_routes(app):
    app.route("/api/fin/fechamento", methods=["GET"])(listar_fechamentos)
    app.route("/api/fin/fechamento/<string:data>", methods=["GET"])(obter_fechamento)
    app.route("/api/fin/fechamento", methods=["POST"])(salvar_fechamento)
    app.route("/api/fin/fechamento/<string:data>", methods=["DELETE"])(deletar_fechamento)
    app.route("/api/fin/resumo-mes", methods=["GET"])(resumo_mes)
