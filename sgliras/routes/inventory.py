"""Rotas: inventory."""
from contextlib import closing
from datetime import datetime
from flask import request, jsonify, session
from ..database import get_db
from ..security import login_requerido, permissao_requerida
from ..validation import ValidationError, json_object, number, text


def _contagens(dados, parcial=False):
    """Valida o lote inteiro antes de permitir qualquer gravação."""
    itens = dados.get("itens")
    if not isinstance(itens, list) or (not parcial and not itens):
        raise ValidationError("Informe uma lista de itens para contagem.")
    validados = []
    produtos = set()
    for item in itens:
        if not isinstance(item, dict):
            raise ValidationError("Cada item da contagem deve ser um objeto JSON.")
        pid = number(item.get("produto_id"), "Produto", minimum=1, integer=True)
        if pid > 9223372036854775807:
            raise ValidationError("Produto deve ser um identificador válido.")
        if pid in produtos:
            raise ValidationError("Não repita um produto na mesma contagem.")
        produtos.add(pid)
        contada = item.get("quantidade_contada")
        # A tela envia null para produtos que ainda não foram contados.
        if contada is not None or not parcial:
            contada = number(contada, "Quantidade contada", minimum=0)
        observacao = text(item.get("observacao"), "Observação", required=False)
        validados.append((pid, contada, observacao))
    return validados

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
    d = json_object()
    categoria = text(d.get("categoria"), "Categoria", required=False) or None
    titulo = (text(d.get("titulo"), "Título", required=False)
              or ("Inventário — " + (categoria or "Geral")))
    observacao = text(d.get("observacao"), "Observação", required=False)
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
    with closing(get_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        aberto = db.execute("SELECT id FROM inventarios WHERE status='aberto'").fetchone()
        if aberto:
            return jsonify({"erro": "Já existe um inventário em aberto. Finalize-o antes de criar outro."}), 400
        prods = db.execute(query, params).fetchall()
        agora = datetime.now().isoformat()
        cur = db.execute(
            "INSERT INTO inventarios (titulo,status,categoria,observacao,usuario_id,criado_em) VALUES (?,?,?,?,?,?)",
            (titulo, "aberto", categoria, observacao, session.get("usuario_id"), agora)
        )
        inv_id = cur.lastrowid
        for p in prods:
            db.execute(
                "INSERT INTO inventario_itens (inventario_id,produto_id,quantidade_sistema) VALUES (?,?,?)",
                (inv_id, p["id"], p["quantidade"])
            )
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
    itens = _contagens(json_object(), parcial=True)
    with closing(get_db()) as db, db:
        # A situação do inventário não pode mudar entre a leitura e a escrita.
        db.execute("BEGIN IMMEDIATE")
        inv = db.execute("SELECT status FROM inventarios WHERE id=?", (inv_id,)).fetchone()
        if not inv or inv["status"] != "aberto":
            return jsonify({"erro": "Inventário não encontrado ou já finalizado"}), 400
        alteracoes = []
        for pid, contada, observacao in itens:
            sistema = db.execute(
                "SELECT quantidade_sistema FROM inventario_itens WHERE inventario_id=? AND produto_id=?",
                (inv_id, pid)
            ).fetchone()
            if not sistema:
                raise ValidationError("Um dos produtos não pertence a este inventário.")
            if contada is None:
                continue
            quantidade_sistema = number(sistema["quantidade_sistema"], "Quantidade no sistema")
            diff = number(round(contada - quantidade_sistema, 4), "Diferença de estoque")
            alteracoes.append((contada, diff, observacao, inv_id, pid))
        db.executemany(
            "UPDATE inventario_itens SET quantidade_contada=?, diferenca=?, observacao=? WHERE inventario_id=? AND produto_id=?",
            alteracoes
        )
    return jsonify({"ok": True})


@login_requerido
@permissao_requerida("produtos")
def finalizar_inventario(inv_id):
    """Finaliza o inventário aplicando os ajustes de estoque."""
    ajustados = 0
    abaixo_minimo = []
    with closing(get_db()) as db, db:
        # Serializa finalizações, salvamentos e outras gravações de estoque.
        db.execute("BEGIN IMMEDIATE")
        inv = db.execute("SELECT * FROM inventarios WHERE id=?", (inv_id,)).fetchone()
        if not inv or inv["status"] != "aberto":
            return jsonify({"erro": "Inventário não encontrado ou já finalizado"}), 400
        itens = db.execute("""
            SELECT ii.*, p.quantidade AS quantidade_atual, p.nome, p.estoque_min
            FROM inventario_itens ii JOIN produtos p ON p.id=ii.produto_id
            WHERE ii.inventario_id=? AND ii.quantidade_contada IS NOT NULL
        """, (inv_id,)).fetchall()
        # Valida também dados antigos, salvos antes da validação de entrada.
        contagens = [(item, number(item["quantidade_contada"], "Quantidade contada", minimum=0),
                      number(item["quantidade_atual"], "Quantidade atual")) for item in itens]
        agora = datetime.now().isoformat()
        for item, contada, atual in contagens:
            # Contagem é absoluta. Movimentos feitos após abrir o inventário
            # não podem fazer uma contagem igual ao saldo inicial ser ignorada.
            if contada == atual:
                continue
            db.execute("UPDATE produtos SET quantidade=? WHERE id=?", (contada, item["produto_id"]))
            obs = f"Inventário #{inv_id} — {inv['titulo']} (anterior: {atual})"
            db.execute(
                "INSERT INTO movimentacoes (produto_id,usuario_id,tipo,quantidade,observacao,criado_em) VALUES (?,?,?,?,?,?)",
                (item["produto_id"], session.get("usuario_id"), "ajuste", contada, obs, agora)
            )
            ajustados += 1
            if contada <= item["estoque_min"]:
                abaixo_minimo.append({"produto_id": item["produto_id"], "nome": item["nome"]})
        db.execute(
            "UPDATE inventarios SET status='finalizado', finalizado_em=? WHERE id=?",
            (agora, inv_id)
        )
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
    itens = _contagens(json_object())
    aplicados = []
    with closing(get_db()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        contagens = []
        for pid, contada, _observacao in itens:
            p = db.execute("SELECT quantidade FROM produtos WHERE id=?", (pid,)).fetchone()
            if not p:
                raise ValidationError("Um dos produtos não foi encontrado.")
            contagens.append((pid, contada, number(p["quantidade"], "Quantidade atual")))
        for pid, contada, atual in contagens:
            if contada == atual:
                continue
            db.execute("UPDATE produtos SET quantidade=? WHERE id=?", (contada, pid))
            obs = f"Contagem rápida de inventário (anterior: {atual})"
            db.execute(
                "INSERT INTO movimentacoes (produto_id,usuario_id,tipo,quantidade,observacao,criado_em) VALUES (?,?,?,?,?,?)",
                (pid, session["usuario_id"], "ajuste", contada, obs, datetime.now().isoformat())
            )
            aplicados.append({"produto_id": pid, "anterior": atual, "novo": contada, "diferenca": contada-atual})
    return jsonify({"ok": True, "ajustados": len(aplicados), "detalhes": aplicados}), 201



def register_routes(app):
    app.route("/api/inventario/produtos")(produtos_para_inventario)
    app.route("/api/inventarios", methods=["GET"])(listar_inventarios)
    app.route("/api/inventarios", methods=["POST"])(criar_inventario)
    app.route("/api/inventarios/<int:inv_id>", methods=["GET"])(obter_inventario)
    app.route("/api/inventarios/<int:inv_id>/itens", methods=["PUT"])(salvar_itens_inventario)
    app.route("/api/inventarios/<int:inv_id>/finalizar", methods=["POST"])(finalizar_inventario)
    app.route("/api/inventarios/<int:inv_id>", methods=["DELETE"])(cancelar_inventario)
    app.route("/api/inventario/aplicar", methods=["POST"])(aplicar_contagem_inventario)
