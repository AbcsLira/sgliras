"""Inicialização, migrações e conexões SQLite."""
import sqlite3
from datetime import datetime
from flask import current_app
from .security import hash_senha

def init_db():
    conn = sqlite3.connect(current_app.config["DATABASE"])
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
        "ALTER TABLE produtos ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE produtos ADD COLUMN codigo_barras TEXT",
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
    conn = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn
