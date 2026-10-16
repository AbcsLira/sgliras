"""Rotas: recipes."""
from datetime import datetime
from flask import request, jsonify, session
from ..banco_dados import get_db
from ..seguranca import login_requerido, permissao_requerida
from ..auditoria import registrar_auditoria, fmt_rs_log

@login_requerido
@permissao_requerida("fichas")
def listar_fichas():
    db=get_db(); fichas=db.execute("SELECT * FROM fichas ORDER BY nome").fetchall(); res=[]
    globais_ativos=db.execute("SELECT * FROM custos_fixos_globais WHERE ativo=1").fetchall()
    globais_ativos=[dict(g) for g in globais_ativos]
    for f in fichas:
        f=dict(f)
        ings=db.execute("""SELECT fi.id,fi.quantidade,fi.unidade,
                   p.id AS produto_id,p.nome AS produto_nome,p.codigo,p.preco_custo
            FROM ficha_ingredientes fi JOIN produtos p ON p.id=fi.produto_id
            WHERE fi.ficha_id=? ORDER BY p.nome""",(f["id"],)).fetchall()
        f["ingredientes"]=[dict(i) for i in ings]

        custos_fixos=db.execute("""SELECT ffx.id AS vinculo_id, cf.id AS custo_fixo_id, cf.nome, cf.categoria, cf.valor
            FROM ficha_custos_fixos ffx JOIN custos_fixos cf ON cf.id=ffx.custo_fixo_id
            WHERE ffx.ficha_id=? ORDER BY cf.nome""",(f["id"],)).fetchall()
        f["custos_fixos"]=[dict(c) for c in custos_fixos]

        custo_ingredientes=sum(i["preco_custo"]*i["quantidade"] for i in f["ingredientes"])
        custo_fixos_total=sum(c["valor"] for c in f["custos_fixos"])

        # Custos fixos globais (%): aplicados sobre o preço de venda, em todas as fichas ativas
        pv_bruto=f.get("preco_venda") or 0
        custos_globais_aplicados=[]
        custo_globais_total=0
        for g in globais_ativos:
            valor_aplicado=round(pv_bruto*(g["percentual"]/100),4)
            custos_globais_aplicados.append({"nome":g["nome"],"percentual":g["percentual"],"valor_aplicado":valor_aplicado})
            custo_globais_total+=valor_aplicado
        f["custos_fixos_globais"]=custos_globais_aplicados

        custo=custo_ingredientes+custo_fixos_total+custo_globais_total
        f["custo_total"]=round(custo,4); f["custo_porcao"]=round(custo/f["rendimento"],4) if f["rendimento"] else 0
        pv=f.get("preco_venda")
        if pv and pv>0 and f["custo_porcao"]>0:
            f["lucro_porcao"]=round(pv-f["custo_porcao"],4); f["margem_pct"]=round((f["lucro_porcao"]/f["custo_porcao"])*100,2)
        else: f["lucro_porcao"]=f["margem_pct"]=None
        res.append(f)
    db.close(); return jsonify(res)

@login_requerido
@permissao_requerida("fichas")
def criar_ficha():
    d=request.get_json(silent=True) or {}; db=get_db()
    try:
        pv=d.get("preco_venda"); pv=None if pv in ("",None) else float(pv)
        cur=db.execute("INSERT INTO fichas (nome,categoria,rendimento,preco_venda,observacao,criado_em) VALUES (?,?,?,?,?,?)",
                       (d["nome"],d.get("categoria","Sanduíche"),d.get("rendimento",1),pv,d.get("observacao",""),datetime.now().isoformat()))
        fid=cur.lastrowid
        for i in d.get("ingredientes",[]):
            db.execute("INSERT INTO ficha_ingredientes (ficha_id,produto_id,quantidade,unidade) VALUES (?,?,?,?)",
                       (fid,i["produto_id"],i["quantidade"],i["unidade"]))
        if pv is not None:
            db.execute("INSERT INTO ficha_preco_historico (ficha_id,preco_anterior,preco_novo,usuario_id,criado_em) VALUES (?,?,?,?,?)",
                       (fid,None,pv,session.get("usuario_id"),datetime.now().isoformat()))
        db.commit(); return jsonify({"ok":True,"id":fid}),201
    finally: db.close()

