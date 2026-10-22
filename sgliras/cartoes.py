"""Condições comerciais, vendas e recebíveis de cartões em centavos inteiros."""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import re
import unicodedata

from werkzeug.exceptions import Conflict, NotFound

from .validacao import ValidationError, iso_date, number, text


OPERADORAS = (
    {"id": "cielo", "nome": "Cielo", "cor": "#168bd2"},
    {"id": "rede", "nome": "Rede", "cor": "#f58220"},
    {"id": "sipag", "nome": "Sipag", "cor": "#19964b"},
)
MODALIDADES = (
    {"id": "debito", "nome": "Débito"},
    {"id": "credito", "nome": "Crédito à vista"},
    {"id": "credito_2x", "nome": "Crédito em 2x"},
    {"id": "voucher", "nome": "Voucher"},
)


def inicializar_tabelas(db):
    """Participa da transação de init_db, sem executescript/commit intermediário."""
    db.execute("""CREATE TABLE IF NOT EXISTS fin_cartoes_condicoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operadora_id TEXT NOT NULL CHECK(operadora_id IN ('cielo','rede','sipag')),
        modalidade TEXT NOT NULL CHECK(modalidade IN ('debito','credito','credito_2x','voucher')),
        bandeira TEXT NOT NULL DEFAULT '', inicio_vigencia TEXT NOT NULL,
        taxa_percentual TEXT NOT NULL, prazo_dias INTEGER NOT NULL CHECK(prazo_dias BETWEEN 0 AND 365),
        tipo_dias TEXT NOT NULL CHECK(tipo_dias IN ('corridos','uteis')),
        intervalo_parcelas_dias INTEGER,
        usuario_id INTEGER REFERENCES usuarios(id), criado_em TEXT NOT NULL, atualizado_em TEXT NOT NULL,
        UNIQUE(operadora_id,modalidade,bandeira,inicio_vigencia),
        CHECK((modalidade='credito_2x' AND intervalo_parcelas_dias BETWEEN 1 AND 365)
              OR (modalidade!='credito_2x' AND intervalo_parcelas_dias IS NULL))
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS fin_cartoes_vendas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operadora_id TEXT NOT NULL CHECK(operadora_id IN ('cielo','rede','sipag')),
        modalidade TEXT NOT NULL CHECK(modalidade IN ('debito','credito','credito_2x','voucher')),
        bandeira TEXT NOT NULL DEFAULT '', data_venda TEXT NOT NULL,
        bruto_centavos INTEGER NOT NULL CHECK(bruto_centavos>0), observacao TEXT NOT NULL DEFAULT '',
        condicao_id INTEGER REFERENCES fin_cartoes_condicoes(id), taxa_percentual TEXT,
        prazo_dias INTEGER, tipo_dias TEXT, intervalo_parcelas_dias INTEGER,
        usuario_id INTEGER REFERENCES usuarios(id), criado_em TEXT NOT NULL, atualizado_em TEXT NOT NULL,
        UNIQUE(data_venda,operadora_id,modalidade,bandeira)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS fin_cartoes_parcelas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        venda_id INTEGER NOT NULL REFERENCES fin_cartoes_vendas(id) ON DELETE CASCADE,
        parcela INTEGER NOT NULL CHECK(parcela IN (1,2)),
        total_parcelas INTEGER NOT NULL CHECK(total_parcelas IN (1,2) AND parcela<=total_parcelas),
        bruto_centavos INTEGER NOT NULL CHECK(bruto_centavos>=0),
        taxa_centavos INTEGER NOT NULL CHECK(taxa_centavos>=0 AND taxa_centavos<=bruto_centavos),
        liquido_centavos INTEGER NOT NULL CHECK(liquido_centavos=bruto_centavos-taxa_centavos),
        data_prevista TEXT NOT NULL, data_prevista_original TEXT NOT NULL,
        valor_recebido_centavos INTEGER CHECK(valor_recebido_centavos>=0), data_recebimento TEXT,
        observacao_recebimento TEXT NOT NULL DEFAULT '', usuario_recebimento_id INTEGER REFERENCES usuarios(id),
        criado_em TEXT NOT NULL, atualizado_em TEXT NOT NULL, UNIQUE(venda_id,parcela),
        CHECK((valor_recebido_centavos IS NULL AND data_recebimento IS NULL)
              OR (valor_recebido_centavos IS NOT NULL AND data_recebimento IS NOT NULL))
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_cartoes_previsao ON fin_cartoes_parcelas(data_prevista)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_cartoes_recebimento ON fin_cartoes_parcelas(data_recebimento)")


def _objeto(value):
    if not isinstance(value, dict):
        raise ValidationError("Envie os dados como um objeto JSON válido.")
    return value


def _opcao(value, opcoes, nome):
    if value not in opcoes:
        raise ValidationError(f"{nome} inválida.")
    return value


def _bandeira(value):
    value = unicodedata.normalize("NFC", text(value, "Bandeira", required=False)).casefold()
    if len(value) > 80:
        raise ValidationError("Bandeira deve ter no máximo 80 caracteres.")
    return value


def _observacao(value):
    value = text(value, "Observação", required=False)
    if len(value) > 2000:
        raise ValidationError("Observação deve ter no máximo 2000 caracteres.")
    return value


def _decimal(value, nome):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValidationError(f"{nome} deve ser um número válido.")
    try:
        resultado = Decimal(str(value))
    except InvalidOperation:
        raise ValidationError(f"{nome} deve ser um número válido.") from None
    if not resultado.is_finite():
        raise ValidationError(f"{nome} deve ser um número finito.")
    return resultado


def centavos(value, nome, permitir_zero=False):
    valor = _decimal(value, nome)
    if valor < 0 or (not permitir_zero and valor == 0) or valor > 10000000:
        raise ValidationError(f"{nome} deve ser {'não negativo' if permitir_zero else 'positivo'} e até R$ 10.000.000,00.")
    if valor != valor.quantize(Decimal("0.01")):
        raise ValidationError(f"{nome} deve ter no máximo duas casas decimais.")
    return int(valor * 100)


def _taxa(value):
    taxa = _decimal(value, "Taxa percentual")
    if not 0 <= taxa <= 100 or taxa != taxa.quantize(Decimal("0.000001")):
        raise ValidationError("Taxa deve estar entre 0 e 100, com no máximo seis casas decimais.")
    return format(taxa.normalize(), "f")


def operadora_filtro(value):
    return _opcao(value, ("", *(op["id"] for op in OPERADORAS)), "Operadora")


def mes_filtro(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value):
        raise ValidationError("Mês deve usar AAAA-MM.")
    iso_date(value + "-01", "Mês")
    return value


def _identificacao(body):
    return {
        "operadora_id": _opcao(body.get("operadora_id"), tuple(op["id"] for op in OPERADORAS), "Operadora"),
        "modalidade": _opcao(body.get("modalidade"), tuple(mod["id"] for mod in MODALIDADES), "Modalidade"),
        "bandeira": _bandeira(body.get("bandeira")),
    }


def dados_venda(body):
    body = _objeto(body)
    return {**_identificacao(body), "data_venda": iso_date(body.get("data_venda"), "Data da venda"),
            "bruto_centavos": centavos(body.get("valor_bruto"), "Valor bruto"),
            "observacao": _observacao(body.get("observacao"))}


def dados_condicao(body):
    body = _objeto(body)
    dados = _identificacao(body)
    prazo = number(body.get("prazo_dias"), "Prazo", minimum=0, integer=True)
    if prazo > 365:
        raise ValidationError("Prazo deve estar entre 0 e 365 dias.")
    intervalo = None
    if dados["modalidade"] == "credito_2x":
        intervalo = number(body.get("intervalo_parcelas_dias"), "Intervalo entre parcelas", minimum=1, integer=True)
        if intervalo > 365:
            raise ValidationError("Intervalo deve estar entre 1 e 365 dias.")
    elif body.get("intervalo_parcelas_dias") is not None:
        raise ValidationError("Somente crédito em 2x permite intervalo entre parcelas.")
    return {**dados, "inicio_vigencia": iso_date(body.get("inicio_vigencia"), "Início da vigência"),
            "taxa_percentual": _taxa(body.get("taxa_percentual")), "prazo_dias": prazo,
            "tipo_dias": _opcao(body.get("tipo_dias"), ("corridos", "uteis"), "Contagem de dias"),
            "intervalo_parcelas_dias": intervalo}


def _auditar(db, usuario_id, acao, entidade, registro_id, detalhes):
    db.execute("""INSERT INTO log_auditoria
        (usuario_id,acao,entidade,entidade_id,detalhes,criado_em) VALUES (?,?,?,?,?,?)""",
               (usuario_id, acao, entidade, registro_id, json.dumps(detalhes, ensure_ascii=False), datetime.now().isoformat()))


def configuracao(db):
    condicoes = [dict(row) for row in db.execute("""SELECT id,operadora_id,modalidade,bandeira,inicio_vigencia,
        taxa_percentual,prazo_dias,tipo_dias,intervalo_parcelas_dias FROM fin_cartoes_condicoes
        ORDER BY operadora_id,modalidade,bandeira,inicio_vigencia DESC""")]
    return {"operadoras": OPERADORAS, "modalidades": MODALIDADES, "condicoes": condicoes}


def salvar_condicao(db, dados, usuario_id):
    campos = tuple(dados)
    antes = db.execute("""SELECT * FROM fin_cartoes_condicoes WHERE operadora_id=? AND modalidade=?
        AND bandeira=? AND inicio_vigencia=?""", tuple(dados[c] for c in (
            "operadora_id", "modalidade", "bandeira", "inicio_vigencia"))).fetchone()
    agora = datetime.now().isoformat()
    if antes:
        registro_id = antes["id"]
        db.execute(f"UPDATE fin_cartoes_condicoes SET {','.join(c+'=?' for c in campos)},usuario_id=?,atualizado_em=? WHERE id=?",
                   (*dados.values(), usuario_id, agora, registro_id))
    else:
        registro_id = db.execute(f"""INSERT INTO fin_cartoes_condicoes
            ({','.join(campos)},usuario_id,criado_em,atualizado_em) VALUES ({','.join('?' for _ in campos)},?,?,?)""",
                                (*dados.values(), usuario_id, agora, agora)).lastrowid
    _auditar(db, usuario_id, "EDITAR" if antes else "CRIAR", "cartoes_condicao", registro_id,
             {"antes": dict(antes) if antes else None, "depois": dados})
    return {"ok": True, "id": registro_id}


def _condicao_vigente(db, venda):
    return db.execute("""SELECT * FROM fin_cartoes_condicoes WHERE operadora_id=? AND modalidade=?
        AND inicio_vigencia<=? AND bandeira IN ('',?)
        ORDER BY CASE WHEN bandeira=? THEN 0 ELSE 1 END,inicio_vigencia DESC LIMIT 1""",
                      (venda["operadora_id"], venda["modalidade"], venda["data_venda"],
                       venda["bandeira"], venda["bandeira"])).fetchone()


def _somar_dias(inicio, quantidade, tipo):
    resultado = date.fromisoformat(inicio)
    try:
        if tipo == "corridos":
            resultado += timedelta(days=quantidade)
        else:
            while quantidade:
                resultado += timedelta(days=1)
                if resultado.weekday() < 5:
                    quantidade -= 1
    except OverflowError:
        raise ValidationError("A previsão ultrapassa o intervalo de datas suportado.") from None
    return resultado.isoformat()


def _dividir_centavos(valor, parcelas):
    base, resto = divmod(valor, parcelas)
    return [base] * (parcelas - 1) + [base + resto]


def _calcular_venda(db, venda):
    condicao = _condicao_vigente(db, venda)
    if condicao is None:
        return False
    total_parcelas = 2 if venda["modalidade"] == "credito_2x" else 1
    taxa_total = int((Decimal(venda["bruto_centavos"]) * Decimal(condicao["taxa_percentual"]) / 100)
                    .quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    brutos = _dividir_centavos(venda["bruto_centavos"], total_parcelas)
    taxas = _dividir_centavos(taxa_total, total_parcelas)
    prevista = _somar_dias(venda["data_venda"], condicao["prazo_dias"], condicao["tipo_dias"])
    agora = datetime.now().isoformat()
    for indice, (bruto, taxa) in enumerate(zip(brutos, taxas), start=1):
        if indice > 1:
            prevista = _somar_dias(prevista, condicao["intervalo_parcelas_dias"], condicao["tipo_dias"])
        db.execute("""INSERT INTO fin_cartoes_parcelas
            (venda_id,parcela,total_parcelas,bruto_centavos,taxa_centavos,liquido_centavos,
             data_prevista,data_prevista_original,criado_em,atualizado_em) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                   (venda["id"], indice, total_parcelas, bruto, taxa, bruto - taxa, prevista, prevista, agora, agora))
    db.execute("""UPDATE fin_cartoes_vendas SET condicao_id=?,taxa_percentual=?,prazo_dias=?,tipo_dias=?,
        intervalo_parcelas_dias=?,atualizado_em=? WHERE id=?""",
               (condicao["id"], condicao["taxa_percentual"], condicao["prazo_dias"], condicao["tipo_dias"],
                condicao["intervalo_parcelas_dias"], agora, venda["id"]))
    return True


