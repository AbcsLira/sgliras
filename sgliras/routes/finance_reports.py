"""Rotas: finance reports."""
from datetime import datetime, timedelta
from flask import request, jsonify, session
from ..database import get_db
from ..security import login_requerido, somente_admin

@login_requerido
def obter_meta_mensal():
    """Retorna a meta do mês informado (ou mês atual) junto com o progresso já realizado."""
    err = somente_admin()
    if err: return err
    mes = request.args.get("mes", datetime.now().strftime("%Y-%m"))
    db = get_db()
    meta = db.execute("SELECT * FROM fin_metas_mensais WHERE mes=?", (mes,)).fetchone()
    # Soma de venda realizada no mês (mesma lógica do resumo mensal — sem delivery)
    venda = db.execute("""
        SELECT COALESCE(SUM(credito+debito+voucher+pix+dinheiro),0) AS total,
               COUNT(*) AS dias
        FROM fin_fechamento_diario WHERE data LIKE ?
    """, (f"{mes}%",)).fetchone()
    db.close()

    realizado = venda["total"] or 0
    dias_lancados = venda["dias"] or 0
    meta_valor = meta["meta_valor"] if meta else None
    media_diaria = round(realizado / dias_lancados, 2) if dias_lancados else 0

    resultado = {
        "mes": mes,
        "meta_valor": meta_valor,
        "realizado": realizado,
        "dias_lancados": dias_lancados,
        "media_diaria": media_diaria,
    }
    if meta_valor:
        resultado["percentual"] = round((realizado / meta_valor) * 100, 1) if meta_valor > 0 else 0
        resultado["falta"] = round(max(meta_valor - realizado, 0), 2)
    return jsonify(resultado)


@login_requerido
def salvar_meta_mensal():
    err = somente_admin()
    if err: return err
    d = request.get_json(silent=True) or {}
    mes = d.get("mes")
    meta_valor = d.get("meta_valor")
    if not mes or not meta_valor:
        return jsonify({"erro": "Mês e valor da meta são obrigatórios"}), 400
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO fin_metas_mensais (mes,meta_valor,usuario_id,criado_em) VALUES (?,?,?,?)",
        (mes, float(meta_valor), session.get("usuario_id"), datetime.now().isoformat())
    )
    db.commit(); db.close()
    return jsonify({"ok": True}), 201


