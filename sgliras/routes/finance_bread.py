"""Rotas: finance bread."""
from datetime import datetime
from flask import request, jsonify, session
from ..database import get_db
from ..security import login_requerido, somente_admin

@login_requerido
def listar_precos_pao():
    err = somente_admin()
    if err: return err
    db = get_db()
    rows = db.execute(
        "SELECT * FROM fin_preco_pao ORDER BY vigente_de DESC"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@login_requerido
def salvar_preco_pao():
    err = somente_admin()
    if err: return err
    d = request.get_json(silent=True) or {}
    if not d.get("preco") or not d.get("vigente_de"):
        return jsonify({"erro": "Preço e data de vigência são obrigatórios"}), 400
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO fin_preco_pao (preco, vigente_de, usuario_id, criado_em) VALUES (?,?,?,?)",
        (float(d["preco"]), d["vigente_de"], session.get("usuario_id"), datetime.now().isoformat())
    )
    db.commit(); db.close()
    return jsonify({"ok": True}), 201

@login_requerido
def deletar_preco_pao(data):
    err = somente_admin()
    if err: return err
    db = get_db()
    db.execute("DELETE FROM fin_preco_pao WHERE vigente_de=?", (data,))
    db.commit(); db.close()
    return jsonify({"ok": True})

@login_requerido
def preco_pao_vigente(data):
    """Retorna o preço do pão vigente em uma data específica."""
    err = somente_admin()
    if err: return err
    db = get_db()
    row = db.execute(
        "SELECT * FROM fin_preco_pao WHERE vigente_de <= ? ORDER BY vigente_de DESC LIMIT 1",
        (data,)
    ).fetchone()
    db.close()
    return jsonify(dict(row) if row else {})

@login_requerido
def relatorio_paes():
    """Retorna os fechamentos com quantidade de pães, já com preço vigente calculado."""
    err = somente_admin()
    if err: return err
    db = get_db()
    mes = request.args.get("mes")
    if mes:
        fechamentos = db.execute(
            "SELECT data, paes_qtd FROM fin_fechamento_diario WHERE data LIKE ? AND paes_qtd > 0 ORDER BY data ASC",
            (f"{mes}%",)
        ).fetchall()
    else:
        fechamentos = db.execute(
            "SELECT data, paes_qtd FROM fin_fechamento_diario WHERE paes_qtd > 0 ORDER BY data DESC LIMIT 60"
        ).fetchall()
    precos = db.execute(
        "SELECT * FROM fin_preco_pao ORDER BY vigente_de DESC"
    ).fetchall()
    pagamentos = db.execute(
        "SELECT id, datas, valor, pago_em FROM fin_paes_pagamento ORDER BY pago_em DESC"
    ).fetchall()
    db.close()

    # Montar conjunto de datas já pagas
    datas_pagas = set()
    for p in pagamentos:
        for dt in (p["datas"] or "").split(","):
            datas_pagas.add(dt.strip())

    def preco_em(data):
        for p in precos:
            if p["vigente_de"] <= data:
                return p["preco"]
        return 0

    resultado = []
    for f in fechamentos:
        preco = preco_em(f["data"])
        resultado.append({
            "data": f["data"],
            "paes_qtd": f["paes_qtd"],
            "preco": preco,
            "valor": round(f["paes_qtd"] * preco, 2),
            "pago": f["data"] in datas_pagas
        })
    return jsonify(resultado)