def _venda(db, registro_id):
    venda = db.execute("SELECT * FROM fin_cartoes_vendas WHERE id=?", (registro_id,)).fetchone()
    if venda is None:
        raise NotFound("Venda não encontrada.")
    return venda


def _proteger_venda_recebida(db, registro_id):
    if db.execute("SELECT 1 FROM fin_cartoes_parcelas WHERE venda_id=? AND data_recebimento IS NOT NULL",
                  (registro_id,)).fetchone():
        raise Conflict("Estorne os recebimentos antes de editar ou excluir a venda.")


def inserir_venda(db, dados, usuario_id):
    campos, agora = tuple(dados), datetime.now().isoformat()
    registro_id = db.execute(f"""INSERT INTO fin_cartoes_vendas
        ({','.join(campos)},usuario_id,criado_em,atualizado_em) VALUES ({','.join('?' for _ in campos)},?,?,?)""",
                            (*dados.values(), usuario_id, agora, agora)).lastrowid
    calculado = _calcular_venda(db, _venda(db, registro_id))
    _auditar(db, usuario_id, "CRIAR", "cartoes_venda", registro_id, {"depois": dict(_venda(db, registro_id))})
    return {"ok": True, "id": registro_id, "calculado": calculado}


def editar_venda(db, registro_id, dados, usuario_id):
    antes = dict(_venda(db, registro_id))
    _proteger_venda_recebida(db, registro_id)
    db.execute("DELETE FROM fin_cartoes_parcelas WHERE venda_id=?", (registro_id,))
    db.execute(f"""UPDATE fin_cartoes_vendas SET {','.join(c+'=?' for c in dados)},condicao_id=NULL,
        taxa_percentual=NULL,prazo_dias=NULL,tipo_dias=NULL,intervalo_parcelas_dias=NULL,
        usuario_id=?,atualizado_em=? WHERE id=?""", (*dados.values(), usuario_id, datetime.now().isoformat(), registro_id))
    calculado = _calcular_venda(db, _venda(db, registro_id))
    _auditar(db, usuario_id, "EDITAR", "cartoes_venda", registro_id,
             {"antes": antes, "depois": dict(_venda(db, registro_id))})
    return {"ok": True, "calculado": calculado}