@login_requerido
@permissao_requerida("fichas")
def atualizar_ficha(fid):
    d=request.get_json(silent=True) or {}; db=get_db()
    try:
        pv=d.get("preco_venda"); pv=None if pv in ("",None) else float(pv)
        anterior=db.execute("SELECT nome,categoria,rendimento,preco_venda FROM fichas WHERE id=?",(fid,)).fetchone()
        preco_anterior=anterior["preco_venda"] if anterior else None
        db.execute("UPDATE fichas SET nome=?,categoria=?,rendimento=?,preco_venda=?,observacao=? WHERE id=?",
                   (d["nome"],d.get("categoria","Sanduíche"),d.get("rendimento",1),pv,d.get("observacao",""),fid))
        db.execute("DELETE FROM ficha_ingredientes WHERE ficha_id=?",(fid,))
        for i in d.get("ingredientes",[]):
            db.execute("INSERT INTO ficha_ingredientes (ficha_id,produto_id,quantidade,unidade) VALUES (?,?,?,?)",
                       (fid,i["produto_id"],i["quantidade"],i["unidade"]))
        # Só registra no histórico de preço se o preço de venda realmente mudou
        if pv != preco_anterior:
            db.execute("INSERT INTO ficha_preco_historico (ficha_id,preco_anterior,preco_novo,usuario_id,criado_em) VALUES (?,?,?,?,?)",
                       (fid,preco_anterior,pv,session.get("usuario_id"),datetime.now().isoformat()))
        if anterior:
            mudancas=[]
            if anterior["nome"]!=d["nome"]:
                mudancas.append(f"nome: {anterior['nome']} → {d['nome']}")
            if anterior["categoria"]!=d.get("categoria","Sanduíche"):
                mudancas.append(f"categoria: {anterior['categoria']} → {d.get('categoria','Sanduíche')}")
            if anterior["rendimento"]!=d.get("rendimento",1):
                mudancas.append(f"rendimento: {anterior['rendimento']} → {d.get('rendimento',1)}")
            if pv!=preco_anterior:
                mudancas.append(f"preço de venda: {fmt_rs_log(preco_anterior)} → {fmt_rs_log(pv)}")
            if mudancas:
                registrar_auditoria(db,"editou","ficha",fid,d["nome"],"; ".join(mudancas))
        db.commit(); return jsonify({"ok":True})
    finally: db.close()

@login_requerido
@permissao_requerida("fichas")
def deletar_ficha(fid):
    db=get_db()
    try:
        ficha=db.execute("SELECT nome FROM fichas WHERE id=?",(fid,)).fetchone()
        db.execute("DELETE FROM fichas WHERE id=?",(fid,))
        if ficha:
            registrar_auditoria(db,"excluiu","ficha",fid,ficha["nome"])
        db.commit()
        return jsonify({"ok":True})
    except Exception as e:
        db.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        db.close()


@login_requerido
@permissao_requerida("fichas")
def historico_preco_ficha(fid):
    db=get_db()
    rows=db.execute("""SELECT h.*, u.usuario AS usuario_nome
        FROM ficha_preco_historico h LEFT JOIN usuarios u ON u.id=h.usuario_id
        WHERE h.ficha_id=? ORDER BY h.criado_em DESC""",(fid,)).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


# ── Custos Fixos (cadastro reutilizável: Salada, Embalagem, Pão, Massa, etc) ────
@login_requerido
@permissao_requerida("fichas")
def listar_custos_fixos():
    db=get_db()
    rows=db.execute("SELECT * FROM custos_fixos ORDER BY categoria, nome").fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@login_requerido
@permissao_requerida("fichas")
def criar_custo_fixo():
    d=request.get_json(silent=True) or {}; db=get_db()
    try:
        cur=db.execute("INSERT INTO custos_fixos (nome,categoria,valor,atualizado_em) VALUES (?,?,?,?)",
                        (d["nome"], d.get("categoria","Geral"), float(d.get("valor",0)), datetime.now().isoformat()))
        db.commit()
        return jsonify({"ok":True,"id":cur.lastrowid}),201
    finally:
        db.close()


@login_requerido
@permissao_requerida("fichas")
def atualizar_custo_fixo(cid):
    d=request.get_json(silent=True) or {}; db=get_db()
    db.execute("UPDATE custos_fixos SET nome=?,categoria=?,valor=?,atualizado_em=? WHERE id=?",
               (d["nome"], d.get("categoria","Geral"), float(d.get("valor",0)), datetime.now().isoformat(), cid))
    db.commit(); db.close()
    return jsonify({"ok":True})


