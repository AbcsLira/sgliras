"""Rotas: inventory."""
from datetime import datetime
from flask import request, jsonify, session
from ..database import get_db
from ..security import login_requerido, permissao_requerida

@login_requerido
def produtos_para_inventario():
    """Lista produtos para contagem, com filtro opcional por categoria."""
    db = get_db()
    filtro_cat = request.args.get("categoria", "").strip()
    query = """
        SELECT p.id, p.nome, p.codigo, p.unidade, p.quantidade,
               p.unid_por_fardo, p.unid_fardo_label,
               COALESCE(c.nome,'Sem categoria') AS categoria
        FROM produtos p
        LEFT JOIN categorias c ON c.id = p.categoria_id
        WHERE p.ativo=1
    """
    params = []
    if filtro_cat:
        query += " AND LOWER(c.nome) = LOWER(?)"
        params.append(filtro_cat)
    query += " ORDER BY c.nome, p.nome"
    rows = db.execute(query, params).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


# ── Inventário Estruturado ────────────────────────────────────────────────────
@login_requerido
@permissao_requerida("produtos")
def listar_inventarios():
    db = get_db()
    rows = db.execute("""
        SELECT i.*, u.nome AS usuario_nome,
               COUNT(ii.id) AS total_itens,
               SUM(CASE WHEN ii.diferenca != 0 AND ii.diferenca IS NOT NULL THEN 1 ELSE 0 END) AS total_divergentes,
               SUM(CASE WHEN ii.diferenca IS NOT NULL THEN ABS(ii.diferenca * (SELECT preco_custo FROM produtos WHERE id=ii.produto_id)) ELSE 0 END) AS valor_divergencia
        FROM inventarios i
        LEFT JOIN usuarios u ON u.id = i.usuario_id
        LEFT JOIN inventario_itens ii ON ii.inventario_id = i.id
        GROUP BY i.id
        ORDER BY i.criado_em DESC LIMIT 30
    """).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@login_requerido
@permissao_requerida("produtos")
def criar_inventario():
    d = request.get_json(silent=True) or {}
    categoria = d.get("categoria") or None
    titulo = d.get("titulo") or ("Inventário — " + (categoria or "Geral"))
    db = get_db()
    # Verificar se há inventário aberto
    aberto = db.execute("SELECT id FROM inventarios WHERE status='aberto'").fetchone()
    if aberto:
        db.close()
        return jsonify({"erro": "Já existe um inventário em aberto. Finalize-o antes de criar outro."}), 400
    # Buscar produtos
    query = """
        SELECT p.id, p.quantidade,
               COALESCE(c.nome,'Sem categoria') AS categoria
        FROM produtos p
        LEFT JOIN categorias c ON c.id = p.categoria_id
        WHERE p.ativo=1
    """
    params = []
    if categoria:
        query += " AND LOWER(c.nome) = LOWER(?)"
        params.append(categoria)
    query += " ORDER BY c.nome, p.nome"
    prods = db.execute(query, params).fetchall()
    agora = datetime.now().isoformat()
    cur = db.execute(
        "INSERT INTO inventarios (titulo,status,categoria,observacao,usuario_id,criado_em) VALUES (?,?,?,?,?,?)",
        (titulo, "aberto", categoria, d.get("observacao",""), session.get("usuario_id"), agora)
    )
    inv_id = cur.lastrowid
    for p in prods:
        db.execute(
            "INSERT INTO inventario_itens (inventario_id,produto_id,quantidade_sistema) VALUES (?,?,?)",
            (inv_id, p["id"], p["quantidade"])
        )
    db.commit()
    db.close()
    return jsonify({"ok": True, "id": inv_id}), 201


@login_requerido
@permissao_requerida("produtos")
def obter_inventario(inv_id):
    db = get_db()
    inv = db.execute("SELECT * FROM inventarios WHERE id=?", (inv_id,)).fetchone()
    if not inv:
        db.close(); return jsonify({"erro": "Inventário não encontrado"}), 404
    itens = db.execute("""
        SELECT ii.*, p.nome, p.codigo, p.unidade, p.unid_por_fardo, p.unid_fardo_label,
               COALESCE(c.nome,'Sem categoria') AS categoria
        FROM inventario_itens ii
        JOIN produtos p ON p.id = ii.produto_id
        LEFT JOIN categorias c ON c.id = p.categoria_id
        WHERE ii.inventario_id=?
        ORDER BY categoria, p.nome
    """, (inv_id,)).fetchall()
    db.close()
    return jsonify({"inventario": dict(inv), "itens": [dict(r) for r in itens]})