def excluir_venda(db, registro_id, usuario_id):
    antes = dict(_venda(db, registro_id))
    _proteger_venda_recebida(db, registro_id)
    db.execute("DELETE FROM fin_cartoes_vendas WHERE id=?", (registro_id,))
    _auditar(db, usuario_id, "EXCLUIR", "cartoes_venda", registro_id, {"antes": antes})
    return {"ok": True}


def calcular_pendentes(db, usuario_id):
    vendas = db.execute("SELECT * FROM fin_cartoes_vendas WHERE condicao_id IS NULL ORDER BY id").fetchall()
    calculadas = 0
    for venda in vendas:
        if _calcular_venda(db, venda):
            calculadas += 1
            _auditar(db, usuario_id, "CALCULAR", "cartoes_venda", venda["id"],
                     {"depois": dict(_venda(db, venda["id"]))})
    return {"ok": True, "calculadas": calculadas, "pendentes": len(vendas) - calculadas}


def listar_vendas(db, mes="", operadora=""):
    operadora_filtro(operadora)
    filtros, parametros = [], []
    if mes:
        mes_filtro(mes)
        filtros.append("data_venda LIKE ?")
        parametros.append(mes + "%")
    if operadora:
        filtros.append("operadora_id=?")
        parametros.append(operadora)
    sql = """SELECT id,operadora_id,modalidade,bandeira,data_venda,bruto_centavos,observacao,
        condicao_id IS NOT NULL AS calculado,taxa_percentual,
        EXISTS(SELECT 1 FROM fin_cartoes_parcelas p WHERE p.venda_id=fin_cartoes_vendas.id
               AND p.data_recebimento IS NOT NULL) AS possui_recebimento FROM fin_cartoes_vendas"""
    if filtros:
        sql += " WHERE " + " AND ".join(filtros)
    vendas = [dict(row) for row in db.execute(sql + " ORDER BY data_venda DESC,id DESC", parametros)]
    for venda in vendas:
        venda["calculado"] = bool(venda["calculado"])
        venda["possui_recebimento"] = bool(venda["possui_recebimento"])
    return vendas