@login_requerido
@permissao_requerida("fichas")
def deletar_custo_fixo(cid):
    db=get_db()
    try:
        db.execute("DELETE FROM ficha_custos_fixos WHERE custo_fixo_id=?",(cid,))
        db.execute("DELETE FROM custos_fixos WHERE id=?",(cid,))
        db.commit()
        return jsonify({"ok":True})
    except Exception as e:
        db.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        db.close()


# ── Vínculo Ficha x Custo Fixo ───────────────────────────────────────────────────
@login_requerido
@permissao_requerida("fichas")
def vincular_custo_fixo(fid):
    d=request.get_json(silent=True) or {}; db=get_db()
    try:
        db.execute("INSERT OR IGNORE INTO ficha_custos_fixos (ficha_id,custo_fixo_id) VALUES (?,?)",
                   (fid, d["custo_fixo_id"]))
        db.commit()
        return jsonify({"ok":True}),201
    finally:
        db.close()


@login_requerido
@permissao_requerida("fichas")
def desvincular_custo_fixo(fid,cid):
    db=get_db()
    db.execute("DELETE FROM ficha_custos_fixos WHERE ficha_id=? AND custo_fixo_id=?",(fid,cid))
    db.commit(); db.close()
    return jsonify({"ok":True})


# ── Custos Fixos Globais (%) — aplicados automaticamente sobre o preço de venda em TODAS as fichas ──
@login_requerido
@permissao_requerida("fichas")
def listar_custos_fixos_globais():
    db=get_db()
    rows=db.execute("SELECT * FROM custos_fixos_globais ORDER BY nome").fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@login_requerido
@permissao_requerida("fichas")
def criar_custo_fixo_global():
    d=request.get_json(silent=True) or {}; db=get_db()
    try:
        cur=db.execute("INSERT INTO custos_fixos_globais (nome,percentual,ativo,atualizado_em) VALUES (?,?,?,?)",
                        (d["nome"], float(d.get("percentual",0)), 1 if d.get("ativo",True) else 0, datetime.now().isoformat()))
        db.commit()
        return jsonify({"ok":True,"id":cur.lastrowid}),201
    finally:
        db.close()


@login_requerido
@permissao_requerida("fichas")
def atualizar_custo_fixo_global(gid):
    d=request.get_json(silent=True) or {}; db=get_db()
    db.execute("UPDATE custos_fixos_globais SET nome=?,percentual=?,ativo=?,atualizado_em=? WHERE id=?",
               (d["nome"], float(d.get("percentual",0)), 1 if d.get("ativo",True) else 0, datetime.now().isoformat(), gid))
    db.commit(); db.close()
    return jsonify({"ok":True})


@login_requerido
@permissao_requerida("fichas")
def deletar_custo_fixo_global(gid):
    db=get_db()
    try:
        db.execute("DELETE FROM custos_fixos_globais WHERE id=?",(gid,))
        db.commit()
        return jsonify({"ok":True})
    except Exception as e:
        db.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        db.close()



def register_routes(app):
    app.route("/api/fichas")(listar_fichas)
    app.route("/api/fichas",methods=["POST"])(criar_ficha)
    app.route("/api/fichas/<int:fid>",methods=["PUT"])(atualizar_ficha)
    app.route("/api/fichas/<int:fid>",methods=["DELETE"])(deletar_ficha)
    app.route("/api/fichas/<int:fid>/historico-preco")(historico_preco_ficha)
    app.route("/api/custos-fixos")(listar_custos_fixos)
    app.route("/api/custos-fixos",methods=["POST"])(criar_custo_fixo)
    app.route("/api/custos-fixos/<int:cid>",methods=["PUT"])(atualizar_custo_fixo)
    app.route("/api/custos-fixos/<int:cid>",methods=["DELETE"])(deletar_custo_fixo)
    app.route("/api/fichas/<int:fid>/custos-fixos",methods=["POST"])(vincular_custo_fixo)
    app.route("/api/fichas/<int:fid>/custos-fixos/<int:cid>",methods=["DELETE"])(desvincular_custo_fixo)
    app.route("/api/custos-fixos-globais")(listar_custos_fixos_globais)
    app.route("/api/custos-fixos-globais",methods=["POST"])(criar_custo_fixo_global)
    app.route("/api/custos-fixos-globais/<int:gid>",methods=["PUT"])(atualizar_custo_fixo_global)
    app.route("/api/custos-fixos-globais/<int:gid>",methods=["DELETE"])(deletar_custo_fixo_global)
