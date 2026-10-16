"""Rotas: dashboard."""
from datetime import datetime
from flask import request, jsonify, session
from ..banco_dados import get_db
from ..seguranca import login_requerido

@login_requerido
def dashboard():
    db=get_db()
    eh_admin = session.get("perfil") == "admin"
    tot=db.execute("SELECT COUNT(*) FROM produtos WHERE ativo=1").fetchone()[0]
    cri=db.execute("SELECT COUNT(*) FROM produtos WHERE ativo=1 AND quantidade<=estoque_min").fetchone()[0]
    zer=db.execute("SELECT COUNT(*) FROM produtos WHERE ativo=1 AND quantidade=0").fetchone()[0]
    valor_total = None
    if eh_admin:
        valor_total = db.execute(
            "SELECT COALESCE(SUM(quantidade * preco_custo), 0) FROM produtos WHERE ativo=1"
        ).fetchone()[0]
        valor_total = round(valor_total, 2)
    rows=db.execute("""
        SELECT p.nome,p.codigo,p.quantidade,p.estoque_min,p.unidade,
               p.sub_qtd_por_un,p.sub_unidade,
               COALESCE(c.nome,'Sem categoria') AS categoria
        FROM produtos p LEFT JOIN categorias c ON c.id=p.categoria_id
        WHERE p.ativo=1 AND p.quantidade<=p.estoque_min ORDER BY categoria,p.quantidade""").fetchall()
    grupos={}
    for r in rows:
        cat=r["categoria"]
        if cat not in grupos: grupos[cat]=[]
        grupos[cat].append({k:r[k] for k in ("nome","codigo","unidade","quantidade","estoque_min","sub_qtd_por_un","sub_unidade")})

    # ── Alertas de validade ──
    from datetime import timedelta
    hoje = datetime.now().date()
    limite = hoje + timedelta(days=15)
    val_rows = db.execute("""
        SELECT p.nome, p.codigo, p.quantidade, p.unidade, p.validade,
               COALESCE(c.nome,'Sem categoria') AS categoria
        FROM produtos p LEFT JOIN categorias c ON c.id=p.categoria_id
        WHERE p.ativo=1 AND p.validade IS NOT NULL AND p.validade != ''
        ORDER BY p.validade ASC
    """).fetchall()

    vencidos = []
    proximos = []
    for r in val_rows:
        try:
            data_val = datetime.strptime(r["validade"], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        item = {"nome": r["nome"], "codigo": r["codigo"], "quantidade": r["quantidade"],
                "unidade": r["unidade"], "categoria": r["categoria"],
                "validade": r["validade"], "dias": (data_val - hoje).days}
        if data_val < hoje:
            vencidos.append(item)
        elif data_val <= limite:
            proximos.append(item)

    db.close()
    return jsonify({"total_produtos":tot,"criticos":cri,"sem_estoque":zer,
                    "valor_total":valor_total,"criticos_por_categoria":grupos,
                    "vencidos":vencidos,"proximos_vencimento":proximos})

# ── Listagem PDF ───────────────────────────────────────────────────────────────
@login_requerido
def listagem_pdf():
    db=get_db()
    # Filtros opcionais via query string
    filtro_cat  = request.args.get("categoria","").strip()
    filtro_nome = request.args.get("nome","").strip()

    query = """
        SELECT p.nome, p.codigo, p.quantidade, p.unidade,
               p.sub_qtd_por_un, p.sub_unidade, p.unid_por_fardo, p.unid_fardo_label,
               p.estoque_min, p.preco_custo,
               COALESCE(c.nome,'Sem categoria') AS categoria
        FROM produtos p
        LEFT JOIN categorias c ON c.id=p.categoria_id
        WHERE p.ativo=1
    """
    params = []
    if filtro_cat:
        query += " AND LOWER(c.nome) = LOWER(?)"
        params.append(filtro_cat)
    if filtro_nome:
        query += " AND LOWER(p.nome) LIKE LOWER(?)"
        params.append(f"%{filtro_nome}%")
    query += " ORDER BY c.nome, p.nome"
    rows=db.execute(query, params).fetchall()
    db.close()

    eh_admin = session.get("perfil") == "admin"
    lista = []
    for r in rows:
        p = dict(r)
        # Calcular exibição de quantidade
        qtd = p["quantidade"]
        un  = p["unidade"] or "un"
        sub_qtd = p["sub_qtd_por_un"]
        sub_un  = p["sub_unidade"]

        unid_por_fardo = p["unid_por_fardo"]

        if sub_qtd and sub_qtd > 0 and sub_un:
            # Subdivisão tradicional: estoque em fardos -> exibe em unidades
            total_sub = qtd * sub_qtd
            sobra_int = int(total_sub)  # trunca em vez de arredondar
            fardos_cheios = sobra_int // int(sub_qtd)
            resto         = sobra_int  % int(sub_qtd)
            if resto == 0:
                qtd_display = f"{fardos_cheios} {un}"
            else:
                qtd_display = f"{fardos_cheios} {un} + {resto} {sub_un}"
        elif unid_por_fardo and unid_por_fardo > 0:
            # Conversão para listagem: estoque em unidades -> exibe em grupos (fardo/caixa/etc)
            grupo_label = p["unid_fardo_label"] or "fd"
            total_un = round(qtd)
            grupos_cheios = total_un // int(unid_por_fardo)
            resto         = total_un %  int(unid_por_fardo)
            if resto == 0:
                qtd_display = f"{grupos_cheios} {grupo_label}"
            else:
                qtd_display = f"{grupos_cheios} {grupo_label} + {resto} {un}"
        else:
            qtd_display = f"{qtd} {un}"

        p["qtd_display"] = qtd_display
        p["valor_total_item"] = round(qtd * p["preco_custo"], 2) if eh_admin else None
        lista.append(p)

    # Agrupar por categoria
    grupos = {}
    for p in lista:
        chave = p["categoria"]
        if chave not in grupos:
            grupos[chave] = []
        grupos[chave].append(p)

    total_geral = round(sum(p["preco_custo"]*p["quantidade"] for p in lista), 2) if eh_admin else None
    return jsonify({"grupos": grupos, "total_geral": total_geral, "eh_admin": eh_admin,
                    "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M")})


def register_routes(app):
    app.route("/api/dashboard")(dashboard)
    app.route("/api/listagem-pdf")(listagem_pdf)
