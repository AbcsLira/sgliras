"""Inicialização, migrações e conexões SQLite."""
import sqlite3
import secrets
from datetime import datetime
from flask import current_app, g
from .seguranca import hash_senha

def init_db():
    """Inicializa o banco e retorna a senha somente se criar o primeiro usuário."""
    conn = sqlite3.connect(current_app.config["DATABASE"])
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        senha_inicial = _initialize_db(conn)
        conn.commit()
        return senha_inicial
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _initialize_db(conn):
    c = conn.cursor()
    # executescript encerra uma transação já aberta. O BEGIN dentro do script
    # mantém criação, migrações e dados iniciais na mesma transação.
    c.executescript("""
        BEGIN IMMEDIATE;
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
            ativo           INTEGER NOT NULL DEFAULT 1,
            codigo_barras   TEXT,
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
        CREATE TABLE IF NOT EXISTS operacoes_idempotentes (
            operacao_id TEXT PRIMARY KEY,
            usuario_id  INTEGER NOT NULL,
            rota        TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            resposta    TEXT NOT NULL,
            criado_em   TEXT NOT NULL
        );
        INSERT OR IGNORE INTO categorias (nome) VALUES
            ('Alimentos'),('Bebidas'),('Limpeza'),('Embalagens'),('Outros'),('Molhos'),('Oficina'),('Gelatos');
    """)
    from .cartoes import inicializar_tabelas
    inicializar_tabelas(conn)
    # Preserva categorias existentes, inclusive 'Oficinas', que pode estar em
    # uso por produtos. Migrações só ignoram colunas comprovadamente existentes.
    for table, column, definition in [
        ("produtos", "unidade", "TEXT NOT NULL DEFAULT 'un'"),
        ("produtos", "sub_qtd_por_un", "REAL"),
        ("produtos", "sub_unidade", "TEXT"),
        ("movimentacoes", "usuario_id", "INTEGER REFERENCES usuarios(id)"),
        ("produtos", "unid_por_fardo", "REAL"),
        ("produtos", "unid_fardo_label", "TEXT DEFAULT 'fd'"),
        ("produtos", "validade", "TEXT"),
        ("fin_fechamento_diario", "preco_pao", "REAL NOT NULL DEFAULT 0"),
        ("produtos", "preco_embalagem", "REAL"),
        ("produtos", "tipo_embalagem", "TEXT"),
        ("produtos", "unid_embalagem", "INTEGER"),
        ("fin_massa_entregas", "conta_pagar_id", "INTEGER REFERENCES fin_contas_pagar(id)"),
        ("fin_paes_pagamento", "conta_pagar_id", "INTEGER REFERENCES fin_contas_pagar(id)"),
        ("produtos", "ativo", "INTEGER NOT NULL DEFAULT 1"),
        ("produtos", "codigo_barras", "TEXT"),
    ]:
        columns = {row[1].casefold() for row in c.execute(f"PRAGMA table_info({table})")}
        if column.casefold() not in columns:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    senha_inicial = None
    if not c.execute("SELECT id FROM usuarios LIMIT 1").fetchone():
        senha_inicial = secrets.token_urlsafe(18)
        c.execute("INSERT INTO usuarios (nome,usuario,senha,perfil,ativo,criado_em) VALUES (?,?,?,?,?,?)",
                  ("Administrador","admin",hash_senha(senha_inicial),"admin",1,datetime.now().isoformat()))
    # Popular categorias padrão de contas a pagar se ainda não existirem
    if not c.execute("SELECT id FROM fin_categorias_pagar LIMIT 1").fetchone():
        cats_padrao = ["Fornecedor","Água/Luz/Gás","Salário","Manutenção","Impostos","Outros"]
        for cat in cats_padrao:
            c.execute("INSERT OR IGNORE INTO fin_categorias_pagar (nome,criado_em) VALUES (?,?)",
                      (cat, datetime.now().isoformat()))
    return senha_inicial

def get_db():
    conn = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
    except Exception:
        conn.close()
        raise
    g.setdefault("_database_connections", []).append(conn)
    return conn


def close_connections(error=None):
    """Fecha também conexões esquecidas por rotas que falharam no meio.

    Mantém o contrato de get_db: cada chamada abre uma conexão independente e
    as rotas continuam podendo fechá-la explicitamente antes do fim do request.
    """
    for conn in g.pop("_database_connections", []):
        conn.close()
