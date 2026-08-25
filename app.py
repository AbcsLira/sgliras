from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
import sqlite3, os, hashlib, secrets, configparser, shutil, glob
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
DB_PATH  = os.path.join(os.path.abspath(os.path.dirname(__file__)), "estoque.db")
CFG_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "config.ini")
BACKUP_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "backups")

# Secret key persistente — salva no config.ini para sobreviver a reinícios
_cfg_tmp = configparser.ConfigParser()
_cfg_tmp.read(CFG_PATH, encoding='utf-8')
_saved_key = _cfg_tmp.get('servidor', 'secret_key', fallback=None)
if not _saved_key:
    _saved_key = secrets.token_hex(32)
    with open(CFG_PATH, 'r', encoding='utf-8') as _f:
        _cfg_raw = _f.read()
    _cfg_raw += '\nsecret_key = ' + _saved_key + '\n'
    with open(CFG_PATH, 'w', encoding='utf-8') as _f:
        _f.write(_cfg_raw)
app.secret_key = _saved_key

def load_config():
    cfg = configparser.ConfigParser()
    cfg.read(CFG_PATH, encoding="utf-8")
    return {
        "host":  cfg.get("servidor","host",  fallback="127.0.0.1"),
        "porta": cfg.getint("servidor","porta", fallback=5000),
        "debug": cfg.getboolean("servidor","debug", fallback=False),
    }

PERFIS = {
    "admin":      {"label":"Administrador","permissoes":["dashboard","produtos","movimentacoes","fichas","usuarios","financeiro"]},
    "estoquista": {"label":"Estoquista",   "permissoes":["dashboard","produtos","movimentacoes"]},
    "caixa":      {"label":"Caixa",        "permissoes":["dashboard","movimentacoes"]},
}

def hash_senha(s): return hashlib.sha256(s.encode()).hexdigest()

