"""Entrada compatível com os scripts existentes: python app.py."""
from sgliras import create_app
from sgliras.configuracao import load_config
from sgliras.banco_dados import init_db
from sgliras.copias_seguranca import backup_diario_necessario, fazer_backup

app = create_app()

if __name__=="__main__":
    # NUNCA apagar os arquivos -wal/-shm manualmente: em modo WAL eles guardam
    # transações confirmadas que ainda não foram gravadas no .db principal.
    # O próprio SQLite recupera esses arquivos automaticamente ao abrir a conexão.
    with app.app_context():
        init_db()
    cfg=load_config()
    # Backup automático diário (na inicialização, se ainda não foi feito hoje)
    with app.app_context():
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
