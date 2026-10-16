"""Rotas: stock."""
from contextlib import closing
from datetime import datetime
from flask import jsonify, session, abort
from ..database import get_db
from ..security import login_requerido, permissao_requerida
from ..audit import registrar_auditoria, fmt_rs_log
from ..validation import ValidationError, json_object, number, text, iso_date
from ..operations import run_operation

@login_requerido
def listar_categorias():
    db=get_db()
    cats=db.execute("SELECT * FROM categorias ORDER BY nome").fetchall()
    db.close(); return jsonify([dict(c) for c in cats])

# ── Produtos ──────────────────────────────────────────────────────────────────
@login_requerido
def listar_produtos():
    db=get_db()
    rows=db.execute("""
        SELECT p.*, c.nome AS categoria
        FROM produtos p
        LEFT JOIN categorias c ON c.id=p.categoria_id
        ORDER BY c.nome, p.nome
    """).fetchall()
    db.close(); return jsonify([dict(r) for r in rows])

def _product_data(data):
    result = dict(data)
    for field, label, default in [('nome', 'Nome', None), ('codigo', 'Código', None),
                                  ('unidade', 'Unidade', 'un')]:
        result[field] = text(data.get(field, default), label)
    for field in ('quantidade', 'preco_custo', 'estoque_min'):
        default = 5 if field == 'estoque_min' else 0
        result[field] = number(data.get(field, default), field, minimum=0,
                               integer=field == 'estoque_min')
    for field in ('preco_venda', 'preco_embalagem', 'sub_qtd_por_un', 'unid_por_fardo', 'unid_embalagem'):
        value = data.get(field)
        result[field] = None if value in (None, '') else number(
            value, field, minimum=0, integer=field == 'unid_embalagem')
        if field in ('sub_qtd_por_un', 'unid_por_fardo', 'unid_embalagem') and result[field] == 0:
            result[field] = None
    result['categoria_id'] = (None if data.get('categoria_id') in (None, '')
                              else number(data['categoria_id'], 'Categoria', minimum=1, integer=True))
    for field in ('sub_unidade', 'tipo_embalagem', 'codigo_barras'):
        result[field] = text(data.get(field), field, required=False) or None
    result['unid_fardo_label'] = text(data.get('unid_fardo_label') or 'fd', 'Nome do agrupamento')
    result['validade'] = iso_date(data['validade'], 'Validade') if data.get('validade') else None
    return result


def _check_product_links(db, data, product_id=None):
    if data['categoria_id'] is not None and not db.execute(
            'SELECT 1 FROM categorias WHERE id=?', (data['categoria_id'],)).fetchone():
        raise ValidationError('Categoria não encontrada.')
    if data['codigo_barras']:
        existing = db.execute('SELECT id FROM produtos WHERE codigo_barras=? AND id!=?',
                              (data['codigo_barras'], product_id or 0)).fetchone()
        if existing:
            raise ValidationError('Código de barras já usado em outro produto.')