@login_requerido
@permissao_requerida("produtos")
def salvar_itens_inventario(inv_id):
    """Salva contagens parciais sem finalizar."""
    d = request.get_json(silent=True) or {}
    itens = d.get("itens", [])
    db = get_db()
    inv = db.execute("SELECT status FROM inventarios WHERE id=?", (inv_id,)).fetchone()
    if not inv or inv["status"] != "aberto":
        db.close(); return jsonify({"erro": "Inventário não encontrado ou já finalizado"}), 400
    for item in itens:
        contada = item.get("quantidade_contada")
        if contada is None:
            continue
        contada = float(contada)
        sistema = db.execute(
            "SELECT quantidade_sistema FROM inventario_itens WHERE inventario_id=? AND produto_id=?",
            (inv_id, item["produto_id"])
        ).fetchone()
        if not sistema:
            continue
        diff = round(contada - sistema["quantidade_sistema"], 4)
        db.execute(
            "UPDATE inventario_itens SET quantidade_contada=?, diferenca=?, observacao=? WHERE inventario_id=? AND produto_id=?",
            (contada, diff, item.get("observacao",""), inv_id, item["produto_id"])
        )
    db.commit(); db.close()
    return jsonify({"ok": True})


@login_requerido
@permissao_requerida("produtos")
def finalizar_inventario(inv_id):
    """Finaliza o inventário aplicando os ajustes de estoque."""
    db = get_db()
    inv = db.execute("SELECT * FROM inventarios WHERE id=?", (inv_id,)).fetchone()
    if not inv or inv["status"] != "aberto":
        db.close(); return jsonify({"erro": "Inventário não encontrado ou já finalizado"}), 400
    itens = db.execute(
        "SELECT * FROM inventario_itens WHERE inventario_id=? AND quantidade_contada IS NOT NULL",
        (inv_id,)
    ).fetchall()
    agora = datetime.now().isoformat()
    ajustados = 0
    abaixo_minimo = []
    for item in itens:
        if item["diferenca"] is None or abs(item["diferenca"]) < 0.0001:
            continue
        contada = item["quantidade_contada"]
        db.execute("UPDATE produtos SET quantidade=? WHERE id=?", (contada, item["produto_id"]))
        obs = f"Inventário #{inv_id} — {inv['titulo']} (anterior: {item['quantidade_sistema']})"
        db.execute(
            "INSERT INTO movimentacoes (produto_id,usuario_id,tipo,quantidade,observacao,criado_em) VALUES (?,?,?,?,?,?)",
            (item["produto_id"], session.get("usuario_id"), "ajuste", contada, obs, agora)
        )
        ajustados += 1
        # Verificar se ficou abaixo do mínimo após ajuste
        p = db.execute("SELECT nome, estoque_min FROM produtos WHERE id=?", (item["produto_id"],)).fetchone()
        if p and contada <= p["estoque_min"]:
            abaixo_minimo.append({"produto_id": item["produto_id"], "nome": p["nome"]})
    db.execute(
        "UPDATE inventarios SET status='finalizado', finalizado_em=? WHERE id=?",
        (agora, inv_id)
    )
    db.commit(); db.close()
    return jsonify({"ok": True, "ajustados": ajustados, "abaixo_minimo": abaixo_minimo})


@login_requerido
@permissao_requerida("produtos")
def cancelar_inventario(inv_id):
    db = get_db()
    db.execute("DELETE FROM inventarios WHERE id=? AND status='aberto'", (inv_id,))
    db.commit(); db.close()
    return jsonify({"ok": True})


@login_requerido
@permissao_requerida("produtos")
def aplicar_contagem_inventario():
    """Mantido para compatibilidade com a contagem rápida existente."""
    d = request.get_json(silent=True) or {}
    itens = d.get("itens", [])
    if not itens:
        return jsonify({"erro": "Nenhum item informado"}), 400
    db = get_db()
    try:
        aplicados = []
        for item in itens:
            pid = item["produto_id"]
            contada = float(item["quantidade_contada"])
            p = db.execute("SELECT quantidade FROM produtos WHERE id=?", (pid,)).fetchone()
            if not p: continue
            atual = p["quantidade"]
            if abs(contada - atual) < 0.0001: continue
            db.execute("UPDATE produtos SET quantidade=? WHERE id=?", (contada, pid))
            obs = f"Contagem rápida de inventário (anterior: {atual})"
            db.execute(
                "INSERT INTO movimentacoes (produto_id,usuario_id,tipo,quantidade,observacao,criado_em) VALUES (?,?,?,?,?,?)",
                (pid, session["usuario_id"], "ajuste", contada, obs, datetime.now().isoformat())
            )
            aplicados.append({"produto_id": pid, "anterior": atual, "novo": contada, "diferenca": contada-atual})
        db.commit()
        return jsonify({"ok": True, "ajustados": len(aplicados), "detalhes": aplicados}), 201
    except Exception as e:
        db.rollback(); return jsonify({"erro": str(e)}), 500
    finally:
        db.close()



def register_routes(app):
    app.route("/api/inventario/produtos")(produtos_para_inventario)
    app.route("/api/inventarios", methods=["GET"])(listar_inventarios)
    app.route("/api/inventarios", methods=["POST"])(criar_inventario)
    app.route("/api/inventarios/<int:inv_id>", methods=["GET"])(obter_inventario)
    app.route("/api/inventarios/<int:inv_id>/itens", methods=["PUT"])(salvar_itens_inventario)
    app.route("/api/inventarios/<int:inv_id>/finalizar", methods=["POST"])(finalizar_inventario)
    app.route("/api/inventarios/<int:inv_id>", methods=["DELETE"])(cancelar_inventario)
    app.route("/api/inventario/aplicar", methods=["POST"])(aplicar_contagem_inventario)