def _parcela(db, registro_id):
    parcela = db.execute("SELECT * FROM fin_cartoes_parcelas WHERE id=?", (registro_id,)).fetchone()
    if parcela is None:
        raise NotFound("Parcela não encontrada.")
    return parcela


def registrar_recebimento(db, registro_id, body, usuario_id):
    body = _objeto(body)
    recebida_em = iso_date(body.get("data_recebimento"), "Data do recebimento")
    valor = centavos(body.get("valor_recebido"), "Valor recebido", permitir_zero=True)
    observacao = _observacao(body.get("observacao"))
    antes = dict(_parcela(db, registro_id))
    if antes["data_recebimento"] is not None:
        if (antes["data_recebimento"] == recebida_em and antes["valor_recebido_centavos"] == valor
                and antes["observacao_recebimento"] == observacao):
            return {"ok": True}
        raise Conflict("Esta parcela já foi recebida. Estorne antes de informar outro recebimento.")
    db.execute("""UPDATE fin_cartoes_parcelas SET valor_recebido_centavos=?,data_recebimento=?,
        observacao_recebimento=?,usuario_recebimento_id=?,atualizado_em=? WHERE id=?""",
               (valor, recebida_em, observacao, usuario_id, datetime.now().isoformat(), registro_id))
    _auditar(db, usuario_id, "RECEBER", "cartoes_parcela", registro_id,
             {"antes": antes, "depois": dict(_parcela(db, registro_id))})
    return {"ok": True}