# ── Banco ─────────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.commit()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nome      TEXT NOT NULL,
            usuario   TEXT NOT NULL UNIQUE,
            senha     TEXT NOT NULL,
            perfil    TEXT NOT NULL DEFAULT 'caixa',
            ativo     INTEGER NOT NULL DEFAULT 1,
            criado_em TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS categorias (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS produtos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nome            TEXT NOT NULL,
            codigo          TEXT NOT NULL UNIQUE,
            unidade         TEXT NOT NULL DEFAULT 'un',
            categoria_id    INTEGER REFERENCES categorias(id),
            quantidade      REAL NOT NULL DEFAULT 0,
            sub_qtd_por_un  REAL,
            sub_unidade     TEXT,
            unid_por_fardo  REAL,
            unid_fardo_label TEXT DEFAULT 'fd',
            validade        TEXT,
            preco_custo     REAL NOT NULL DEFAULT 0,
            preco_venda     REAL,
            estoque_min     INTEGER NOT NULL DEFAULT 5,
            criado_em       TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS movimentacoes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            produto_id INTEGER NOT NULL REFERENCES produtos(id),
            usuario_id INTEGER REFERENCES usuarios(id),
            tipo       TEXT NOT NULL,
            quantidade REAL NOT NULL,
            observacao TEXT,
            criado_em  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fichas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nome        TEXT NOT NULL,
            categoria   TEXT NOT NULL DEFAULT 'Sanduíche',
            rendimento  INTEGER NOT NULL DEFAULT 1,
            preco_venda REAL,
            observacao  TEXT,
            criado_em   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ficha_ingredientes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ficha_id   INTEGER NOT NULL REFERENCES fichas(id) ON DELETE CASCADE,
            produto_id INTEGER NOT NULL REFERENCES produtos(id),
            quantidade REAL NOT NULL,
            unidade    TEXT NOT NULL DEFAULT 'un'
        );
        CREATE TABLE IF NOT EXISTS custos_fixos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nome        TEXT NOT NULL,
            categoria   TEXT NOT NULL DEFAULT 'Geral',
            valor       REAL NOT NULL DEFAULT 0,
            atualizado_em TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ficha_custos_fixos (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ficha_id      INTEGER NOT NULL REFERENCES fichas(id) ON DELETE CASCADE,
            custo_fixo_id INTEGER NOT NULL REFERENCES custos_fixos(id) ON DELETE CASCADE,
            UNIQUE(ficha_id, custo_fixo_id)
        );
        CREATE TABLE IF NOT EXISTS custos_fixos_globais (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nome        TEXT NOT NULL,
            percentual  REAL NOT NULL DEFAULT 0,
            ativo       INTEGER NOT NULL DEFAULT 1,
            atualizado_em TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ficha_preco_historico (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ficha_id   INTEGER NOT NULL REFERENCES fichas(id) ON DELETE CASCADE,
            preco_anterior REAL,
            preco_novo REAL,
            usuario_id INTEGER REFERENCES usuarios(id),
            criado_em  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS log_auditoria (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id  INTEGER REFERENCES usuarios(id),
            acao        TEXT NOT NULL,
            entidade    TEXT NOT NULL,
            entidade_id INTEGER,
            entidade_nome TEXT,
            detalhes    TEXT,
            criado_em   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fornecedores (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            nome       TEXT NOT NULL,
            contato    TEXT,
            observacao TEXT,
            criado_em  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS produto_fornecedores (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            produto_id    INTEGER NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
            fornecedor_id INTEGER NOT NULL REFERENCES fornecedores(id) ON DELETE CASCADE,
            preco         REAL NOT NULL DEFAULT 0,
            atualizado_em TEXT NOT NULL,
            UNIQUE(produto_id, fornecedor_id)
        );
        CREATE TABLE IF NOT EXISTS fin_fechamento_diario (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            data          TEXT NOT NULL UNIQUE,
            credito       REAL NOT NULL DEFAULT 0,
            debito        REAL NOT NULL DEFAULT 0,
            voucher       REAL NOT NULL DEFAULT 0,
            pix           REAL NOT NULL DEFAULT 0,
            dinheiro      REAL NOT NULL DEFAULT 0,
            delivery_qtd  INTEGER NOT NULL DEFAULT 0,
            delivery_val  REAL NOT NULL DEFAULT 0,
            frete         REAL NOT NULL DEFAULT 0,
            paes_qtd      INTEGER NOT NULL DEFAULT 0,
            janta         REAL NOT NULL DEFAULT 0,
            func_val      REAL NOT NULL DEFAULT 0,
            cortesia      REAL NOT NULL DEFAULT 0,
            observacao    TEXT,
            usuario_id    INTEGER REFERENCES usuarios(id),
            criado_em     TEXT NOT NULL,
            atualizado_em TEXT
        );
        CREATE TABLE IF NOT EXISTS fin_contas_pagar (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao     TEXT NOT NULL,
            valor         REAL NOT NULL,
            vencimento    TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'aberto',
            categoria     TEXT NOT NULL DEFAULT 'Outros',
            fornecedor_id INTEGER REFERENCES fornecedores(id),
            pago_em       TEXT,
            observacao    TEXT,
            usuario_id    INTEGER REFERENCES usuarios(id),
            criado_em     TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fin_contas_receber (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao     TEXT NOT NULL,
            valor         REAL NOT NULL,
            vencimento    TEXT NOT NULL,
            status        TEXT NOT NULL DEFAULT 'aberto',
            categoria     TEXT NOT NULL DEFAULT 'Outros',
            recebido_em   TEXT,
            observacao    TEXT,
            usuario_id    INTEGER REFERENCES usuarios(id),
            criado_em     TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fin_preco_pao (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            preco      REAL NOT NULL,
            vigente_de TEXT NOT NULL UNIQUE,
            usuario_id INTEGER REFERENCES usuarios(id),
            criado_em  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fin_paes_pagamento (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao  TEXT NOT NULL,
            valor      REAL NOT NULL,
            datas      TEXT NOT NULL,
            pago_em    TEXT NOT NULL,
            usuario_id INTEGER REFERENCES usuarios(id),
            criado_em  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fin_massa_precos (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            vigente_de TEXT NOT NULL,
            preco_p    REAL NOT NULL DEFAULT 0,
            preco_m    REAL NOT NULL DEFAULT 0,
            preco_g    REAL NOT NULL DEFAULT 0,
            preco_gg   REAL NOT NULL DEFAULT 0,
            preco_burg REAL NOT NULL DEFAULT 0,
            usuario_id INTEGER REFERENCES usuarios(id),
            criado_em  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fin_massa_entregas (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            data       TEXT NOT NULL,
            qtd_p      INTEGER NOT NULL DEFAULT 0,
            qtd_m      INTEGER NOT NULL DEFAULT 0,
            qtd_g      INTEGER NOT NULL DEFAULT 0,
            qtd_gg     INTEGER NOT NULL DEFAULT 0,
            qtd_burg   INTEGER NOT NULL DEFAULT 0,
            valor_total REAL NOT NULL DEFAULT 0,
            observacao TEXT,
            pago       INTEGER NOT NULL DEFAULT 0,
            usuario_id INTEGER REFERENCES usuarios(id),
            criado_em  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fin_massa_pagamento (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao  TEXT NOT NULL,
            valor      REAL NOT NULL,
            entrega_ids TEXT NOT NULL,
            pago_em    TEXT NOT NULL,
            usuario_id INTEGER REFERENCES usuarios(id),
            criado_em  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fin_metas_mensais (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            mes        TEXT NOT NULL UNIQUE,
            meta_valor REAL NOT NULL,
            usuario_id INTEGER REFERENCES usuarios(id),
            criado_em  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fin_categorias_pagar (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nome      TEXT NOT NULL UNIQUE,
            criado_em TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS inventarios (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo        TEXT NOT NULL DEFAULT 'Inventário',
            status        TEXT NOT NULL DEFAULT 'aberto',
            categoria     TEXT,
            observacao    TEXT,
            usuario_id    INTEGER REFERENCES usuarios(id),
            finalizado_em TEXT,
            criado_em     TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS inventario_itens (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            inventario_id       INTEGER NOT NULL REFERENCES inventarios(id) ON DELETE CASCADE,
            produto_id          INTEGER NOT NULL REFERENCES produtos(id),
            quantidade_sistema  REAL NOT NULL,
            quantidade_contada  REAL,
            diferenca           REAL,
            observacao          TEXT
        );
        INSERT OR IGNORE INTO categorias (nome) VALUES
            ('Alimentos'),('Bebidas'),('Limpeza'),('Embalagens'),('Outros'),('Molhos'),('Oficina'),('Gelatos');
    """)
    # Remove categoria duplicada 'Oficinas' se existir
    try:
        c.execute("DELETE FROM categorias WHERE nome='Oficinas'")
        conn.commit()
    except: pass
    # Migrações seguras para bancos existentes
    for sql in [
        "ALTER TABLE produtos ADD COLUMN unidade TEXT NOT NULL DEFAULT 'un'",
        "ALTER TABLE produtos ADD COLUMN sub_qtd_por_un REAL",
        "ALTER TABLE produtos ADD COLUMN sub_unidade TEXT",
        "ALTER TABLE movimentacoes ADD COLUMN usuario_id INTEGER REFERENCES usuarios(id)",
        "ALTER TABLE produtos ADD COLUMN unid_por_fardo REAL",
        "ALTER TABLE produtos ADD COLUMN unid_fardo_label TEXT DEFAULT 'fd'",
        "ALTER TABLE produtos ADD COLUMN validade TEXT",
        "ALTER TABLE fin_fechamento_diario ADD COLUMN preco_pao REAL NOT NULL DEFAULT 0",
        "ALTER TABLE produtos ADD COLUMN preco_embalagem REAL",
        "ALTER TABLE produtos ADD COLUMN tipo_embalagem TEXT",
        "ALTER TABLE produtos ADD COLUMN unid_embalagem INTEGER",
        "ALTER TABLE fin_massa_entregas ADD COLUMN conta_pagar_id INTEGER REFERENCES fin_contas_pagar(id)",
        "ALTER TABLE fin_paes_pagamento ADD COLUMN conta_pagar_id INTEGER REFERENCES fin_contas_pagar(id)",
    ]:
        try: c.execute(sql); conn.commit()
        except: pass
    admin = c.execute("SELECT id FROM usuarios WHERE usuario='admin'").fetchone()
    if not admin:
        c.execute("INSERT INTO usuarios (nome,usuario,senha,perfil,ativo,criado_em) VALUES (?,?,?,?,?,?)",
                  ("Administrador","admin",hash_senha("admin123"),"admin",1,datetime.now().isoformat()))
    # Popular categorias padrão de contas a pagar se ainda não existirem
    if not c.execute("SELECT id FROM fin_categorias_pagar LIMIT 1").fetchone():
        cats_padrao = ["Fornecedor","Água/Luz/Gás","Salário","Manutenção","Impostos","Outros"]
        for cat in cats_padrao:
            c.execute("INSERT OR IGNORE INTO fin_categorias_pagar (nome,criado_em) VALUES (?,?)",
                      (cat, datetime.now().isoformat()))
    conn.commit(); conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


# ── Log de Auditoria ─────────────────────────────────────────────────────────
def registrar_auditoria(db, acao, entidade, entidade_id=None, entidade_nome=None, detalhes=None):
    """Registra uma ação administrativa no log de auditoria.
    Usa a mesma conexão db já aberta na rota, sem abrir/fechar conexão própria,
    para que o registro entre na mesma transação da ação principal."""
    db.execute(
        "INSERT INTO log_auditoria (usuario_id,acao,entidade,entidade_id,entidade_nome,detalhes,criado_em) VALUES (?,?,?,?,?,?,?)",
        (session.get("usuario_id"), acao, entidade, entidade_id, entidade_nome, detalhes, datetime.now().isoformat())
    )

def fmt_rs_log(v):
    return "—" if v in (None,0) else f"R${float(v):.2f}"


# ── Backup automático ──────────────────────────────────────────────────────────
def fazer_backup(motivo="automatico"):
    """Cria uma cópia do banco de dados na pasta backups/.
    Mantém os últimos 30 arquivos, removendo os mais antigos."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    nome_backup = f"estoque_{timestamp}_{motivo}.db"
    destino = os.path.join(BACKUP_DIR, nome_backup)
    try:
        shutil.copy2(DB_PATH, destino)
    except Exception as e:
        print(f"⚠️  Falha ao criar backup: {e}")
        return None

    # Limpeza: mantém só os 30 backups mais recentes
    arquivos = sorted(glob.glob(os.path.join(BACKUP_DIR, "estoque_*.db")), key=os.path.getmtime)
    while len(arquivos) > 30:
        mais_antigo = arquivos.pop(0)
        try:
            os.remove(mais_antigo)
        except Exception:
            pass

    return nome_backup


def backup_diario_necessario():
    """Verifica se já existe um backup automático feito hoje."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    hoje = datetime.now().strftime("%Y-%m-%d")
    for arq in glob.glob(os.path.join(BACKUP_DIR, f"estoque_{hoje}_*_automatico.db")):
        return False  # já existe backup de hoje
    return True


def verificar_integridade_banco():
    """Roda PRAGMA integrity_check no banco. Retorna (ok, mensagem)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        resultado = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        if resultado and resultado[0] == "ok":
            return True, "ok"
        return False, str(resultado[0] if resultado else "resultado vazio")
    except Exception as e:
        return False, str(e)

# ── Decorators ────────────────────────────────────────────────────────────────
def login_requerido(f):
    @wraps(f)
    def dec(*a,**kw):
        if "usuario_id" not in session:
            if request.path.startswith("/api/"): return jsonify({"erro":"Não autenticado"}),401
            return redirect(url_for("login_page"))
        return f(*a,**kw)
    return dec

def permissao_requerida(perm):
    def decorator(f):
        @wraps(f)
        def dec(*a,**kw):
            if perm not in PERFIS.get(session.get("perfil",""),{}).get("permissoes",[]):
                return jsonify({"erro":"Sem permissão"}),403
            return f(*a,**kw)
        return dec
    return decorator

# ── Auth ──────────────────────────────────────────────────────────────────────
@app.route("/login")
def login_page():
    if "usuario_id" in session: return redirect("/")
    return render_template("login.html")

@app.route("/")
@login_requerido
def index(): return render_template("index.html")

@app.route("/api/auth/login", methods=["POST"])
def api_login():
    d=request.json; db=get_db()
    u=db.execute("SELECT * FROM usuarios WHERE usuario=? AND ativo=1",(d.get("usuario",""),)).fetchone()
    db.close()
    if not u or u["senha"]!=hash_senha(d.get("senha","")): return jsonify({"erro":"Usuário ou senha inválidos"}),401
    session.update({"usuario_id":u["id"],"usuario":u["usuario"],"nome":u["nome"],"perfil":u["perfil"]})
    perms=PERFIS.get(u["perfil"],{}).get("permissoes",[])
    return jsonify({"ok":True,"nome":u["nome"],"perfil":u["perfil"],"perfil_label":PERFIS[u["perfil"]]["label"],"permissoes":perms})

@app.route("/api/auth/logout",methods=["POST"])
def api_logout(): session.clear(); return jsonify({"ok":True})

@app.route("/api/auth/me")
@login_requerido
def api_me():
    pf=session.get("perfil",""); perms=PERFIS.get(pf,{}).get("permissoes",[])
    return jsonify({"id":session["usuario_id"],"nome":session["nome"],"usuario":session["usuario"],"perfil":pf,
                    "perfil_label":PERFIS[pf]["label"],"permissoes":perms})

@app.route("/api/auth/senha",methods=["PUT"])
@login_requerido
def alterar_senha():
    d=request.json; db=get_db()
    u=db.execute("SELECT senha FROM usuarios WHERE id=?",(session["usuario_id"],)).fetchone()
    if u["senha"]!=hash_senha(d.get("senha_atual","")): db.close(); return jsonify({"erro":"Senha atual incorreta"}),400
    db.execute("UPDATE usuarios SET senha=? WHERE id=?",(hash_senha(d["senha_nova"]),session["usuario_id"]))
    db.commit(); db.close(); return jsonify({"ok":True})

# ── Usuários ──────────────────────────────────────────────────────────────────
@app.route("/api/usuarios")
@login_requerido
@permissao_requerida("usuarios")
def listar_usuarios():
    db=get_db(); rows=db.execute("SELECT id,nome,usuario,perfil,ativo,criado_em FROM usuarios ORDER BY nome").fetchall(); db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/usuarios",methods=["POST"])
@login_requerido
@permissao_requerida("usuarios")
def criar_usuario():
    d=request.json; db=get_db()
    try:
        db.execute("INSERT INTO usuarios (nome,usuario,senha,perfil,ativo,criado_em) VALUES (?,?,?,?,?,?)",
                   (d["nome"],d["usuario"],hash_senha(d["senha"]),d.get("perfil","caixa"),1,datetime.now().isoformat()))
        novo_id=db.execute("SELECT id FROM usuarios WHERE usuario=?",(d["usuario"],)).fetchone()["id"]
        registrar_auditoria(db,"criou","usuario",novo_id,d["nome"],f"login: {d['usuario']}; perfil: {d.get('perfil','caixa')}")
        db.commit(); return jsonify({"ok":True}),201
    except sqlite3.IntegrityError: return jsonify({"erro":"Nome de usuário já existe"}),400
    finally: db.close()

@app.route("/api/usuarios/<int:uid>",methods=["PUT"])
@login_requerido
@permissao_requerida("usuarios")
def atualizar_usuario(uid):
    d=request.json; db=get_db()
    anterior=db.execute("SELECT nome,usuario,perfil,ativo FROM usuarios WHERE id=?",(uid,)).fetchone()
    if d.get("senha"):
        db.execute("UPDATE usuarios SET nome=?,usuario=?,perfil=?,ativo=?,senha=? WHERE id=?",
                   (d["nome"],d["usuario"],d["perfil"],d.get("ativo",1),hash_senha(d["senha"]),uid))
    else:
        db.execute("UPDATE usuarios SET nome=?,usuario=?,perfil=?,ativo=? WHERE id=?",
                   (d["nome"],d["usuario"],d["perfil"],d.get("ativo",1),uid))
    if anterior:
        mudancas=[]
        if anterior["nome"]!=d["nome"]:
            mudancas.append(f"nome: {anterior['nome']} → {d['nome']}")
        if anterior["usuario"]!=d["usuario"]:
            mudancas.append(f"login: {anterior['usuario']} → {d['usuario']}")
        if anterior["perfil"]!=d["perfil"]:
            mudancas.append(f"perfil: {anterior['perfil']} → {d['perfil']}")
        if anterior["ativo"]!=d.get("ativo",1):
            mudancas.append(f"ativo: {'sim' if anterior['ativo'] else 'não'} → {'sim' if d.get('ativo',1) else 'não'}")
        if d.get("senha"):
            mudancas.append("senha alterada")
        if mudancas:
            registrar_auditoria(db,"editou","usuario",uid,d["nome"],"; ".join(mudancas))
    db.commit(); db.close(); return jsonify({"ok":True})

@app.route("/api/usuarios/<int:uid>",methods=["DELETE"])
@login_requerido
@permissao_requerida("usuarios")
def deletar_usuario(uid):
    if uid==session["usuario_id"]: return jsonify({"erro":"Não pode excluir seu próprio usuário"}),400
    db=get_db()
    try:
        usuario=db.execute("SELECT nome FROM usuarios WHERE id=?",(uid,)).fetchone()
        db.execute("DELETE FROM usuarios WHERE id=?",(uid,))
        if usuario:
            registrar_auditoria(db,"excluiu","usuario",uid,usuario["nome"])
        db.commit()
        return jsonify({"ok":True})
    except Exception as e:
        db.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        db.close()

# ── Categorias ────────────────────────────────────────────────────────────────
@app.route("/api/categorias")
@login_requerido
def listar_categorias():
    db=get_db()
    cats=db.execute("SELECT * FROM categorias ORDER BY nome").fetchall()
    db.close(); return jsonify([dict(c) for c in cats])

# ── Produtos ──────────────────────────────────────────────────────────────────
@app.route("/api/produtos")
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

@app.route("/api/produtos",methods=["POST"])
@login_requerido
@permissao_requerida("produtos")
def criar_produto():
    d=request.json; db=get_db()
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
        cur = db.execute("""INSERT INTO produtos
            (nome,codigo,unidade,categoria_id,quantidade,
             sub_qtd_por_un,sub_unidade,unid_por_fardo,unid_fardo_label,validade,
             preco_custo,preco_venda,estoque_min,preco_embalagem,tipo_embalagem,unid_embalagem,criado_em)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d["nome"],d["codigo"],d.get("unidade","un"),d.get("categoria_id"),
             d.get("quantidade",0),sq,su,upf,ufl,val,d.get("preco_custo",0),pv,d.get("estoque_min",5),
             pe,te,ue,datetime.now().isoformat()))
        db.commit(); return jsonify({"ok":True,"id":cur.lastrowid}),201
    except sqlite3.IntegrityError as e: return jsonify({"erro":str(e)}),400
    finally: db.close()

@app.route("/api/produtos/<int:pid>",methods=["PUT"])
@login_requerido
@permissao_requerida("produtos")
def atualizar_produto(pid):
    d=request.json; db=get_db()
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
    db.execute("""UPDATE produtos SET nome=?,codigo=?,unidade=?,categoria_id=?,
                  sub_qtd_por_un=?,sub_unidade=?,unid_por_fardo=?,unid_fardo_label=?,validade=?,
                  preco_custo=?,preco_venda=?,estoque_min=?,
                  preco_embalagem=?,tipo_embalagem=?,unid_embalagem=? WHERE id=?""",
               (d["nome"],d["codigo"],d.get("unidade","un"),d.get("categoria_id"),
                sq,su,upf,ufl,val,d.get("preco_custo",0),pv,d.get("estoque_min",5),
                pe,te,ue,pid))
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

@app.route("/api/produtos/<int:pid>",methods=["DELETE"])
@login_requerido
@permissao_requerida("produtos")
def deletar_produto(pid):
    db=get_db()
    try:
        produto=db.execute("SELECT nome FROM produtos WHERE id=?",(pid,)).fetchone()
        # Remove movimentações e ingredientes de ficha vinculados antes de excluir o produto
        db.execute("DELETE FROM movimentacoes WHERE produto_id=?",(pid,))
        db.execute("DELETE FROM ficha_ingredientes WHERE produto_id=?",(pid,))
        db.execute("DELETE FROM produtos WHERE id=?",(pid,))
        if produto:
            registrar_auditoria(db,"excluiu","produto",pid,produto["nome"])
        db.commit()
        return jsonify({"ok":True})
    except Exception as e:
        db.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        db.close()

# ── Movimentações ─────────────────────────────────────────────────────────────
@app.route("/api/movimentacoes")
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

@app.route("/api/movimentacoes",methods=["POST"])
@login_requerido
def registrar_movimentacao():
    d=request.json
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
        nova=p["quantidade"]
        if   tipo=="entrada": nova+=qtd
        elif tipo=="saida":
            if nova<qtd: return jsonify({"erro":"Estoque insuficiente"}),400
            nova-=qtd
        elif tipo=="ajuste": nova=qtd
        db.execute("UPDATE produtos SET quantidade=? WHERE id=?",(nova,pid))

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

# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route("/api/dashboard")
@login_requerido
def dashboard():
    db=get_db()
    eh_admin = session.get("perfil") == "admin"
    tot=db.execute("SELECT COUNT(*) FROM produtos").fetchone()[0]
    cri=db.execute("SELECT COUNT(*) FROM produtos WHERE quantidade<=estoque_min").fetchone()[0]
    zer=db.execute("SELECT COUNT(*) FROM produtos WHERE quantidade=0").fetchone()[0]
    valor_total = None
    if eh_admin:
        valor_total = db.execute(
            "SELECT COALESCE(SUM(quantidade * preco_custo), 0) FROM produtos"
        ).fetchone()[0]
        valor_total = round(valor_total, 2)
    rows=db.execute("""
        SELECT p.nome,p.codigo,p.quantidade,p.estoque_min,p.unidade,
               p.sub_qtd_por_un,p.sub_unidade,
               COALESCE(c.nome,'Sem categoria') AS categoria
        FROM produtos p LEFT JOIN categorias c ON c.id=p.categoria_id
        WHERE p.quantidade<=p.estoque_min ORDER BY categoria,p.quantidade""").fetchall()
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
        WHERE p.validade IS NOT NULL AND p.validade != ''
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
@app.route("/api/listagem-pdf")
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
        WHERE 1=1
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

# ── Fichas ────────────────────────────────────────────────────────────────────
@app.route("/api/fichas")
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

@app.route("/api/fichas",methods=["POST"])
@login_requerido
@permissao_requerida("fichas")
def criar_ficha():
    d=request.json; db=get_db()
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

@app.route("/api/fichas/<int:fid>",methods=["PUT"])
@login_requerido
@permissao_requerida("fichas")
def atualizar_ficha(fid):
    d=request.json; db=get_db()
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

@app.route("/api/fichas/<int:fid>",methods=["DELETE"])
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


@app.route("/api/fichas/<int:fid>/historico-preco")
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
@app.route("/api/custos-fixos")
@login_requerido
@permissao_requerida("fichas")
def listar_custos_fixos():
    db=get_db()
    rows=db.execute("SELECT * FROM custos_fixos ORDER BY categoria, nome").fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/custos-fixos",methods=["POST"])
@login_requerido
@permissao_requerida("fichas")
def criar_custo_fixo():
    d=request.json; db=get_db()
    try:
        cur=db.execute("INSERT INTO custos_fixos (nome,categoria,valor,atualizado_em) VALUES (?,?,?,?)",
                        (d["nome"], d.get("categoria","Geral"), float(d.get("valor",0)), datetime.now().isoformat()))
        db.commit()
        return jsonify({"ok":True,"id":cur.lastrowid}),201
    finally:
        db.close()


@app.route("/api/custos-fixos/<int:cid>",methods=["PUT"])
@login_requerido
@permissao_requerida("fichas")
def atualizar_custo_fixo(cid):
    d=request.json; db=get_db()
    db.execute("UPDATE custos_fixos SET nome=?,categoria=?,valor=?,atualizado_em=? WHERE id=?",
               (d["nome"], d.get("categoria","Geral"), float(d.get("valor",0)), datetime.now().isoformat(), cid))
    db.commit(); db.close()
    return jsonify({"ok":True})


@app.route("/api/custos-fixos/<int:cid>",methods=["DELETE"])
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
@app.route("/api/fichas/<int:fid>/custos-fixos",methods=["POST"])
@login_requerido
@permissao_requerida("fichas")
def vincular_custo_fixo(fid):
    d=request.json; db=get_db()
    try:
        db.execute("INSERT OR IGNORE INTO ficha_custos_fixos (ficha_id,custo_fixo_id) VALUES (?,?)",
                   (fid, d["custo_fixo_id"]))
        db.commit()
        return jsonify({"ok":True}),201
    finally:
        db.close()


@app.route("/api/fichas/<int:fid>/custos-fixos/<int:cid>",methods=["DELETE"])
@login_requerido
@permissao_requerida("fichas")
def desvincular_custo_fixo(fid,cid):
    db=get_db()
    db.execute("DELETE FROM ficha_custos_fixos WHERE ficha_id=? AND custo_fixo_id=?",(fid,cid))
    db.commit(); db.close()
    return jsonify({"ok":True})


# ── Custos Fixos Globais (%) — aplicados automaticamente sobre o preço de venda em TODAS as fichas ──
@app.route("/api/custos-fixos-globais")
@login_requerido
@permissao_requerida("fichas")
def listar_custos_fixos_globais():
    db=get_db()
    rows=db.execute("SELECT * FROM custos_fixos_globais ORDER BY nome").fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/custos-fixos-globais",methods=["POST"])
@login_requerido
@permissao_requerida("fichas")
def criar_custo_fixo_global():
    d=request.json; db=get_db()
    try:
        cur=db.execute("INSERT INTO custos_fixos_globais (nome,percentual,ativo,atualizado_em) VALUES (?,?,?,?)",
                        (d["nome"], float(d.get("percentual",0)), 1 if d.get("ativo",True) else 0, datetime.now().isoformat()))
        db.commit()
        return jsonify({"ok":True,"id":cur.lastrowid}),201
    finally:
        db.close()


@app.route("/api/custos-fixos-globais/<int:gid>",methods=["PUT"])
@login_requerido
@permissao_requerida("fichas")
def atualizar_custo_fixo_global(gid):
    d=request.json; db=get_db()
    db.execute("UPDATE custos_fixos_globais SET nome=?,percentual=?,ativo=?,atualizado_em=? WHERE id=?",
               (d["nome"], float(d.get("percentual",0)), 1 if d.get("ativo",True) else 0, datetime.now().isoformat(), gid))
    db.commit(); db.close()
    return jsonify({"ok":True})


@app.route("/api/custos-fixos-globais/<int:gid>",methods=["DELETE"])
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


# ── Backups (somente admin) ──────────────────────────────────────────────────
@app.route("/api/backups")
@login_requerido
@permissao_requerida("usuarios")
def listar_backups():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    arquivos = sorted(glob.glob(os.path.join(BACKUP_DIR, "estoque_*.db")), key=os.path.getmtime, reverse=True)
    res = []
    for a in arquivos:
        nome = os.path.basename(a)
        tamanho_kb = round(os.path.getsize(a) / 1024, 1)
        modificado = datetime.fromtimestamp(os.path.getmtime(a)).strftime("%d/%m/%Y %H:%M:%S")
        res.append({"nome": nome, "tamanho_kb": tamanho_kb, "criado_em": modificado})
    return jsonify(res)


@app.route("/api/backups", methods=["POST"])
@login_requerido
@permissao_requerida("usuarios")
def criar_backup_manual():
    nome = fazer_backup(motivo="manual")
    if not nome:
        return jsonify({"erro": "Falha ao criar backup"}), 500
    return jsonify({"ok": True, "nome": nome}), 201


@app.route("/api/backups/<nome>")
@login_requerido
@permissao_requerida("usuarios")
def baixar_backup(nome):
    # Proteção contra path traversal
    nome_seguro = os.path.basename(nome)
    caminho = os.path.join(BACKUP_DIR, nome_seguro)
    if not os.path.isfile(caminho) or not nome_seguro.startswith("estoque_"):
        return jsonify({"erro": "Backup não encontrado"}), 404
    return send_file(caminho, as_attachment=True, download_name=nome_seguro)


@app.route("/api/status-backup")
@login_requerido
def status_backup():
    """Retorna status atual dos backups e integridade do banco."""
    if session.get("perfil") != "admin":
        return jsonify({"erro": "Apenas administradores"}), 403
    banco_ok, banco_msg = verificar_integridade_banco()
    arquivos_backup = sorted(
        glob.glob(os.path.join(BACKUP_DIR, "estoque_*.db")),
        key=os.path.getmtime, reverse=True
    )
    ultimo_backup = None
    if arquivos_backup:
        mtime = os.path.getmtime(arquivos_backup[0])
        ultimo_backup = datetime.fromtimestamp(mtime).isoformat()
    tamanho_banco = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    return jsonify({
        "banco_ok": banco_ok,
        "banco_msg": banco_msg,
        "tamanho_banco_kb": round(tamanho_banco / 1024, 1),
        "total_backups_internos": len(arquivos_backup),
        "ultimo_backup": ultimo_backup,
        "backup_hoje": not backup_diario_necessario(),
    })


# ── Fornecedores ──────────────────────────────────────────────────────────────
@app.route("/api/fornecedores")
@login_requerido
def listar_fornecedores():
    db = get_db()
    rows = db.execute("SELECT * FROM fornecedores ORDER BY nome").fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/fornecedores", methods=["POST"])
@login_requerido
@permissao_requerida("produtos")
def criar_fornecedor():
    d = request.json
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


@app.route("/api/fornecedores/<int:fid>", methods=["PUT"])
@login_requerido
@permissao_requerida("produtos")
def atualizar_fornecedor(fid):
    d = request.json
    db = get_db()
    db.execute(
        "UPDATE fornecedores SET nome=?, contato=?, observacao=? WHERE id=?",
        (d["nome"], d.get("contato", ""), d.get("observacao", ""), fid)
    )
    db.commit(); db.close()
    return jsonify({"ok": True})


@app.route("/api/fornecedores/<int:fid>", methods=["DELETE"])
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


@app.route("/api/fornecedores/<int:fid>/produtos")
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
@app.route("/api/produtos/<int:pid>/fornecedores")
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


@app.route("/api/produtos/<int:pid>/fornecedores", methods=["POST"])
@login_requerido
@permissao_requerida("produtos")
def vincular_fornecedor(pid):
    d = request.json
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


@app.route("/api/produtos/<int:pid>/fornecedores/<int:vid>", methods=["DELETE"])
@login_requerido
@permissao_requerida("produtos")
def desvincular_fornecedor(pid, vid):
    db = get_db()
    db.execute("DELETE FROM produto_fornecedores WHERE id=? AND produto_id=?", (vid, pid))
    db.commit(); db.close()
    return jsonify({"ok": True})


# ── Lista de Compras ─────────────────────────────────────────────────────────
@app.route("/api/lista-compras/sugestao")
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
        WHERE p.quantidade <= p.estoque_min
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


# ── Contagem de Inventário ──────────────────────────────────────────────────────
@app.route("/api/inventario/produtos")
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
        WHERE 1=1
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
@app.route("/api/inventarios", methods=["GET"])
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


@app.route("/api/inventarios", methods=["POST"])
@login_requerido
@permissao_requerida("produtos")
def criar_inventario():
    d = request.json
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
    """
    params = []
    if categoria:
        query += " WHERE LOWER(c.nome) = LOWER(?)"
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


@app.route("/api/inventarios/<int:inv_id>", methods=["GET"])
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
        ORDER BY categoria, p.nome
    """, ).fetchall()
    # Filtrar apenas itens deste inventário
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


@app.route("/api/inventarios/<int:inv_id>/itens", methods=["PUT"])
@login_requerido
@permissao_requerida("produtos")
def salvar_itens_inventario(inv_id):
    """Salva contagens parciais sem finalizar."""
    d = request.json
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


@app.route("/api/inventarios/<int:inv_id>/finalizar", methods=["POST"])
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


@app.route("/api/inventarios/<int:inv_id>", methods=["DELETE"])
@login_requerido
@permissao_requerida("produtos")
def cancelar_inventario(inv_id):
    db = get_db()
    db.execute("DELETE FROM inventarios WHERE id=? AND status='aberto'", (inv_id,))
    db.commit(); db.close()
    return jsonify({"ok": True})


@app.route("/api/inventario/aplicar", methods=["POST"])
@login_requerido
@permissao_requerida("produtos")
def aplicar_contagem_inventario():
    """Mantido para compatibilidade com a contagem rápida existente."""
    d = request.json
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


# ── Relatório de Consumo por Período ────────────────────────────────────────────
@app.route("/api/relatorios/consumo")
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


@app.route("/api/log-auditoria")
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


@app.route("/api/perfis")
@login_requerido
def listar_perfis():
    return jsonify([{"id":k,"label":v["label"],"permissoes":v["permissoes"]} for k,v in PERFIS.items()])


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO FINANCEIRO
# ══════════════════════════════════════════════════════════════════════════════

def somente_admin():
    """Retorna erro 403 se o usuário não for admin, ou None se ok."""
    if session.get("perfil") != "admin":
        return jsonify({"erro": "Apenas o administrador pode acessar o módulo financeiro"}), 403
    return None

# ── Fechamento Diário ─────────────────────────────────────────────────────────
@app.route("/api/fin/fechamento", methods=["GET"])
@login_requerido
def listar_fechamentos():
    err = somente_admin()
    if err: return err
    db = get_db()
    mes = request.args.get("mes")  # formato YYYY-MM
    if mes:
        rows = db.execute(
            "SELECT * FROM fin_fechamento_diario WHERE data LIKE ? ORDER BY data DESC",
            (f"{mes}%",)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM fin_fechamento_diario ORDER BY data DESC LIMIT 60"
        ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/fin/fechamento/<string:data>", methods=["GET"])
@login_requerido
def obter_fechamento(data):
    err = somente_admin()
    if err: return err
    db = get_db()
    row = db.execute("SELECT * FROM fin_fechamento_diario WHERE data=?", (data,)).fetchone()
    db.close()
    return jsonify(dict(row) if row else {})

@app.route("/api/fin/fechamento", methods=["POST"])
@login_requerido
def salvar_fechamento():
    err = somente_admin()
    if err: return err
    d = request.json
    data = d.get("data")
    if not data:
        return jsonify({"erro": "Data é obrigatória"}), 400
    db = get_db()
    existente = db.execute("SELECT id FROM fin_fechamento_diario WHERE data=?", (data,)).fetchone()
    agora = datetime.now().isoformat()
    campos = ("credito","debito","voucher","pix","dinheiro",
              "delivery_qtd","delivery_val","frete","paes_qtd",
              "janta","func_val","cortesia","observacao")
    valores = [d.get(c, 0) for c in campos]
    if existente:
        sets = ", ".join(f"{c}=?" for c in campos) + ", atualizado_em=?, usuario_id=?"
        db.execute(f"UPDATE fin_fechamento_diario SET {sets} WHERE data=?",
                   valores + [agora, session.get("usuario_id"), data])
    else:
        cols = "data," + ",".join(campos) + ",usuario_id,criado_em"
        phs  = "?," + ",".join("?" for _ in campos) + ",?,?"
        db.execute(f"INSERT INTO fin_fechamento_diario ({cols}) VALUES ({phs})",
                   [data] + valores + [session.get("usuario_id"), agora])
    db.commit(); db.close()
    return jsonify({"ok": True})

@app.route("/api/fin/fechamento/<string:data>", methods=["DELETE"])
@login_requerido
def deletar_fechamento(data):
    err = somente_admin()
    if err: return err
    db = get_db()
    db.execute("DELETE FROM fin_fechamento_diario WHERE data=?", (data,))
    db.commit(); db.close()
    return jsonify({"ok": True})

@app.route("/api/fin/resumo-mes", methods=["GET"])
@login_requerido
def resumo_mes():
    err = somente_admin()
    if err: return err
    mes = request.args.get("mes", datetime.now().strftime("%Y-%m"))
    db = get_db()
    rows = db.execute(
        "SELECT * FROM fin_fechamento_diario WHERE data LIKE ? ORDER BY data ASC",
        (f"{mes}%",)
    ).fetchall()
    # Buscar todos os preços de pão ordenados (para calcular vigente de cada dia)
    precos_pao = db.execute(
        "SELECT preco, vigente_de FROM fin_preco_pao ORDER BY vigente_de DESC"
    ).fetchall()
    db.close()
    if not rows:
        return jsonify({"mes": mes, "dias": 0, "totais": {}, "por_dia": []})

    def preco_pao_no_dia(data):
        for p in precos_pao:
            if p["vigente_de"] <= data:
                return p["preco"]
        return 0

    totais = {
        "credito": 0, "debito": 0, "voucher": 0, "pix": 0, "dinheiro": 0,
        "delivery_val": 0, "frete": 0, "janta": 0, "func_val": 0, "cortesia": 0,
        "paes_qtd": 0, "delivery_qtd": 0, "custo_paes": 0
    }
    por_dia = []
    for r in rows:
        rd = dict(r)
        venda_dia = rd["credito"] + rd["debito"] + rd["voucher"] + rd["pix"] + rd["dinheiro"]
        rd["venda_total"] = venda_dia
        preco_pao = preco_pao_no_dia(rd["data"])
        rd["preco_pao_vigente"] = preco_pao
        rd["custo_paes"] = round((rd.get("paes_qtd") or 0) * preco_pao, 2)
        por_dia.append(rd)
        for k in totais:
            if k == "custo_paes":
                totais[k] += rd["custo_paes"]
            else:
                totais[k] += rd.get(k, 0) or 0
    totais["venda_total"] = (totais["credito"] + totais["debito"] + totais["voucher"]
                             + totais["pix"] + totais["dinheiro"])
    totais["cartao_total"] = totais["credito"] + totais["debito"] + totais["voucher"]
    return jsonify({"mes": mes, "dias": len(rows), "totais": totais, "por_dia": por_dia})

# ── Contas a Pagar ─────────────────────────────────────────────────────────────
@app.route("/api/fin/contas-pagar", methods=["GET"])
@login_requerido
def listar_contas_pagar():
    err = somente_admin()
    if err: return err
    db = get_db()
    status    = request.args.get("status", "")
    categoria = request.args.get("categoria", "")
    mes       = request.args.get("mes", "")
    fornecedor_id = request.args.get("fornecedor_id", "")

    where, params = ["1=1"], []
    if status:
        where.append("cp.status=?"); params.append(status)
    if categoria:
        where.append("cp.categoria=?"); params.append(categoria)
    if mes:
        where.append("(cp.vencimento LIKE ? OR cp.pago_em LIKE ?)"); params += [f"{mes}%", f"{mes}%"]
    if fornecedor_id:
        where.append("cp.fornecedor_id=?"); params.append(int(fornecedor_id))

    rows = db.execute(f"""
        SELECT cp.*, f.nome AS fornecedor_nome
        FROM fin_contas_pagar cp
        LEFT JOIN fornecedores f ON f.id=cp.fornecedor_id
        WHERE {' AND '.join(where)}
        ORDER BY cp.vencimento ASC
    """, params).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/fin/contas-pagar/<int:cid>", methods=["PUT"])
@login_requerido
def editar_conta_pagar(cid):
    err = somente_admin()
    if err: return err
    d = request.json
    if not d.get("descricao") or not d.get("valor") or not d.get("vencimento"):
        return jsonify({"erro": "Descrição, valor e vencimento são obrigatórios"}), 400
    db = get_db()
    db.execute("""UPDATE fin_contas_pagar SET
        descricao=?, valor=?, vencimento=?, categoria=?,
        fornecedor_id=?, observacao=? WHERE id=?""",
        (d["descricao"], float(d["valor"]), d["vencimento"],
         d.get("categoria", "Outros"),
         d.get("fornecedor_id") or None,
         d.get("observacao", ""), cid))
    db.commit(); db.close()
    return jsonify({"ok": True})


@app.route("/api/fin/contas-pagar/resumo-categorias", methods=["GET"])
@login_requerido
def resumo_categorias_pagar():
    """Retorna totais agrupados por categoria para o período/status informado."""
    err = somente_admin()
    if err: return err
    db = get_db()
    mes    = request.args.get("mes", "")
    status = request.args.get("status", "")

    where, params = ["1=1"], []
    if mes:
        where.append("(vencimento LIKE ? OR pago_em LIKE ?)"); params += [f"{mes}%", f"{mes}%"]
    if status:
        where.append("status=?"); params.append(status)

    rows = db.execute(f"""
        SELECT categoria,
               COUNT(*) AS total_contas,
               SUM(valor) AS total_valor,
               SUM(CASE WHEN status='pago' THEN valor ELSE 0 END) AS total_pago,
               SUM(CASE WHEN status='aberto' THEN valor ELSE 0 END) AS total_aberto
        FROM fin_contas_pagar
        WHERE {' AND '.join(where)}
        GROUP BY categoria ORDER BY total_valor DESC
    """, params).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/fin/contas-pagar", methods=["POST"])
@login_requerido
def criar_conta_pagar():
    err = somente_admin()
    if err: return err
    d = request.json
    if not d.get("descricao") or not d.get("valor") or not d.get("vencimento"):
        return jsonify({"erro": "Descrição, valor e vencimento são obrigatórios"}), 400
    db = get_db()
    db.execute(
        """INSERT INTO fin_contas_pagar
           (descricao,valor,vencimento,status,categoria,fornecedor_id,observacao,usuario_id,criado_em)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (d["descricao"], float(d["valor"]), d["vencimento"],
         "aberto", d.get("categoria", "Outros"),
         d.get("fornecedor_id") or None, d.get("observacao", ""),
         session.get("usuario_id"), datetime.now().isoformat())
    )
    db.commit(); db.close()
    return jsonify({"ok": True}), 201

@app.route("/api/fin/contas-pagar/<int:cid>/pagar", methods=["POST"])
@login_requerido
def pagar_conta(cid):
    err = somente_admin()
    if err: return err
    db = get_db()
    conta = db.execute("SELECT * FROM fin_contas_pagar WHERE id=?", (cid,)).fetchone()
    if not conta:
        db.close(); return jsonify({"erro": "Conta não encontrada"}), 404
    agora = datetime.now().isoformat()
    db.execute("UPDATE fin_contas_pagar SET status='pago', pago_em=? WHERE id=?", (agora, cid))
    db.commit(); db.close()
    return jsonify({"ok": True})

@app.route("/api/fin/contas-pagar/<int:cid>", methods=["DELETE"])
@login_requerido
def deletar_conta_pagar(cid):
    err = somente_admin()
    if err: return err
    db = get_db()
    db.execute("DELETE FROM fin_contas_pagar WHERE id=?", (cid,))
    db.commit(); db.close()
    return jsonify({"ok": True})

# ── Contas a Receber ──────────────────────────────────────────────────────────
@app.route("/api/fin/contas-receber", methods=["GET"])
@login_requerido
def listar_contas_receber():
    err = somente_admin()
    if err: return err
    db = get_db()
    status = request.args.get("status", "")
    if status:
        rows = db.execute(
            "SELECT * FROM fin_contas_receber WHERE status=? ORDER BY vencimento ASC", (status,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM fin_contas_receber ORDER BY vencimento ASC"
        ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/fin/contas-receber", methods=["POST"])
@login_requerido
def criar_conta_receber():
    err = somente_admin()
    if err: return err
    d = request.json
    if not d.get("descricao") or not d.get("valor") or not d.get("vencimento"):
        return jsonify({"erro": "Descrição, valor e vencimento são obrigatórios"}), 400
    db = get_db()
    db.execute(
        """INSERT INTO fin_contas_receber
           (descricao,valor,vencimento,status,categoria,observacao,usuario_id,criado_em)
           VALUES (?,?,?,?,?,?,?,?)""",
        (d["descricao"], float(d["valor"]), d["vencimento"],
         "aberto", d.get("categoria", "Outros"),
         d.get("observacao", ""), session.get("usuario_id"), datetime.now().isoformat())
    )
    db.commit(); db.close()
    return jsonify({"ok": True}), 201

@app.route("/api/fin/contas-receber/<int:cid>/receber", methods=["POST"])
@login_requerido
def receber_conta(cid):
    err = somente_admin()
    if err: return err
    db = get_db()
    conta = db.execute("SELECT * FROM fin_contas_receber WHERE id=?", (cid,)).fetchone()
    if not conta:
        db.close(); return jsonify({"erro": "Conta não encontrada"}), 404
    agora = datetime.now().isoformat()
    db.execute("UPDATE fin_contas_receber SET status='recebido', recebido_em=? WHERE id=?", (agora, cid))
    db.commit(); db.close()
    return jsonify({"ok": True})

@app.route("/api/fin/contas-receber/<int:cid>", methods=["DELETE"])
@login_requerido
def deletar_conta_receber(cid):
    err = somente_admin()
    if err: return err
    db = get_db()
    db.execute("DELETE FROM fin_contas_receber WHERE id=?", (cid,))
    db.commit(); db.close()
    return jsonify({"ok": True})

# ── Categorias financeiras ────────────────────────────────────────────────────
CATS_RECEBER = ["Venda","Serviço","Reembolso","Outros"]

@app.route("/api/fin/categorias-pagar")
@login_requerido
def categorias_pagar():
    db = get_db()
    rows = db.execute("SELECT id, nome FROM fin_categorias_pagar ORDER BY nome").fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/fin/categorias-pagar", methods=["POST"])
@login_requerido
def criar_categoria_pagar():
    err = somente_admin()
    if err: return err
    d = request.json
    nome = (d.get("nome") or "").strip()
    if not nome:
        return jsonify({"erro": "Nome obrigatório"}), 400
    db = get_db()
    try:
        db.execute("INSERT INTO fin_categorias_pagar (nome,criado_em) VALUES (?,?)",
                   (nome, datetime.now().isoformat()))
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({"erro": "Categoria já existe"}), 400
    finally:
        db.close()
    return jsonify({"ok": True}), 201

@app.route("/api/fin/categorias-pagar/<int:cid>", methods=["PUT"])
@login_requerido
def renomear_categoria_pagar(cid):
    err = somente_admin()
    if err: return err
    d = request.json
    nome = (d.get("nome") or "").strip()
    if not nome:
        return jsonify({"erro": "Nome obrigatório"}), 400
    db = get_db()
    try:
        # Atualizar o nome nas contas a pagar existentes também
        cat_atual = db.execute("SELECT nome FROM fin_categorias_pagar WHERE id=?", (cid,)).fetchone()
        if cat_atual:
            db.execute("UPDATE fin_contas_pagar SET categoria=? WHERE categoria=?",
                       (nome, cat_atual["nome"]))
        db.execute("UPDATE fin_categorias_pagar SET nome=? WHERE id=?", (nome, cid))
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({"erro": "Categoria já existe com esse nome"}), 400
    finally:
        db.close()
    return jsonify({"ok": True})

@app.route("/api/fin/categorias-pagar/<int:cid>", methods=["DELETE"])
@login_requerido
def excluir_categoria_pagar(cid):
    err = somente_admin()
    if err: return err
    db = get_db()
    cat = db.execute("SELECT nome FROM fin_categorias_pagar WHERE id=?", (cid,)).fetchone()
    if not cat:
        db.close()
        return jsonify({"erro": "Categoria não encontrada"}), 404
    # Verificar se há contas vinculadas
    vinculadas = db.execute(
        "SELECT COUNT(*) AS total FROM fin_contas_pagar WHERE categoria=?",
        (cat["nome"],)
    ).fetchone()["total"]
    if vinculadas > 0:
        db.close()
        return jsonify({"erro": f"Não é possível excluir: {vinculadas} conta(s) vinculada(s) a esta categoria. Reatribua-as primeiro."}), 400
    db.execute("DELETE FROM fin_categorias_pagar WHERE id=?", (cid,))
    db.commit(); db.close()
    return jsonify({"ok": True})

@app.route("/api/fin/categorias-receber")
@login_requerido
def categorias_receber():
    return jsonify(CATS_RECEBER)

@app.route("/api/fin/preco-pao", methods=["GET"])
@login_requerido
def listar_precos_pao():
    err = somente_admin()
    if err: return err
    db = get_db()
    rows = db.execute(
        "SELECT * FROM fin_preco_pao ORDER BY vigente_de DESC"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/fin/preco-pao", methods=["POST"])
@login_requerido
def salvar_preco_pao():
    err = somente_admin()
    if err: return err
    d = request.json
    if not d.get("preco") or not d.get("vigente_de"):
        return jsonify({"erro": "Preço e data de vigência são obrigatórios"}), 400
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO fin_preco_pao (preco, vigente_de, usuario_id, criado_em) VALUES (?,?,?,?)",
        (float(d["preco"]), d["vigente_de"], session.get("usuario_id"), datetime.now().isoformat())
    )
    db.commit(); db.close()
    return jsonify({"ok": True}), 201

@app.route("/api/fin/preco-pao/<string:data>", methods=["DELETE"])
@login_requerido
def deletar_preco_pao(data):
    err = somente_admin()
    if err: return err
    db = get_db()
    db.execute("DELETE FROM fin_preco_pao WHERE vigente_de=?", (data,))
    db.commit(); db.close()
    return jsonify({"ok": True})

@app.route("/api/fin/preco-pao-vigente/<string:data>", methods=["GET"])
@login_requerido
def preco_pao_vigente(data):
    """Retorna o preço do pão vigente em uma data específica."""
    err = somente_admin()
    if err: return err
    db = get_db()
    row = db.execute(
        "SELECT * FROM fin_preco_pao WHERE vigente_de <= ? ORDER BY vigente_de DESC LIMIT 1",
        (data,)
    ).fetchone()
    db.close()
    return jsonify(dict(row) if row else {})

@app.route("/api/fin/relatorio-paes", methods=["GET"])
@login_requerido
def relatorio_paes():
    """Retorna os fechamentos com quantidade de pães, já com preço vigente calculado."""
    err = somente_admin()
    if err: return err
    db = get_db()
    mes = request.args.get("mes")
    if mes:
        fechamentos = db.execute(
            "SELECT data, paes_qtd FROM fin_fechamento_diario WHERE data LIKE ? AND paes_qtd > 0 ORDER BY data ASC",
            (f"{mes}%",)
        ).fetchall()
    else:
        fechamentos = db.execute(
            "SELECT data, paes_qtd FROM fin_fechamento_diario WHERE paes_qtd > 0 ORDER BY data DESC LIMIT 60"
        ).fetchall()
    precos = db.execute(
        "SELECT * FROM fin_preco_pao ORDER BY vigente_de DESC"
    ).fetchall()
    pagamentos = db.execute(
        "SELECT id, datas, valor, pago_em FROM fin_paes_pagamento ORDER BY pago_em DESC"
    ).fetchall()
    db.close()

    # Montar conjunto de datas já pagas
    datas_pagas = set()
    for p in pagamentos:
        for dt in (p["datas"] or "").split(","):
            datas_pagas.add(dt.strip())

    def preco_em(data):
        for p in precos:
            if p["vigente_de"] <= data:
                return p["preco"]
        return 0

    resultado = []
    for f in fechamentos:
        preco = preco_em(f["data"])
        resultado.append({
            "data": f["data"],
            "paes_qtd": f["paes_qtd"],
            "preco": preco,
            "valor": round(f["paes_qtd"] * preco, 2),
            "pago": f["data"] in datas_pagas
        })
    return jsonify(resultado)

@app.route("/api/fin/paes-historico-pagamentos", methods=["GET"])
@login_requerido
def paes_historico_pagamentos():
    err = somente_admin()
    if err: return err
    db = get_db()
    rows = db.execute(
        "SELECT * FROM fin_paes_pagamento ORDER BY pago_em DESC"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/fin/paes-pagamento/<int:pid>", methods=["DELETE"])
@login_requerido
def desfazer_pagamento_paes(pid):
    """Remove um registro de pagamento de pães, liberando as datas para novo pagamento."""
    err = somente_admin()
    if err: return err
    db = get_db()
    reg = db.execute("SELECT * FROM fin_paes_pagamento WHERE id=?", (pid,)).fetchone()
    if not reg:
        db.close()
        return jsonify({"erro": "Registro não encontrado"}), 404
    # Desfazer também as contas a pagar vinculadas (se houver)
    datas = [dt.strip() for dt in (reg["datas"] or "").split(",") if dt.strip()]
    for data in datas:
        db.execute(
            "DELETE FROM fin_contas_pagar WHERE descricao=? AND status='pago'",
            (f"Pães — {data}",)
        )
    db.execute("DELETE FROM fin_paes_pagamento WHERE id=?", (pid,))
    db.commit(); db.close()
    return jsonify({"ok": True, "datas_liberadas": datas})

@app.route("/api/fin/paes-lancar-contas", methods=["POST"])
@login_requerido
def paes_lancar_contas():
    """Lança dias de pães selecionados em Contas a Pagar como 'em aberto'."""
    err = somente_admin()
    if err: return err
    d = request.json
    dias = d.get("dias", [])  # lista de {data, valor, preco, paes_qtd}
    if not dias:
        return jsonify({"erro": "Nenhum dia informado"}), 400
    agora = datetime.now().isoformat()
    db = get_db()
    # Buscar pagamentos já existentes para evitar duplicar
    pagas_existentes = set()
    rows = db.execute("SELECT datas FROM fin_paes_pagamento").fetchall()
    for r in rows:
        for dt in (r["datas"] or "").split(","):
            pagas_existentes.add(dt.strip())
    ids_criados = []
    for dia in dias:
        data = dia["data"]
        if data in pagas_existentes:
            continue
        descricao = f"Pães — {data}"
        # Verificar se já existe conta a pagar em aberto para esse dia
        existente = db.execute(
            "SELECT id FROM fin_contas_pagar WHERE descricao=? AND status='aberto'", (descricao,)
        ).fetchone()
        if existente:
            ids_criados.append(existente["id"])
            continue
        cur = db.execute(
            """INSERT INTO fin_contas_pagar
               (descricao,valor,vencimento,status,categoria,observacao,usuario_id,criado_em)
               VALUES (?,?,?,?,?,?,?,?)""",
            (descricao, float(dia["valor"]), data, "aberto", "Fornecedor",
             f"{dia.get('paes_qtd',0)} pães × R${dia.get('preco',0):.2f}",
             session.get("usuario_id"), agora)
        )
        ids_criados.append(cur.lastrowid)
    db.commit(); db.close()
    return jsonify({"ok": True, "criadas": len(ids_criados)}), 201


@app.route("/api/fin/paes-pagamento", methods=["POST"])
@login_requerido
def registrar_pagamento_paes():
    """Marca contas a pagar de pães como pagas (ou cria já paga se não existir)."""
    err = somente_admin()
    if err: return err
    d = request.json
    datas = d.get("datas", [])
    valor = float(d.get("valor", 0))
    if not datas or not valor:
        return jsonify({"erro": "Selecione ao menos um dia e informe o valor"}), 400
    agora = datetime.now().isoformat()
    hoje = datetime.now().strftime("%Y-%m-%d")
    datas_str = ", ".join(sorted(datas))
    descricao_pagamento = f"Pães — {datas_str}"
    db = get_db()
    # Marcar contas a pagar individuais como pagas
    for data in datas:
        descricao_dia = f"Pães — {data}"
        conta = db.execute(
            "SELECT id FROM fin_contas_pagar WHERE descricao=? AND status='aberto'", (descricao_dia,)
        ).fetchone()
        if conta:
            db.execute("UPDATE fin_contas_pagar SET status='pago', pago_em=? WHERE id=?",
                       (agora, conta["id"]))
        else:
            # Se não existe conta individual, cria já paga (compatibilidade)
            valor_dia = round(valor / len(datas), 2)
            db.execute(
                """INSERT INTO fin_contas_pagar
                   (descricao,valor,vencimento,status,categoria,pago_em,usuario_id,criado_em)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (descricao_dia, valor_dia, data, "pago", "Fornecedor",
                 agora, session.get("usuario_id"), agora)
            )
    # Registrar no histórico de pagamentos de pães
    db.execute(
        "INSERT INTO fin_paes_pagamento (descricao,valor,datas,pago_em,usuario_id,criado_em) VALUES (?,?,?,?,?,?)",
        (descricao_pagamento, valor, ",".join(sorted(datas)), agora, session.get("usuario_id"), agora)
    )
    db.commit(); db.close()
    return jsonify({"ok": True}), 201


# ── Massas de Pizza ───────────────────────────────────────────────────────────
MASSA_TIPOS = ["p","m","g","gg","burg"]

@app.route("/api/fin/massa-precos", methods=["GET"])
@login_requerido
def listar_massa_precos():
    err = somente_admin()
    if err: return err
    db = get_db()
    rows = db.execute("SELECT * FROM fin_massa_precos ORDER BY vigente_de DESC").fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/fin/massa-precos", methods=["POST"])
@login_requerido
def salvar_massa_preco():
    err = somente_admin()
    if err: return err
    d = request.json
    vigente_de = d.get("vigente_de")
    if not vigente_de:
        return jsonify({"erro": "Data de vigência obrigatória"}), 400
    db = get_db()
    db.execute(
        """INSERT OR REPLACE INTO fin_massa_precos
           (vigente_de,preco_p,preco_m,preco_g,preco_gg,preco_burg,usuario_id,criado_em)
           VALUES (?,?,?,?,?,?,?,?)""",
        (vigente_de,
         float(d.get("preco_p",0)), float(d.get("preco_m",0)),
         float(d.get("preco_g",0)), float(d.get("preco_gg",0)),
         float(d.get("preco_burg",0)),
         session.get("usuario_id"), datetime.now().isoformat())
    )
    db.commit(); db.close()
    return jsonify({"ok": True}), 201

@app.route("/api/fin/massa-precos/<string:data>", methods=["DELETE"])
@login_requerido
def deletar_massa_preco(data):
    err = somente_admin()
    if err: return err
    db = get_db()
    db.execute("DELETE FROM fin_massa_precos WHERE vigente_de=?", (data,))
    db.commit(); db.close()
    return jsonify({"ok": True})

@app.route("/api/fin/massa-entregas", methods=["GET"])
@login_requerido
def listar_massa_entregas():
    err = somente_admin()
    if err: return err
    mes = request.args.get("mes")
    db = get_db()
    if mes:
        rows = db.execute(
            "SELECT * FROM fin_massa_entregas WHERE data LIKE ? ORDER BY data DESC",
            (f"{mes}%",)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM fin_massa_entregas ORDER BY data DESC LIMIT 60"
        ).fetchall()
    precos = db.execute(
        "SELECT * FROM fin_massa_precos ORDER BY vigente_de DESC"
    ).fetchall()
    db.close()

    def preco_vigente(data):
        for p in precos:
            if p["vigente_de"] <= data:
                return dict(p)
        return {"preco_p":0,"preco_m":0,"preco_g":0,"preco_gg":0,"preco_burg":0}

    resultado = []
    for r in rows:
        rd = dict(r)
        p = preco_vigente(rd["data"])
        rd["preco_p"]    = p.get("preco_p",0)
        rd["preco_m"]    = p.get("preco_m",0)
        rd["preco_g"]    = p.get("preco_g",0)
        rd["preco_gg"]   = p.get("preco_gg",0)
        rd["preco_burg"] = p.get("preco_burg",0)
        rd["valor_calculado"] = round(
            rd["qtd_p"]*rd["preco_p"] + rd["qtd_m"]*rd["preco_m"] +
            rd["qtd_g"]*rd["preco_g"] + rd["qtd_gg"]*rd["preco_gg"] +
            rd["qtd_burg"]*rd["preco_burg"], 2)
        resultado.append(rd)
    return jsonify(resultado)

@app.route("/api/fin/massa-entregas", methods=["POST"])
@login_requerido
def registrar_massa_entrega():
    err = somente_admin()
    if err: return err
    d = request.json
    if not d.get("data"):
        return jsonify({"erro": "Data obrigatória"}), 400
    agora = datetime.now().isoformat()
    db = get_db()
    # Inserir entrega
    cur = db.execute(
        """INSERT INTO fin_massa_entregas
           (data,qtd_gg,qtd_g,qtd_m,qtd_p,qtd_burg,valor_total,observacao,pago,usuario_id,criado_em)
           VALUES (?,?,?,?,?,?,?,?,0,?,?)""",
        (d["data"],
         int(d.get("qtd_gg",0)), int(d.get("qtd_g",0)),
         int(d.get("qtd_m",0)), int(d.get("qtd_p",0)),
         int(d.get("qtd_burg",0)),
         float(d.get("valor_total",0)),
         d.get("observacao",""),
         session.get("usuario_id"), agora)
    )
    entrega_id = cur.lastrowid
    # Criar conta a pagar em aberto
    valor = float(d.get("valor_total",0))
    data_fmt = new_data = d["data"]
    descricao = f"Massas — {data_fmt}"
    conta_cur = db.execute(
        """INSERT INTO fin_contas_pagar
           (descricao,valor,vencimento,status,categoria,observacao,usuario_id,criado_em)
           VALUES (?,?,?,?,?,?,?,?)""",
        (descricao, valor, data_fmt, "aberto", "Fornecedor",
         d.get("observacao",""), session.get("usuario_id"), agora)
    )
    conta_id = conta_cur.lastrowid
    # Vincular conta à entrega
    db.execute("UPDATE fin_massa_entregas SET conta_pagar_id=? WHERE id=?", (conta_id, entrega_id))
    db.commit(); db.close()
    return jsonify({"ok": True, "entrega_id": entrega_id, "conta_pagar_id": conta_id}), 201

@app.route("/api/fin/massa-entregas/<int:eid>", methods=["PUT"])
@login_requerido
def atualizar_massa_entrega(eid):
    err = somente_admin()
    if err: return err
    d = request.json
    db = get_db()
    db.execute(
        """UPDATE fin_massa_entregas SET
           qtd_p=?,qtd_m=?,qtd_g=?,qtd_gg=?,qtd_burg=?,valor_total=?,observacao=?
           WHERE id=?""",
        (int(d.get("qtd_p",0)), int(d.get("qtd_m",0)),
         int(d.get("qtd_g",0)), int(d.get("qtd_gg",0)),
         int(d.get("qtd_burg",0)),
         float(d.get("valor_total",0)),
         d.get("observacao",""), eid)
    )
    db.commit(); db.close()
    return jsonify({"ok": True})

@app.route("/api/fin/massa-entregas/<int:eid>", methods=["DELETE"])
@login_requerido
def deletar_massa_entrega(eid):
    err = somente_admin()
    if err: return err
    db = get_db()
    entrega = db.execute("SELECT conta_pagar_id FROM fin_massa_entregas WHERE id=? AND pago=0", (eid,)).fetchone()
    if entrega:
        if entrega["conta_pagar_id"]:
            db.execute("DELETE FROM fin_contas_pagar WHERE id=?", (entrega["conta_pagar_id"],))
        db.execute("DELETE FROM fin_massa_entregas WHERE id=?", (eid,))
    db.commit(); db.close()
    return jsonify({"ok": True})

@app.route("/api/fin/massa-pagamento", methods=["POST"])
@login_requerido
def registrar_pagamento_massa():
    err = somente_admin()
    if err: return err
    d = request.json
    ids = d.get("ids", [])
    if not ids:
        return jsonify({"erro": "Selecione ao menos uma entrega"}), 400
    agora = datetime.now().isoformat()
    db = get_db()
    ph = ",".join("?" for _ in ids)
    entregas = db.execute(
        f"SELECT id, conta_pagar_id, valor_total FROM fin_massa_entregas WHERE id IN ({ph})", ids
    ).fetchall()
    # Marcar cada conta a pagar vinculada como paga
    for e in entregas:
        if e["conta_pagar_id"]:
            db.execute(
                "UPDATE fin_contas_pagar SET status='pago', pago_em=? WHERE id=?",
                (agora, e["conta_pagar_id"])
            )
    # Marcar entregas como pagas
    db.execute(f"UPDATE fin_massa_entregas SET pago=1 WHERE id IN ({ph})", ids)
    db.commit(); db.close()
    total = sum(e["valor_total"] for e in entregas)
    return jsonify({"ok": True, "valor_total": total}), 201


@app.route("/api/fin/meta-mensal", methods=["GET"])
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


@app.route("/api/fin/meta-mensal", methods=["POST"])
@login_requerido
def salvar_meta_mensal():
    err = somente_admin()
    if err: return err
    d = request.json
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


@app.route("/api/fin/comparativo-fds")
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

    if modo == "mes":
        # Agrupar por semana do mês
        from datetime import date
        fds_grupos = {}
        for r in rows:
            dt = date.fromisoformat(r["data"])
            # Número da semana dentro do mês (1-5)
            semana = (dt.day - 1) // 7 + 1
            key = f"FDS {semana}"
            if key not in fds_grupos:
                fds_grupos[key] = {"label": key, "dias": []}
            venda = r["credito"] + r["debito"] + r["voucher"] + r["pix"] + r["dinheiro"]
            fds_grupos[key]["dias"].append({
                "data": r["data"],
                "dia_nome": NOME_DIA.get(r["dia_semana"], ""),
                "venda": venda,
                "delivery_val": r["delivery_val"],
                "delivery_qtd": r["delivery_qtd"],
            })
        # Calcular totais por FDS
        resultado = []
        for key, g in fds_grupos.items():
            total = sum(d["venda"] for d in g["dias"])
            g["total"] = total
            resultado.append(g)
        return jsonify({"modo": "mes", "mes": mes, "fds": resultado})

    else:
        # Agrupar por mês → semanas dentro de cada mês
        from datetime import date
        meses_grupos = {}
        for r in rows:
            dt = date.fromisoformat(r["data"])
            mes_ref = r["mes_ref"]
            semana = (dt.day - 1) // 7 + 1
            if mes_ref not in meses_grupos:
                meses_grupos[mes_ref] = {}
            key = f"FDS {semana}"
            if key not in meses_grupos[mes_ref]:
                meses_grupos[mes_ref][key] = {"label": key, "total": 0, "dias": []}
            venda = r["credito"] + r["debito"] + r["voucher"] + r["pix"] + r["dinheiro"]
            meses_grupos[mes_ref][key]["total"] += venda
            meses_grupos[mes_ref][key]["dias"].append({
                "data": r["data"],
                "dia_nome": NOME_DIA.get(r["dia_semana"], ""),
                "venda": venda,
            })
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

@app.route("/api/fin/comparativo-resultado")
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

@app.route("/api/fin/relatorio-mensal")
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


if __name__=="__main__":
    # Limpa arquivos de lock órfãos de execuções anteriores que travaram
    for ext in ["-wal", "-shm", "-journal"]:
        lock_file = DB_PATH + ext
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
                print(f"🧹 Removido arquivo de lock: {os.path.basename(lock_file)}")
            except Exception as _e:
                print(f"⚠️  Não foi possível remover {lock_file}: {_e}")
    init_db()
    cfg=load_config()
    # Backup automático diário (na inicialização, se ainda não foi feito hoje)
    if backup_diario_necessario():
        nome_bkp = fazer_backup(motivo="automatico")
        if nome_bkp:
            print(f"💾  Backup automático criado: {nome_bkp}")
    print("\n✅  Banco inicializado.")
    print(f"👤  Admin padrão: usuário=admin  senha=admin123")
    print(f"🚀  http://{cfg['host']}:{cfg['porta']}\n")

    # Tenta usar Waitress (servidor de produção para Windows)
    # Se não estiver instalado, cai para o servidor de desenvolvimento do Flask
    try:
        from waitress import serve
        print("🟢  Usando Waitress (servidor de produção)\n")
        serve(app, host=cfg["host"], port=cfg["porta"], threads=4)
    except ImportError:
        print("⚠️  Waitress não encontrado, usando servidor Flask (development)")
        print("   Para instalar: pip install waitress\n")
        app.run(host=cfg["host"], port=cfg["porta"], debug=False)