@login_requerido
@permissao_requerida("produtos")
def criar_produto():
    data = _product_data(json_object())
    fields = ('nome', 'codigo', 'unidade', 'categoria_id', 'quantidade', 'sub_qtd_por_un',
              'sub_unidade', 'unid_por_fardo', 'unid_fardo_label', 'validade', 'preco_custo',
              'preco_venda', 'estoque_min', 'preco_embalagem', 'tipo_embalagem',
              'unid_embalagem', 'codigo_barras')
    with closing(get_db()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        _check_product_links(db, data)
        cur = db.execute(f"INSERT INTO produtos ({','.join(fields)},criado_em) VALUES ({','.join('?' for _ in fields)},?)",
                         tuple(data[f] for f in fields) + (datetime.now().isoformat(),))
        return jsonify(ok=True, id=cur.lastrowid), 201


@login_requerido
@permissao_requerida("produtos")
def atualizar_produto(pid):
    data = _product_data(json_object())
    fields = ('nome', 'codigo', 'unidade', 'categoria_id', 'sub_qtd_por_un', 'sub_unidade',
              'unid_por_fardo', 'unid_fardo_label', 'validade', 'preco_custo', 'preco_venda',
              'estoque_min', 'preco_embalagem', 'tipo_embalagem', 'unid_embalagem', 'codigo_barras')
    with closing(get_db()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT * FROM produtos WHERE id=?', (pid,)).fetchone()
        if not previous:
            abort(404, description='Produto não encontrado.')
        _check_product_links(db, data, pid)
        db.execute(f"UPDATE produtos SET {','.join(f+'=?' for f in fields)} WHERE id=?",
                   tuple(data[f] for f in fields) + (pid,))
        changes = []
        if previous['preco_custo'] != data['preco_custo']:
            changes.append(f"preço de custo: R${previous['preco_custo']:.2f} → R${data['preco_custo']:.2f}")
        if (previous['preco_venda'] or None) != data['preco_venda']:
            changes.append(f"preço de venda: {fmt_rs_log(previous['preco_venda'])} → {fmt_rs_log(data['preco_venda'])}")
        if previous['estoque_min'] != data['estoque_min']:
            changes.append(f"estoque mínimo: {previous['estoque_min']} → {data['estoque_min']}")
        if previous['nome'] != data['nome']:
            changes.append(f"nome: {previous['nome']} → {data['nome']}")
        if changes:
            registrar_auditoria(db, 'editou', 'produto', pid, data['nome'], '; '.join(changes))
    return jsonify(ok=True)


@login_requerido
@permissao_requerida("produtos")
def alternar_ativo_produto(pid):
    d = json_object()
    if 'ativo' in d and (not isinstance(d['ativo'], (bool, int)) or d['ativo'] not in (0, 1)):
        raise ValidationError('Ativo deve ser verdadeiro ou falso.')
    with closing(get_db()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        produto = db.execute('SELECT nome, ativo FROM produtos WHERE id=?', (pid,)).fetchone()
        if not produto:
            abort(404, description='Produto não encontrado.')
        novo_ativo = int(d.get('ativo', not produto['ativo']))
        db.execute('UPDATE produtos SET ativo=? WHERE id=?', (novo_ativo, pid))
        registrar_auditoria(db, 'ativou' if novo_ativo else 'desativou', 'produto', pid, produto['nome'],
                            'Produto reativado' if novo_ativo else 'Produto desativado (fora de uso temporariamente)')
    return jsonify({"ok":True,"ativo":bool(novo_ativo)})

@login_requerido
@permissao_requerida("produtos")
def deletar_produto(pid):
    with closing(get_db()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        produto=db.execute("SELECT nome FROM produtos WHERE id=?",(pid,)).fetchone()
        if not produto:
            return jsonify({"erro":"Produto não encontrado"}),404
        # Exclusão física só é permitida se não houver histórico vinculado
        # (movimentações ou uso em fichas de custo). Isso evita apagar dados
        # de auditoria/custeio por engano; para tirar um produto de uso sem
        # perder histórico, use o botão de ativar/desativar.
        tem_mov = db.execute("SELECT 1 FROM movimentacoes WHERE produto_id=? LIMIT 1",(pid,)).fetchone()
        tem_ficha = db.execute("SELECT 1 FROM ficha_ingredientes WHERE produto_id=? LIMIT 1",(pid,)).fetchone()
        tem_inventario = db.execute('SELECT 1 FROM inventario_itens WHERE produto_id=? LIMIT 1', (pid,)).fetchone()
        if tem_mov or tem_ficha or tem_inventario:
            return jsonify({"erro":"Este produto tem histórico de movimentações ou é usado em fichas de custo. "
                                    "Para não perder esses dados, desative o produto em vez de excluí-lo."}),400
        db.execute("DELETE FROM produtos WHERE id=?",(pid,))
        registrar_auditoria(db,"excluiu","produto",pid,produto["nome"])
        return jsonify({"ok":True})

# ── Movimentações ─────────────────────────────────────────────────────────────
@login_requerido
def listar_movimentacoes():
    db=get_db()
    rows=db.execute("""
        SELECT m.*, p.nome AS produto, p.codigo, p.unidade, u.nome AS usuario_nome
        FROM movimentacoes m
        JOIN produtos p ON p.id=m.produto_id
        LEFT JOIN usuarios u ON u.id=m.usuario_id
        ORDER BY m.criado_em DESC LIMIT 100""").fetchall()
    db.close(); return jsonify([dict(r) for r in rows])

def _movement_data(data):
    if not isinstance(data, dict):
        raise ValidationError('Cada movimentação deve ser um objeto JSON.')
    tipo = data.get('tipo')
    if tipo not in ('entrada', 'saida', 'ajuste'):
        raise ValidationError('Tipo de movimentação inválido.')
    quantity = number(data.get('quantidade'), 'Quantidade', minimum=0)
    if tipo != 'ajuste' and quantity == 0:
        raise ValidationError('Quantidade deve ser maior que zero.')
    return {
        'produto_id': number(data.get('produto_id'), 'Produto', minimum=1, integer=True),
        'tipo': tipo, 'quantidade': quantity,
        'observacao': text(data.get('observacao'), 'Observação', required=False),
        'validade': iso_date(data['validade'], 'Validade') if data.get('validade') else None,
    }


def _apply_movement(db, data):
    pid, tipo, quantity = data['produto_id'], data['tipo'], data['quantidade']
    product = db.execute('SELECT quantidade, validade FROM produtos WHERE id=?', (pid,)).fetchone()
    if not product:
        abort(404, description='Produto não encontrado.')
    if tipo == 'entrada':
        new_quantity = number(product['quantidade'] + quantity, 'Estoque resultante', minimum=0)
        db.execute('UPDATE produtos SET quantidade=? WHERE id=?', (new_quantity, pid))
    elif tipo == 'saida':
        changed = db.execute('UPDATE produtos SET quantidade=quantidade-? WHERE id=? AND quantidade>=?',
                             (quantity, pid, quantity))
        if not changed.rowcount:
            raise ValidationError('Estoque insuficiente.')
    else:
        db.execute('UPDATE produtos SET quantidade=? WHERE id=?', (quantity, pid))
    if tipo == 'entrada' and data['validade'] and (not product['validade'] or data['validade'] < product['validade']):
        db.execute('UPDATE produtos SET validade=? WHERE id=?', (data['validade'], pid))
    db.execute('INSERT INTO movimentacoes\n                  (produto_id,usuario_id,tipo,quantidade,observacao,criado_em) VALUES (?,?,?,?,?,?)',
               (pid, session['usuario_id'], tipo, quantity, data['observacao'], datetime.now().isoformat()))
    current = db.execute('SELECT quantidade FROM produtos WHERE id=?', (pid,)).fetchone()[0]
    return {'produto_id': pid, 'novo_estoque': current}


@login_requerido
def registrar_movimentacao():
    payload = json_object()
    data = _movement_data(payload)
    def apply(db):
        result = _apply_movement(db, data)
        return {'ok': True, 'novo_estoque': result['novo_estoque']}
    if 'operacao_id' in payload:
        result, status = run_operation(payload, apply)
        return jsonify(result), status
    with closing(get_db()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        result = apply(db)
    return jsonify(result), 201


@login_requerido
def registrar_lote():
    payload = json_object()
    items = payload.get('itens')
    if not isinstance(items, list) or not items or len(items) > 500:
        raise ValidationError('Informe entre 1 e 500 movimentações.')
    validated = [_movement_data(item) for item in items]
    def apply(db):
        results = [_apply_movement(db, data) for data in validated]
        return {'ok': True, 'resultados': results}
    result, status = run_operation(payload, apply)
    return jsonify(result), status



def register_routes(app):
    app.route("/api/categorias")(listar_categorias)
    app.route("/api/produtos")(listar_produtos)
    app.route("/api/produtos",methods=["POST"])(criar_produto)
    app.route("/api/produtos/<int:pid>",methods=["PUT"])(atualizar_produto)
    app.route("/api/produtos/<int:pid>/ativo",methods=["PUT"])(alternar_ativo_produto)
    app.route("/api/produtos/<int:pid>",methods=["DELETE"])(deletar_produto)
    app.route("/api/movimentacoes")(listar_movimentacoes)
    app.route("/api/movimentacoes",methods=["POST"])(registrar_movimentacao)
    app.route("/api/movimentacoes/lote",methods=["POST"])(registrar_lote)
