"""Rotas: suppliers."""
from datetime import datetime
from flask import request, jsonify
from ..banco_dados import get_db
from ..seguranca import login_requerido, permissao_requerida

@login_requerido
def listar_fornecedores():
    db = get_db()
    rows = db.execute("SELECT * FROM fornecedores ORDER BY nome").fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@login_requerido
@permissao_requerida("produtos")
def criar_fornecedor():
    d = request.get_json(silent=True) or {}
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO fornecedores (nome, contato, observacao, criado_em) VALUES (?,?,?,?)",
            (d["nome"], d.get("contato", ""), d.get("observacao", ""), datetime.now().isoformat())
        )
        db.commit()
        return jsonify({"ok": True, "id": cur.lastrowid}), 201
    finally:
        db.close()


@login_requerido
@permissao_requerida("produtos")
def atualizar_fornecedor(fid):
    d = request.get_json(silent=True) or {}
    db = get_db()
    db.execute(
        "UPDATE fornecedores SET nome=?, contato=?, observacao=? WHERE id=?",
        (d["nome"], d.get("contato", ""), d.get("observacao", ""), fid)
    )
    db.commit(); db.close()
    return jsonify({"ok": True})


@login_requerido
@permissao_requerida("produtos")
def deletar_fornecedor(fid):
    db = get_db()
    try:
        db.execute("DELETE FROM produto_fornecedores WHERE fornecedor_id=?", (fid,))
        db.execute("DELETE FROM fornecedores WHERE id=?", (fid,))
        db.commit()
        return jsonify({"ok": True})
    except Exception as e:
        db.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        db.close()


@login_requerido
def listar_produtos_do_fornecedor(fid):
    """Retorna todos os produtos vinculados a um fornecedor, com o preço cobrado por ele."""
    db = get_db()
    rows = db.execute("""
        SELECT p.id, p.nome, p.codigo, p.unidade, p.quantidade, p.estoque_min,
               p.unid_por_fardo, p.unid_fardo_label,
               COALESCE(c.nome,'Sem categoria') AS categoria,
               pf.preco AS preco_fornecedor
        FROM produto_fornecedores pf
        JOIN produtos p ON p.id = pf.produto_id
        LEFT JOIN categorias c ON c.id = p.categoria_id
        WHERE pf.fornecedor_id = ?
        ORDER BY p.nome
    """, (fid,)).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


# ── Vínculo Produto x Fornecedor (preço por fornecedor) ─────────────────────────
@login_requerido
def listar_fornecedores_do_produto(pid):
    db = get_db()
    rows = db.execute("""
        SELECT pf.id, pf.fornecedor_id, pf.preco, pf.atualizado_em, f.nome AS fornecedor_nome, f.contato
        FROM produto_fornecedores pf
        JOIN fornecedores f ON f.id = pf.fornecedor_id
        WHERE pf.produto_id = ?
        ORDER BY pf.preco ASC
    """, (pid,)).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@login_requerido
@permissao_requerida("produtos")
def vincular_fornecedor(pid):
    d = request.get_json(silent=True) or {}
    db = get_db()
    try:
        fornecedor_id = d["fornecedor_id"]
        preco = float(d.get("preco", 0))
        agora = datetime.now().isoformat()
        existente = db.execute(
            "SELECT id FROM produto_fornecedores WHERE produto_id=? AND fornecedor_id=?",
            (pid, fornecedor_id)
        ).fetchone()
        if existente:
            db.execute(
                "UPDATE produto_fornecedores SET preco=?, atualizado_em=? WHERE id=?",
                (preco, agora, existente["id"])
            )
        else:
            db.execute(
                "INSERT INTO produto_fornecedores (produto_id, fornecedor_id, preco, atualizado_em) VALUES (?,?,?,?)",
                (pid, fornecedor_id, preco, agora)
            )
        db.commit()
        return jsonify({"ok": True}), 201
    finally:
        db.close()


@login_requerido
@permissao_requerida("produtos")
def desvincular_fornecedor(pid, vid):
    db = get_db()
    db.execute("DELETE FROM produto_fornecedores WHERE id=? AND produto_id=?", (vid, pid))
    db.commit(); db.close()
    return jsonify({"ok": True})


# ── Lista de Compras ─────────────────────────────────────────────────────────
@login_requerido
def sugestao_lista_compras():
    """Retorna produtos com estoque <= mínimo, com o fornecedor mais barato vinculado (se houver)."""
    db = get_db()
    produtos_baixos = db.execute("""
        SELECT p.id, p.nome, p.codigo, p.unidade, p.quantidade, p.estoque_min, p.preco_custo,
               p.unid_por_fardo, p.unid_fardo_label,
               COALESCE(c.nome,'Sem categoria') AS categoria
        FROM produtos p
        LEFT JOIN categorias c ON c.id = p.categoria_id
        WHERE p.ativo=1 AND p.quantidade <= p.estoque_min
        ORDER BY c.nome, p.nome
    """).fetchall()

    resultado = []
    for p in produtos_baixos:
        p = dict(p)
        melhor = db.execute("""
            SELECT f.nome AS fornecedor_nome, pf.preco
            FROM produto_fornecedores pf
            JOIN fornecedores f ON f.id = pf.fornecedor_id
            WHERE pf.produto_id = ?
            ORDER BY pf.preco ASC LIMIT 1
        """, (p["id"],)).fetchone()
        p["fornecedor_sugerido"] = melhor["fornecedor_nome"] if melhor else None
        p["preco_fornecedor"] = melhor["preco"] if melhor else None
        # Sugestão de quantidade a comprar: repõe até o estoque mínimo x2 (regra simples)
        falta = max(p["estoque_min"] * 2 - p["quantidade"], p["estoque_min"])
        p["quantidade_sugerida"] = round(falta, 2) if falta > 0 else p["estoque_min"]
        resultado.append(p)

    db.close()
    return jsonify(resultado)



def register_routes(app):
    app.route("/api/fornecedores")(listar_fornecedores)
    app.route("/api/fornecedores", methods=["POST"])(criar_fornecedor)
    app.route("/api/fornecedores/<int:fid>", methods=["PUT"])(atualizar_fornecedor)
    app.route("/api/fornecedores/<int:fid>", methods=["DELETE"])(deletar_fornecedor)
    app.route("/api/fornecedores/<int:fid>/produtos")(listar_produtos_do_fornecedor)
    app.route("/api/produtos/<int:pid>/fornecedores")(listar_fornecedores_do_produto)
    app.route("/api/produtos/<int:pid>/fornecedores", methods=["POST"])(vincular_fornecedor)
    app.route("/api/produtos/<int:pid>/fornecedores/<int:vid>", methods=["DELETE"])(desvincular_fornecedor)
    app.route("/api/lista-compras/sugestao")(sugestao_lista_compras)