@login_requerido
def comparativo_fds():
    """
    Retorna comparativo de finais de semana (sex/sáb/dom).
    modo=mes  → compara FDS dentro de um mês (ex: FDS 1 vs 2 vs 3 vs 4)
    modo=anual → compara o mesmo FDS entre meses diferentes
    """
    err = somente_admin()
    if err: return err
    modo = request.args.get("modo", "mes")  # "mes" ou "anual"
    mes  = request.args.get("mes", datetime.now().strftime("%Y-%m"))
    db   = get_db()

    # Busca fechamentos com dia da semana (0=dom, 6=sáb no strftime SQLite)
    # %w: 0=domingo, 1=seg, ..., 5=sex, 6=sáb
    if modo == "mes":
        rows = db.execute("""
            SELECT data, credito, debito, voucher, pix, dinheiro, delivery_val, delivery_qtd,
                   CAST(strftime('%w', data) AS INTEGER) AS dia_semana
            FROM fin_fechamento_diario
            WHERE data LIKE ? AND CAST(strftime('%w', data) AS INTEGER) IN (0,5,6)
            ORDER BY data ASC
        """, (f"{mes}%",)).fetchall()
    else:
        # Últimos 6 meses, finais de semana
        rows = db.execute("""
            SELECT data, credito, debito, voucher, pix, dinheiro, delivery_val, delivery_qtd,
                   CAST(strftime('%w', data) AS INTEGER) AS dia_semana,
                   substr(data,1,7) AS mes_ref
            FROM fin_fechamento_diario
            WHERE data >= date('now', '-6 months')
              AND CAST(strftime('%w', data) AS INTEGER) IN (0,5,6)
            ORDER BY data ASC
        """).fetchall()
    db.close()

    NOME_DIA = {5: "Sexta", 6: "Sábado", 0: "Domingo"}

    def _ancora_fds(dt, dia_semana):
        """Retorna a data da sexta-feira do fim de semana ao qual esse dia pertence.
        Ancorar pela sexta (em vez de dividir o mês em blocos fixos de 7 dias) evita
        que sábado/domingo de um mesmo fim de semana caiam em grupos diferentes
        quando a sexta cai perto da virada de um bloco (ex: dia 7, 14, 21, 28)."""
        if dia_semana == 5:    # sexta
            return dt
        elif dia_semana == 6:  # sábado
            return dt - timedelta(days=1)
        else:                  # domingo (0)
            return dt - timedelta(days=2)

    if modo == "mes":
        # Agrupar por fim de semana real (ancorado na sexta-feira)
        from datetime import date
        grupos_por_ancora = {}
        for r in rows:
            dt = date.fromisoformat(r["data"])
            ancora = _ancora_fds(dt, r["dia_semana"])
            if ancora not in grupos_por_ancora:
                grupos_por_ancora[ancora] = {"dias": []}
            venda = r["credito"] + r["debito"] + r["voucher"] + r["pix"] + r["dinheiro"]
            grupos_por_ancora[ancora]["dias"].append({
                "data": r["data"],
                "dia_nome": NOME_DIA.get(r["dia_semana"], ""),
                "venda": venda,
                "delivery_val": r["delivery_val"],
                "delivery_qtd": r["delivery_qtd"],
            })
        # Numerar os FDS em ordem cronológica dentro do mês (FDS 1 = primeiro fim de semana, etc.)
        resultado = []
        for i, ancora in enumerate(sorted(grupos_por_ancora.keys()), start=1):
            g = grupos_por_ancora[ancora]
            total = sum(d["venda"] for d in g["dias"])
            resultado.append({"label": f"FDS {i}", "dias": g["dias"], "total": total})
        return jsonify({"modo": "mes", "mes": mes, "fds": resultado})

    else:
        # Agrupar por mês → dentro de cada mês, por fim de semana real (ancorado na sexta)
        from datetime import date
        meses_ancoras = {}
        for r in rows:
            dt = date.fromisoformat(r["data"])
            mes_ref = r["mes_ref"]
            ancora = _ancora_fds(dt, r["dia_semana"])
            meses_ancoras.setdefault(mes_ref, {}).setdefault(ancora, {"dias": []})
            venda = r["credito"] + r["debito"] + r["voucher"] + r["pix"] + r["dinheiro"]
            meses_ancoras[mes_ref][ancora]["dias"].append({
                "data": r["data"],
                "dia_nome": NOME_DIA.get(r["dia_semana"], ""),
                "venda": venda,
            })
        # Dentro de cada mês, numera os FDS em ordem cronológica para poder
        # comparar "FDS 1 de um mês" com "FDS 1 de outro mês" de forma consistente.
        meses_grupos = {}
        for mes_ref, ancoras in meses_ancoras.items():
            meses_grupos[mes_ref] = {}
            for i, ancora in enumerate(sorted(ancoras.keys()), start=1):
                dias = ancoras[ancora]["dias"]
                total = sum(d["venda"] for d in dias)
                key = f"FDS {i}"
                meses_grupos[mes_ref][key] = {"label": key, "total": total, "dias": dias}
        # Organizar por semana para comparar entre meses
        semanas_unicas = sorted(set(
            s for m in meses_grupos.values() for s in m.keys()
        ))
        resultado = []
        for sem in semanas_unicas:
            item = {"semana": sem, "por_mes": []}
            for mes_r, semanas in sorted(meses_grupos.items()):
                if sem in semanas:
                    item["por_mes"].append({
                        "mes": mes_r,
                        "total": semanas[sem]["total"],
                        "dias": semanas[sem]["dias"]
                    })
            resultado.append(item)
        return jsonify({"modo": "anual", "semanas": resultado})


@login_requerido
def alertas_vencimento():
    """Retorna contas a pagar em aberto vencendo nos próximos 7 dias ou já vencidas."""
    err = somente_admin()
    if err: return err
    db = get_db()
    hoje = datetime.now().strftime("%Y-%m-%d")
    em7  = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    rows = db.execute("""
        SELECT cp.*, f.nome AS fornecedor_nome,
               julianday(cp.vencimento) - julianday(?) AS dias_restantes
        FROM fin_contas_pagar cp
        LEFT JOIN fornecedores f ON f.id=cp.fornecedor_id
        WHERE cp.status='aberto' AND cp.vencimento <= ?
        ORDER BY cp.vencimento ASC
    """, (hoje, em7)).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@login_requerido
