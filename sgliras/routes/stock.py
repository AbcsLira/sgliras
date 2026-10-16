"""Rotas: stock."""
import sqlite3
from datetime import datetime
from flask import request, jsonify, session
from ..database import get_db
from ..security import login_requerido, permissao_requerida
from ..audit import registrar_auditoria, fmt_rs_log

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

@login_requerido
@permissao_requerida("produtos")
def criar_produto():
    d=request.get_json(silent=True) or {}; db=get_db()
    try:
        pv=d.get("preco_venda"); pv=None if pv in ("",None) else float(pv)
        sq=d.get("sub_qtd_por_un"); sq=None if sq in ("",None,0,"0") else float(sq)
        su=d.get("sub_unidade") or None
        upf=d.get("unid_por_fardo"); upf=None if upf in ("",None,0,"0") else float(upf)
        ufl=d.get("unid_fardo_label") or "fd"
        val=d.get("validade") or None
        pe=d.get("preco_embalagem"); pe=None if pe in ("",None,0,"0") else float(pe)
        te=d.get("tipo_embalagem") or None
        ue=d.get("unid_embalagem"); ue=None if ue in ("",None,0,"0") else int(ue)
        cb=d.get("codigo_barras") or None
        if cb:
            existe=db.execute("SELECT nome FROM produtos WHERE codigo_barras=?",(cb,)).fetchone()
            if existe:
                return jsonify({"erro":f"Código de barras já usado no produto \"{existe['nome']}\""}),400
        cur = db.execute("""INSERT INTO produtos
            (nome,codigo,unidade,categoria_id,quantidade,
             sub_qtd_por_un,sub_unidade,unid_por_fardo,unid_fardo_label,validade,
             preco_custo,preco_venda,estoque_min,preco_embalagem,tipo_embalagem,unid_embalagem,codigo_barras,criado_em)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d["nome"],d["codigo"],d.get("unidade","un"),d.get("categoria_id"),
             d.get("quantidade",0),sq,su,upf,ufl,val,d.get("preco_custo",0),pv,d.get("estoque_min",5),
             pe,te,ue,cb,datetime.now().isoformat()))
        db.commit(); return jsonify({"ok":True,"id":cur.lastrowid}),201
    except sqlite3.IntegrityError as e: return jsonify({"erro":str(e)}),400
    finally: db.close()

@login_requerido
@permissao_requerida("produtos")
def atualizar_produto(pid):
    d=request.get_json(silent=True) or {}; db=get_db()
    anterior=db.execute("SELECT * FROM produtos WHERE id=?",(pid,)).fetchone()
    pv=d.get("preco_venda"); pv=None if pv in ("",None) else float(pv)
    sq=d.get("sub_qtd_por_un"); sq=None if sq in ("",None,0,"0") else float(sq)
    su=d.get("sub_unidade") or None
    upf=d.get("unid_por_fardo"); upf=None if upf in ("",None,0,"0") else float(upf)
    ufl=d.get("unid_fardo_label") or "fd"
    val=d.get("validade") or None
    pe=d.get("preco_embalagem"); pe=None if pe in ("",None,0,"0") else float(pe)
    te=d.get("tipo_embalagem") or None
    ue=d.get("unid_embalagem"); ue=None if ue in ("",None,0,"0") else int(ue)
    cb=d.get("codigo_barras") or None
    if cb:
        existe=db.execute("SELECT nome FROM produtos WHERE codigo_barras=? AND id!=?",(cb,pid)).fetchone()
        if existe:
            db.close(); return jsonify({"erro":f"Código de barras já usado no produto \"{existe['nome']}\""}),400
    db.execute("""UPDATE produtos SET nome=?,codigo=?,unidade=?,categoria_id=?,
                  sub_qtd_por_un=?,sub_unidade=?,unid_por_fardo=?,unid_fardo_label=?,validade=?,
                  preco_custo=?,preco_venda=?,estoque_min=?,
                  preco_embalagem=?,tipo_embalagem=?,unid_embalagem=?,codigo_barras=? WHERE id=?""",
               (d["nome"],d["codigo"],d.get("unidade","un"),d.get("categoria_id"),
                sq,su,upf,ufl,val,d.get("preco_custo",0),pv,d.get("estoque_min",5),
                pe,te,ue,cb,pid))
    if anterior:
        mudancas=[]
        novo_custo=d.get("preco_custo",0)
        if anterior["preco_custo"]!=novo_custo:
            mudancas.append(f"preço de custo: R${anterior['preco_custo']:.2f} → R${float(novo_custo):.2f}")
        if (anterior["preco_venda"] or None)!=pv:
            mudancas.append(f"preço de venda: {fmt_rs_log(anterior['preco_venda'])} → {fmt_rs_log(pv)}")
        if anterior["estoque_min"]!=d.get("estoque_min",5):
            mudancas.append(f"estoque mínimo: {anterior['estoque_min']} → {d.get('estoque_min',5)}")
        if anterior["nome"]!=d["nome"]:
            mudancas.append(f"nome: {anterior['nome']} → {d['nome']}")
        if mudancas:
            registrar_auditoria(db,"editou","produto",pid,d["nome"],"; ".join(mudancas))
    db.commit(); db.close(); return jsonify({"ok":True})

@login_requerido
@permissao_requerida("produtos")
def alternar_ativo_produto(pid):
    d=request.get_json(silent=True) or {}
    db=get_db()
    produto=db.execute("SELECT nome, ativo FROM produtos WHERE id=?",(pid,)).fetchone()
    if not produto:
        db.close(); return jsonify({"erro":"Produto não encontrado"}),404
    novo_ativo = 1 if d.get("ativo", not produto["ativo"]) else 0
    db.execute("UPDATE produtos SET ativo=? WHERE id=?",(novo_ativo,pid))
    registrar_auditoria(db,"ativou" if novo_ativo else "desativou","produto",pid,produto["nome"],
                         "Produto reativado" if novo_ativo else "Produto desativado (fora de uso temporariamente)")
    db.commit(); db.close()
    return jsonify({"ok":True,"ativo":bool(novo_ativo)})

@login_requerido
@permissao_requerida("produtos")
def deletar_produto(pid):
    db=get_db()
    try:
        produto=db.execute("SELECT nome FROM produtos WHERE id=?",(pid,)).fetchone()
        if not produto:
            return jsonify({"erro":"Produto não encontrado"}),404
        # Exclusão física só é permitida se não houver histórico vinculado
        # (movimentações ou uso em fichas de custo). Isso evita apagar dados
        # de auditoria/custeio por engano; para tirar um produto de uso sem
        # perder histórico, use o botão de ativar/desativar.
        tem_mov = db.execute("SELECT 1 FROM movimentacoes WHERE produto_id=? LIMIT 1",(pid,)).fetchone()
        tem_ficha = db.execute("SELECT 1 FROM ficha_ingredientes WHERE produto_id=? LIMIT 1",(pid,)).fetchone()
        if tem_mov or tem_ficha:
            return jsonify({"erro":"Este produto tem histórico de movimentações ou é usado em fichas de custo. "
                                    "Para não perder esses dados, desative o produto em vez de excluí-lo."}),400
        db.execute("DELETE FROM produtos WHERE id=?",(pid,))
        registrar_auditoria(db,"excluiu","produto",pid,produto["nome"])
        db.commit()
        return jsonify({"ok":True})
    except Exception as e:
        db.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        db.close()

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

@login_requerido
def registrar_movimentacao():
    d=request.get_json(silent=True) or {}
    pid=d.get("produto_id")
    tipo=d.get("tipo")
    if not pid or not tipo:
        return jsonify({"erro": "produto_id e tipo são obrigatórios"}), 400
    try:
        qtd=float(d.get("quantidade", 0))
        if qtd <= 0 and tipo != "ajuste":
            return jsonify({"erro": "Quantidade deve ser maior que zero"}), 400
    except (TypeError, ValueError):
        return jsonify({"erro": "Quantidade inválida"}), 400
    validade_lote = d.get("validade") or None
    db=get_db()
    try:
        p=db.execute("SELECT quantidade, validade FROM produtos WHERE id=?",(pid,)).fetchone()
        if not p: return jsonify({"erro":"Produto não encontrado"}),404

        # Atualização atômica direto no SQL (em vez de ler, calcular em Python e
        # gravar de volta) para evitar "lost update" quando duas requisições
        # mexem no mesmo produto ao mesmo tempo (ex: dois caixas simultâneos).
        if tipo=="entrada":
            db.execute("UPDATE produtos SET quantidade = quantidade + ? WHERE id=?",(qtd,pid))
        elif tipo=="saida":
            cur=db.execute(
                "UPDATE produtos SET quantidade = quantidade - ? WHERE id=? AND quantidade >= ?",
                (qtd,pid,qtd)
            )
            if cur.rowcount==0:
                return jsonify({"erro":"Estoque insuficiente"}),400
        elif tipo=="ajuste":
            db.execute("UPDATE produtos SET quantidade=? WHERE id=?",(qtd,pid))

        nova=db.execute("SELECT quantidade FROM produtos WHERE id=?",(pid,)).fetchone()["quantidade"]

        # Em entradas com validade informada, atualiza a validade do produto
        # se for mais próxima (menor) que a atual cadastrada, ou se ainda não houver validade
        if tipo == "entrada" and validade_lote:
            validade_atual = p["validade"]
            if not validade_atual or validade_lote < validade_atual:
                db.execute("UPDATE produtos SET validade=? WHERE id=?", (validade_lote, pid))

        db.execute("INSERT INTO movimentacoes (produto_id,usuario_id,tipo,quantidade,observacao,criado_em) VALUES (?,?,?,?,?,?)",
                   (pid,session["usuario_id"],tipo,qtd,d.get("observacao",""),datetime.now().isoformat()))
        db.commit(); return jsonify({"ok":True,"novo_estoque":nova}),201
    finally: db.close()


def register_routes(app):
    app.route("/api/categorias")(listar_categorias)
    app.route("/api/produtos")(listar_produtos)
    app.route("/api/produtos",methods=["POST"])(criar_produto)
    app.route("/api/produtos/<int:pid>",methods=["PUT"])(atualizar_produto)
    app.route("/api/produtos/<int:pid>/ativo",methods=["PUT"])(alternar_ativo_produto)
    app.route("/api/produtos/<int:pid>",methods=["DELETE"])(deletar_produto)
    app.route("/api/movimentacoes")(listar_movimentacoes)
    app.route("/api/movimentacoes",methods=["POST"])(registrar_movimentacao)