def estornar_recebimento(db, registro_id, usuario_id):
    antes = dict(_parcela(db, registro_id))
    if antes["data_recebimento"] is None:
        return {"ok": True}
    db.execute("""UPDATE fin_cartoes_parcelas SET valor_recebido_centavos=NULL,data_recebimento=NULL,
        observacao_recebimento='',usuario_recebimento_id=NULL,atualizado_em=? WHERE id=?""",
               (datetime.now().isoformat(), registro_id))
    _auditar(db, usuario_id, "ESTORNAR", "cartoes_parcela", registro_id, {"antes": antes})
    return {"ok": True}


def alterar_previsao(db, registro_id, body, usuario_id):
    prevista = iso_date(_objeto(body).get("data_prevista"), "Data prevista")
    antes = dict(_parcela(db, registro_id))
    if antes["data_recebimento"] is not None:
        raise Conflict("Estorne o recebimento antes de alterar a previsão desta parcela.")
    if prevista != antes["data_prevista"]:
        db.execute("UPDATE fin_cartoes_parcelas SET data_prevista=?,atualizado_em=? WHERE id=?",
                   (prevista, datetime.now().isoformat(), registro_id))
        _auditar(db, usuario_id, "ALTERAR_PREVISAO", "cartoes_parcela", registro_id,
                 {"antes": antes["data_prevista"], "depois": prevista})
    return {"ok": True}