def comparativo_resultado():
    """Compara receita de vendas com contas pagas no período — visão de resultado."""
    err = somente_admin()
    if err: return err
    mes = request.args.get("mes", datetime.now().strftime("%Y-%m"))
    db = get_db()

    # Receitas do fechamento diário
    fechamento = db.execute("""
        SELECT
            COALESCE(SUM(credito+debito+voucher+pix+dinheiro), 0) AS venda_total,
            COALESCE(SUM(delivery_val), 0) AS delivery_total,
            COALESCE(SUM(frete), 0) AS frete_total,
            COUNT(*) AS dias_lancados
        FROM fin_fechamento_diario WHERE data LIKE ?
    """, (f"{mes}%",)).fetchone()

    # Contas pagas no mês agrupadas por categoria
    contas = db.execute("""
        SELECT categoria,
               COUNT(*) AS total_contas,
               SUM(valor) AS total_valor
        FROM fin_contas_pagar
        WHERE status='pago' AND (pago_em LIKE ? OR vencimento LIKE ?)
        GROUP BY categoria ORDER BY total_valor DESC
    """, (f"{mes}%", f"{mes}%")).fetchall()

    # Custo dos pães no mês
    precos_pao = db.execute(
        "SELECT preco, vigente_de FROM fin_preco_pao ORDER BY vigente_de DESC"
    ).fetchall()
    dias_paes = db.execute(
        "SELECT data, paes_qtd FROM fin_fechamento_diario WHERE data LIKE ? AND paes_qtd > 0",
        (f"{mes}%",)
    ).fetchall()

    def preco_pao_no_dia(data):
        for p in precos_pao:
            if p["vigente_de"] <= data:
                return p["preco"]
        return 0

    custo_paes = sum((d["paes_qtd"] or 0) * preco_pao_no_dia(d["data"]) for d in dias_paes)

    # Custo das massas no mês
    custo_massas = db.execute("""
        SELECT COALESCE(SUM(valor_total), 0) AS total
        FROM fin_massa_entregas WHERE data LIKE ?
    """, (f"{mes}%",)).fetchone()["total"] or 0

    db.close()

    total_despesas_cap = sum(c["total_valor"] for c in contas)
    venda_total = fechamento["venda_total"] or 0
    receita_total = venda_total  # delivery e frete são informativos, não entram na soma
    resultado_estimado = receita_total - total_despesas_cap

    return jsonify({
        "mes": mes,
        "receita": {
            "venda_total": round(venda_total, 2),
            "delivery": round(fechamento["delivery_total"] or 0, 2),
            "frete": round(fechamento["frete_total"] or 0, 2),
            "total": round(receita_total, 2),
            "dias_lancados": fechamento["dias_lancados"] or 0,
        },
        "custos_operacionais": {
            "paes": round(custo_paes, 2),
            "massas": round(custo_massas, 2),
        },
        "despesas_cap": [dict(c) for c in contas],
        "total_despesas_cap": round(total_despesas_cap, 2),
        "resultado_estimado": round(resultado_estimado, 2),
    })

@login_requerido
def relatorio_mensal():
    """Retorna resumo de todos os meses com fechamentos, para comparativo."""
    err = somente_admin()
    if err: return err
    db = get_db()
    rows = db.execute("""
        SELECT
            substr(data,1,7) AS mes,
            COUNT(*) AS dias,
            SUM(credito+debito+voucher+pix+dinheiro) AS venda_total,
            SUM(credito+debito+voucher) AS cartao_total,
            SUM(pix) AS pix_total,
            SUM(dinheiro) AS dinheiro_total,
            SUM(delivery_val) AS delivery_total,
            SUM(delivery_qtd) AS entregas_total,
            SUM(frete) AS frete_total,
            SUM(paes_qtd) AS paes_total,
            SUM(janta) AS janta_total,
            SUM(func_val) AS func_total,
            SUM(cortesia) AS cortesia_total
        FROM fin_fechamento_diario
        GROUP BY substr(data,1,7)
        ORDER BY mes DESC
        LIMIT 24
    """).fetchall()
    # Buscar preços de pão para calcular custo por mês
    precos_pao = db.execute(
        "SELECT preco, vigente_de FROM fin_preco_pao ORDER BY vigente_de ASC"
    ).fetchall()
    db.close()

    # Para cada mês, calcular custo dos pães buscando preço vigente por dia
    # Buscar todos os fechamentos com pães de uma vez (evita N+1 queries)
    db2 = get_db()
    todos_dias_paes = db2.execute(
        "SELECT data, paes_qtd FROM fin_fechamento_diario WHERE paes_qtd > 0 ORDER BY data"
    ).fetchall()
    db2.close()

    def preco_no_dia(data):
        preco = 0
        for p in precos_pao:
            if p["vigente_de"] <= data:
                preco = p["preco"]
        return preco

    resultado = []
    for r in rows:
        rd = dict(r)
        mes_ref = rd["mes"]
        dias_paes = [d for d in todos_dias_paes if d["data"].startswith(mes_ref)]
        custo_paes = sum((d["paes_qtd"] or 0) * preco_no_dia(d["data"]) for d in dias_paes)
        rd["custo_paes_total"] = round(custo_paes, 2)
        resultado.append(rd)

    return jsonify(resultado)



def register_routes(app):
    app.route("/api/fin/meta-mensal", methods=["GET"])(obter_meta_mensal)
    app.route("/api/fin/meta-mensal", methods=["POST"])(salvar_meta_mensal)
    app.route("/api/fin/comparativo-fds")(comparativo_fds)
    app.route("/api/fin/alertas-vencimento", methods=["GET"])(alertas_vencimento)
    app.route("/api/fin/comparativo-resultado")(comparativo_resultado)
    app.route("/api/fin/relatorio-mensal")(relatorio_mensal)