@login_requerido
def paes_historico_pagamentos():
    err = somente_admin()
    if err: return err
    db = get_db()
    rows = db.execute(
        "SELECT * FROM fin_paes_pagamento ORDER BY pago_em DESC"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@login_requerido
def desfazer_pagamento_paes(pid):
    """Remove um registro de pagamento de pães, liberando as datas para novo pagamento."""
    err = somente_admin()
    if err: return err
    db = get_db()
    reg = db.execute("SELECT * FROM fin_paes_pagamento WHERE id=?", (pid,)).fetchone()
    if not reg:
        db.close()
        return jsonify({"erro": "Registro não encontrado"}), 404
    # Desfazer também as contas a pagar vinculadas (se houver)
    datas = [dt.strip() for dt in (reg["datas"] or "").split(",") if dt.strip()]
    for data in datas:
        db.execute(
            "DELETE FROM fin_contas_pagar WHERE descricao=? AND status='pago'",
            (f"Pães — {data}",)
        )
    db.execute("DELETE FROM fin_paes_pagamento WHERE id=?", (pid,))
    db.commit(); db.close()
    return jsonify({"ok": True, "datas_liberadas": datas})

@login_requerido
def paes_lancar_contas():
    """Lança dias de pães selecionados em Contas a Pagar como 'em aberto'."""
    err = somente_admin()
    if err: return err
    d = request.get_json(silent=True) or {}
    dias = d.get("dias", [])  # lista de {data, valor, preco, paes_qtd}
    if not dias:
        return jsonify({"erro": "Nenhum dia informado"}), 400
    agora = datetime.now().isoformat()
    db = get_db()
    # Buscar pagamentos já existentes para evitar duplicar
    pagas_existentes = set()
    rows = db.execute("SELECT datas FROM fin_paes_pagamento").fetchall()
    for r in rows:
        for dt in (r["datas"] or "").split(","):
            pagas_existentes.add(dt.strip())
    ids_criados = []
    for dia in dias:
        data = dia["data"]
        if data in pagas_existentes:
            continue
        descricao = f"Pães — {data}"
        # Verificar se já existe conta a pagar em aberto para esse dia
        existente = db.execute(
            "SELECT id FROM fin_contas_pagar WHERE descricao=? AND status='aberto'", (descricao,)
        ).fetchone()
        if existente:
            ids_criados.append(existente["id"])
            continue
        cur = db.execute(
            """INSERT INTO fin_contas_pagar
               (descricao,valor,vencimento,status,categoria,observacao,usuario_id,criado_em)
               VALUES (?,?,?,?,?,?,?,?)""",
            (descricao, float(dia["valor"]), data, "aberto", "Fornecedor",
             f"{dia.get('paes_qtd',0)} pães × R${dia.get('preco',0):.2f}",
             session.get("usuario_id"), agora)
        )
        ids_criados.append(cur.lastrowid)
    db.commit(); db.close()
    return jsonify({"ok": True, "criadas": len(ids_criados)}), 201


@login_requerido
def registrar_pagamento_paes():
    """Marca contas a pagar de pães como pagas (ou cria já paga se não existir)."""
    err = somente_admin()
    if err: return err
    d = request.get_json(silent=True) or {}
    datas = d.get("datas", [])
    valor = float(d.get("valor", 0))
    if not datas or not valor:
        return jsonify({"erro": "Selecione ao menos um dia e informe o valor"}), 400
    agora = datetime.now().isoformat()
    hoje = datetime.now().strftime("%Y-%m-%d")
    datas_str = ", ".join(sorted(datas))
    descricao_pagamento = f"Pães — {datas_str}"
    db = get_db()
    # Marcar contas a pagar individuais como pagas
    for data in datas:
        descricao_dia = f"Pães — {data}"
        conta = db.execute(
            "SELECT id FROM fin_contas_pagar WHERE descricao=? AND status='aberto'", (descricao_dia,)
        ).fetchone()
        if conta:
            db.execute("UPDATE fin_contas_pagar SET status='pago', pago_em=? WHERE id=?",
                       (agora, conta["id"]))
        else:
            # Se não existe conta individual, cria já paga (compatibilidade)
            valor_dia = round(valor / len(datas), 2)
            db.execute(
                """INSERT INTO fin_contas_pagar
                   (descricao,valor,vencimento,status,categoria,pago_em,usuario_id,criado_em)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (descricao_dia, valor_dia, data, "pago", "Fornecedor",
                 agora, session.get("usuario_id"), agora)
            )
    # Registrar no histórico de pagamentos de pães
    db.execute(
        "INSERT INTO fin_paes_pagamento (descricao,valor,datas,pago_em,usuario_id,criado_em) VALUES (?,?,?,?,?,?)",
        (descricao_pagamento, valor, ",".join(sorted(datas)), agora, session.get("usuario_id"), agora)
    )
    db.commit(); db.close()
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