def relatorio(db, mes, operadora=""):
    mes_filtro(mes)
    operadora_filtro(operadora)
    where = " WHERE v.operadora_id=?" if operadora else ""
    parametros = (operadora,) if operadora else ()
    todas = [dict(row) for row in db.execute("""SELECT p.id,p.venda_id,v.operadora_id,v.modalidade,v.bandeira,
        v.data_venda,p.parcela,p.total_parcelas,p.bruto_centavos,p.taxa_centavos,p.liquido_centavos,
        p.data_prevista,p.valor_recebido_centavos,p.data_recebimento,p.observacao_recebimento,
        CASE WHEN p.data_recebimento IS NULL THEN 'pendente'
             WHEN p.valor_recebido_centavos=p.liquido_centavos THEN 'recebido' ELSE 'divergente' END AS status,
        CASE WHEN p.data_recebimento IS NULL THEN NULL ELSE p.valor_recebido_centavos-p.liquido_centavos END AS diferenca_centavos
        FROM fin_cartoes_parcelas p JOIN fin_cartoes_vendas v ON v.id=p.venda_id""" + where +
        " ORDER BY p.data_prevista,v.operadora_id,p.venda_id,p.parcela", parametros)]
    parcelas = [p for p in todas if p["data_prevista"][:7] == mes]
    resumo = {"bruto_centavos": sum(p["bruto_centavos"] for p in parcelas),
              "taxas_centavos": sum(p["taxa_centavos"] for p in parcelas),
              "previsto_centavos": sum(p["liquido_centavos"] for p in parcelas),
              "saldo_centavos": sum(p["liquido_centavos"] for p in parcelas if p["status"] == "pendente"),
              "recebido_no_mes_centavos": sum(p["valor_recebido_centavos"] for p in todas
                                              if (p["data_recebimento"] or "")[:7] == mes),
              "diferenca_centavos": sum(p["diferenca_centavos"] or 0 for p in parcelas)}
    por_operadora = []
    for op in OPERADORAS:
        if operadora and op["id"] != operadora:
            continue
        previstas = [p for p in parcelas if p["operadora_id"] == op["id"]]
        por_operadora.append({"operadora_id": op["id"], "nome": op["nome"], "cor": op["cor"],
            "previsto_centavos": sum(p["liquido_centavos"] for p in previstas),
            "saldo_centavos": sum(p["liquido_centavos"] for p in previstas if p["status"] == "pendente"),
            "recebido_no_mes_centavos": sum(p["valor_recebido_centavos"] for p in todas
                if p["operadora_id"] == op["id"] and (p["data_recebimento"] or "")[:7] == mes)})
    agenda = {}

    def mes_agenda(chave):
        return agenda.setdefault(chave, {"mes": chave, "previsto_centavos": 0,
                                        "saldo_centavos": 0, "recebido_no_mes_centavos": 0})

    for parcela in todas:
        previsto = mes_agenda(parcela["data_prevista"][:7])
        previsto["previsto_centavos"] += parcela["liquido_centavos"]
        if parcela["status"] == "pendente":
            previsto["saldo_centavos"] += parcela["liquido_centavos"]
        else:
            mes_agenda(parcela["data_recebimento"][:7])["recebido_no_mes_centavos"] += parcela["valor_recebido_centavos"]
    pendentes = db.execute("""SELECT COUNT(*) AS quantidade,COALESCE(SUM(bruto_centavos),0) AS bruto_centavos
        FROM fin_cartoes_vendas WHERE condicao_id IS NULL""" +
        (" AND operadora_id=?" if operadora else ""), parametros).fetchone()
    return {"mes": mes, "resumo": resumo, "por_operadora": por_operadora, "parcelas": parcelas,
            "agenda_mensal": [agenda[chave] for chave in sorted(agenda)],
            "pendentes_configuracao": dict(pendentes)}
