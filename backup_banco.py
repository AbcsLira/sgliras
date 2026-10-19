"""Cópia consistente de SQLite, inclusive com gravações ainda no WAL.

Uso: python backup_banco.py <arquivo_destino> [--origem <banco>]
     python backup_banco.py --pasta <diretorio> [--origem <banco>]
O destino deve ser um arquivo novo; backups existentes nunca são substituídos.
"""
import argparse
from contextlib import closing
from datetime import datetime
import os
from pathlib import Path
import sqlite3
import sys
import tempfile


ORIGEM = Path(__file__).resolve().parent / "estoque.db"


def _publicar_sem_sobrescrever(temporario, destino):
    """Publica somente a cópia validada, sem substituir outro arquivo."""
    if sys.platform == "win32":
        # No Windows, rename recusa destino existente, inclusive em FAT/exFAT.
        os.rename(temporario, destino)
    else:
        # rename em Unix substituiria o destino; link é uma criação exclusiva.
        # O temporário fica na mesma pasta para não cruzar sistemas de arquivos.
        os.link(temporario, destino)


def criar_backup(origem, destino):
    """Gera, verifica e publica um backup; falhas não deixam um .db parcial."""
    origem = Path(origem).resolve(strict=True)
    destino = Path(destino).absolute()
    if not origem.is_file():
        raise ValueError("O banco de origem deve ser um arquivo")
    if destino.resolve() == origem:
        raise ValueError("O destino não pode ser o banco de origem")
    if destino.exists() or destino.is_symlink():
        raise FileExistsError(f"O destino já existe e foi preservado: {destino}")

    descritor, nome_temporario = tempfile.mkstemp(
        prefix=f".{destino.name}.", suffix=".tmp", dir=destino.parent,
    )
    os.close(descritor)
    temporario = Path(nome_temporario)
    try:
        # mode=ro impede a criação silenciosa de um banco vazio na origem.
        with closing(sqlite3.connect(
                origem.as_uri() + "?mode=ro", uri=True, timeout=30)) as fonte:
            with closing(sqlite3.connect(temporario, timeout=30)) as copia:
                fonte.backup(copia)
                # O destino deve ser autossuficiente, sem depender de sidecars.
                copia.execute("PRAGMA journal_mode=DELETE")
                resultado = copia.execute("PRAGMA integrity_check").fetchall()
                if resultado != [("ok",)]:
                    raise sqlite3.DatabaseError(
                        f"A verificação de integridade do backup falhou: {resultado}"
                    )
        # FlushFileBuffers no Windows exige um descritor com acesso de escrita.
        with temporario.open("r+b") as arquivo:
            os.fsync(arquivo.fileno())
        _publicar_sem_sobrescrever(temporario, destino)
    finally:
        # As conexões já foram fechadas, inclusive quando abrir/copiar falha.
        for sufixo in ("", "-wal", "-shm", "-journal"):
            Path(str(temporario) + sufixo).unlink(missing_ok=True)
    return destino


def main(argumentos=None):
    parser = argparse.ArgumentParser(description=__doc__)
    destinos = parser.add_mutually_exclusive_group(required=True)
    destinos.add_argument("destino", nargs="?", help="Arquivo novo para receber o backup")
    destinos.add_argument("--pasta", type=Path, help="Diretório para um backup com data e hora únicas")
    parser.add_argument("--origem", default=ORIGEM, help="Banco de origem")
    opcoes = parser.parse_args(argumentos)
    destino = opcoes.destino
    if opcoes.pasta is not None:
        nome = datetime.now().strftime("estoque_%Y-%m-%d_%H-%M-%S-%f.db")
        destino = opcoes.pasta / nome
    try:
        destino = criar_backup(opcoes.origem, destino)
    except (OSError, sqlite3.Error, ValueError) as erro:
        print(f"Falha no backup: {erro}", file=sys.stderr)
        return 1
    print(f"Backup consistente criado: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
