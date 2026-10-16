"""Rotas: reports."""
from datetime import datetime
from flask import request, jsonify, session
from ..database import get_db
from ..security import PERFIS, login_requerido

@login_requerido
def relatorio_consumo():
    """Retorna o total de saídas por produto dentro de um período informado.
    Parâmetros: inicio (YYYY-MM-DD), fim (YYYY-MM-DD)."""
    inicio = request.args.get("inicio", "").strip()
    fim = request.args.get("fim", "").strip()
    if not inicio or not fim:
        return jsonify({"erro": "Informe data de início e fim"}), 400
    try:
        datetime.strptime(inicio, "%Y-%m-%d")
        datetime.strptime(fim, "%Y-%m-%d")
    except ValueError:
        return jsonify({"erro": "Formato de data inválido. Use YYYY-MM-DD"}), 400
    if inicio > fim:
        return jsonify({"erro": "Data de início não pode ser maior que a data fim"}), 400

    # Inclui o dia final completo (até 23:59:59)
    inicio_iso = f"{inicio}T00:00:00"
    fim_iso = f"{fim}T23:59:59"

    db = get_db()
    rows = db.execute("""
        SELECT p.id, p.nome, p.codigo, p.unidade,
               COALESCE(c.nome,'Sem categoria') AS categoria,
               SUM(m.quantidade) AS total_saida,
               COUNT(m.id) AS num_movimentacoes,
               p.preco_custo
        FROM movimentacoes m
        JOIN produtos p ON p.id = m.produto_id
        LEFT JOIN categorias c ON c.id = p.categoria_id
        WHERE m.tipo = 'saida' AND m.criado_em BETWEEN ? AND ?
        GROUP BY p.id
        ORDER BY total_saida DESC
    """, (inicio_iso, fim_iso)).fetchall()
    db.close()

    itens = [dict(r) for r in rows]
    for item in itens:
        item["valor_consumido"] = round((item["total_saida"] or 0) * (item["preco_custo"] or 0), 2)

    total_geral_qtd = sum(i["total_saida"] or 0 for i in itens)
    total_geral_valor = sum(i["valor_consumido"] for i in itens)

    return jsonify({
        "itens": itens,
        "total_produtos": len(itens),
        "total_quantidade": round(total_geral_qtd, 2),
        "total_valor": round(total_geral_valor, 2),
        "periodo": {"inicio": inicio, "fim": fim}
    })


@login_requerido
def listar_log_auditoria():
    if session.get("perfil")!="admin":
        return jsonify({"erro":"Apenas o administrador pode ver o log de auditoria"}),403
    db=get_db()
    rows=db.execute("""SELECT l.*, u.nome AS usuario_nome
        FROM log_auditoria l LEFT JOIN usuarios u ON u.id=l.usuario_id
        ORDER BY l.criado_em DESC LIMIT 500""").fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@login_requerido
def listar_perfis():
    return jsonify([{"id":k,"label":v["label"],"permissoes":v["permissoes"]} for k,v in PERFIS.items()])



def register_routes(app):
    app.route("/api/relatorios/consumo")(relatorio_consumo)
    app.route("/api/log-auditoria")(listar_log_auditoria)
    app.route("/api/perfis")(listar_perfis)
