"""Backup externo consistente, exclusivo e com liberação de arquivos no Windows."""
from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import date, timedelta
import io
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import backup_banco


class BackupExternoTests(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.origem = self.raiz / "origem.db"
        self.destino = self.raiz / "copia.db"
        with closing(sqlite3.connect(self.origem)) as banco, banco:
            banco.execute("CREATE TABLE produtos (nome TEXT)")
            banco.execute("INSERT INTO produtos VALUES ('Existente')")

    def assert_conexoes_fechadas(self, conexoes):
        for conexao in conexoes:
            with self.assertRaises(sqlite3.ProgrammingError):
                conexao.execute("SELECT 1")
        self.assertEqual(list(self.raiz.glob(".*.tmp*")), [])

    def test_copia_inclui_dados_ainda_no_wal_sem_alterar_a_origem(self):
        with closing(sqlite3.connect(self.origem)) as banco:
            banco.execute("PRAGMA journal_mode=WAL")
            banco.execute("PRAGMA wal_autocheckpoint=0")
            banco.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            banco.execute("INSERT INTO produtos VALUES ('Somente no WAL')")
            banco.commit()
            self.assertGreater(Path(str(self.origem) + "-wal").stat().st_size, 0)
            # Uma cópia crua do .db perderia esta linha confirmada.
            with closing(sqlite3.connect(
                    self.origem.as_uri() + "?immutable=1", uri=True)) as cru:
                self.assertEqual(cru.execute("SELECT COUNT(*) FROM produtos").fetchone(), (1,))
            conteudo_original = self.origem.read_bytes()
            backup_banco.criar_backup(self.origem, self.destino)
            self.assertEqual(self.origem.read_bytes(), conteudo_original)
            with closing(sqlite3.connect(self.destino)) as copia:
                self.assertEqual(copia.execute("SELECT nome FROM produtos ORDER BY rowid").fetchall(),
                                 [("Existente",), ("Somente no WAL",)])
                self.assertEqual(copia.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
                self.assertEqual(copia.execute("PRAGMA journal_mode").fetchone(), ("delete",))
        self.assertFalse(Path(str(self.destino) + "-wal").exists())
        self.assertEqual(list(self.raiz.glob(".*.tmp*")), [])

    def test_destino_existente_e_banco_de_origem_sao_preservados(self):
        conteudo_original = self.origem.read_bytes()
        self.destino.write_bytes(b"backup anterior que deve ser preservado")
        with self.assertRaises(FileExistsError):
            backup_banco.criar_backup(self.origem, self.destino)
        self.assertEqual(self.destino.read_bytes(), b"backup anterior que deve ser preservado")
        with self.assertRaises(ValueError):
            backup_banco.criar_backup(self.origem, self.origem)
        self.assertEqual(self.origem.read_bytes(), conteudo_original)

    def test_origem_ausente_nao_cria_banco_vazio_ou_destino(self):
        ausente = self.raiz / "ausente.db"
        with self.assertRaises(FileNotFoundError):
            backup_banco.criar_backup(ausente, self.destino)
        self.assertFalse(ausente.exists())
        self.assertFalse(self.destino.exists())

    def test_origem_corrompida_e_preservada_e_nao_gera_backup(self):
        self.origem.write_bytes(b"Este arquivo nao e um banco SQLite")
        with self.assertRaises(sqlite3.DatabaseError):
            backup_banco.criar_backup(self.origem, self.destino)
        self.assertEqual(self.origem.read_bytes(), b"Este arquivo nao e um banco SQLite")
        self.assertFalse(self.destino.exists())
        self.assertEqual(list(self.raiz.glob(".*.tmp*")), [])

    def test_sucesso_fecha_ambas_conexoes_antes_da_publicacao(self):
        conectar = sqlite3.connect
        publicar = backup_banco._publicar_sem_sobrescrever
        conexoes = []

        def abrir(*args, **kwargs):
            conexao = conectar(*args, **kwargs)
            conexoes.append(conexao)
            return conexao

        def verificar_fechamento(temporario, destino):
            self.assertEqual(len(conexoes), 2)
            for conexao in conexoes:
                with self.assertRaises(sqlite3.ProgrammingError):
                    conexao.execute("SELECT 1")
            publicar(temporario, destino)

        with patch.object(backup_banco.sqlite3, "connect", abrir):
            with patch.object(backup_banco, "_publicar_sem_sobrescrever", verificar_fechamento):
                backup_banco.criar_backup(self.origem, self.destino)
        self.assert_conexoes_fechadas(conexoes)
        self.assertTrue(self.destino.exists())

    def test_destino_criado_durante_backup_nao_e_substituido(self):
        publicar = backup_banco._publicar_sem_sobrescrever

        def criar_concorrente(temporario, destino):
            destino.write_bytes(b"backup de outra execucao")
            publicar(temporario, destino)

        with patch.object(backup_banco, "_publicar_sem_sobrescrever", criar_concorrente):
            with self.assertRaises(FileExistsError):
                backup_banco.criar_backup(self.origem, self.destino)
        self.assertEqual(self.destino.read_bytes(), b"backup de outra execucao")
        self.assertEqual(list(self.raiz.glob(".*.tmp*")), [])

    def test_falha_ao_abrir_destino_fecha_origem_e_remove_temporario(self):
        conectar = sqlite3.connect
        conexoes = []

        def abrir(*args, **kwargs):
            if conexoes:
                raise sqlite3.OperationalError("Dispositivo indisponível")
            conexao = conectar(*args, **kwargs)
            conexoes.append(conexao)
            return conexao

        with patch.object(backup_banco.sqlite3, "connect", abrir):
            with self.assertRaises(sqlite3.OperationalError):
                backup_banco.criar_backup(self.origem, self.destino)
        self.assert_conexoes_fechadas(conexoes)
        self.assertFalse(self.destino.exists())

    def test_falha_na_copia_fecha_ambas_conexoes_e_nao_publica_backup(self):
        conectar = sqlite3.connect
        conexoes = []

        class ConexaoComFalha(sqlite3.Connection):
            def backup(self, destino, **opcoes):
                raise sqlite3.OperationalError("Falha durante a cópia")

        def abrir(*args, **kwargs):
            if not conexoes:
                kwargs["factory"] = ConexaoComFalha
            conexao = conectar(*args, **kwargs)
            conexoes.append(conexao)
            return conexao

        with patch.object(backup_banco.sqlite3, "connect", abrir):
            with self.assertRaises(sqlite3.OperationalError):
                backup_banco.criar_backup(self.origem, self.destino)
        self.assertEqual(len(conexoes), 2)
        self.assert_conexoes_fechadas(conexoes)
        self.assertFalse(self.destino.exists())

    def test_integridade_invalida_fecha_conexoes_e_rejeita_destino(self):
        conectar = sqlite3.connect
        conexoes = []

        class ConexaoInvalida(sqlite3.Connection):
            def execute(self, sql, *args, **kwargs):
                if sql == "PRAGMA integrity_check":
                    return super().execute("SELECT 'falha de integridade'")
                return super().execute(sql, *args, **kwargs)

        def abrir(*args, **kwargs):
            if conexoes:
                kwargs["factory"] = ConexaoInvalida
            conexao = conectar(*args, **kwargs)
            conexoes.append(conexao)
            return conexao

        with patch.object(backup_banco.sqlite3, "connect", abrir):
            with self.assertRaisesRegex(sqlite3.DatabaseError, "integridade"):
                backup_banco.criar_backup(self.origem, self.destino)
        self.assert_conexoes_fechadas(conexoes)
        self.assertFalse(self.destino.exists())

    def test_falha_na_publicacao_fecha_conexoes_sem_deixar_parcial(self):
        conectar = sqlite3.connect
        conexoes = []

        def abrir(*args, **kwargs):
            conexao = conectar(*args, **kwargs)
            conexoes.append(conexao)
            return conexao

        with patch.object(backup_banco.sqlite3, "connect", abrir):
            with patch.object(backup_banco, "_publicar_sem_sobrescrever",
                              side_effect=PermissionError("Dispositivo desconectado")):
                with self.assertRaises(PermissionError):
                    backup_banco.criar_backup(self.origem, self.destino)
        self.assert_conexoes_fechadas(conexoes)
        self.assertFalse(self.destino.exists())

    def test_cli_sinaliza_falha_sem_anunciar_sucesso(self):
        saida = io.StringIO()
        erro = io.StringIO()
        with redirect_stdout(saida), redirect_stderr(erro):
            codigo = backup_banco.main([str(self.destino), "--origem", str(self.raiz / "ausente.db")])
        self.assertEqual(codigo, 1)
        self.assertEqual(saida.getvalue(), "")
        self.assertIn("Falha no backup", erro.getvalue())

    def test_cli_pasta_gera_dois_backups_unicos_e_preserva_o_primeiro(self):
        pasta = self.raiz / "backups por data"
        pasta.mkdir()
        comando = [sys.executable, str(Path(backup_banco.__file__)),
                   "--pasta", str(pasta), "--origem", str(self.origem)]
        resultado = subprocess.run(comando, capture_output=True, timeout=30)
        self.assertEqual(resultado.returncode, 0, (resultado.stdout, resultado.stderr))
        primeiro = next(pasta.glob("*.db"))
        conteudo_primeiro = primeiro.read_bytes()
        resultado = subprocess.run(comando, capture_output=True, timeout=30)
        self.assertEqual(resultado.returncode, 0, (resultado.stdout, resultado.stderr))
        backups = list(pasta.glob("*.db"))
        self.assertEqual(len(backups), 2)
        self.assertEqual(primeiro.read_bytes(), conteudo_primeiro)
        for arquivo in backups:
            self.assertRegex(arquivo.name, r"^estoque_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}-\d{6}\.db$")
            with closing(sqlite3.connect(arquivo)) as banco:
                self.assertEqual(banco.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
                self.assertEqual(banco.execute("SELECT nome FROM produtos").fetchall(), [("Existente",)])

    def test_cli_rejeita_destino_e_pasta_ao_mesmo_tempo(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as erro:
                backup_banco.main([str(self.destino), "--pasta", str(self.raiz)])
        self.assertEqual(erro.exception.code, 2)

    def preparar_batch(self):
        projeto = Path(backup_banco.__file__).parent
        batch = (projeto / "backup_externo.bat").read_text(encoding="utf-8")
        batch = batch.replace('set "UNIDADE_EXTERNA=G:"', f'set "UNIDADE_EXTERNA={self.raiz}"')
        script = self.raiz / "backup_externo.bat"
        script.write_text(batch, encoding="utf-8")
        shutil.copyfile(projeto / "backup_banco.py", self.raiz / "backup_banco.py")
        return script

    def executar_batch(self, script):
        ambiente = dict(os.environ)
        ambiente["PATH"] = str(Path(sys.executable).parent) + os.pathsep + ambiente.get("PATH", "")
        return subprocess.run(["cmd.exe", "/d", "/c", str(script)], cwd=self.raiz,
                              env=ambiente, capture_output=True, timeout=120)

    @unittest.skipUnless(sys.platform == "win32", "O batch exige cmd.exe do Windows")
    def test_batch_falha_principal_preserva_status_e_backups_antigos(self):
        script = self.preparar_batch()
        destino = self.raiz / "Backup_EstoqueLiras"
        banco = destino / "banco"
        banco.mkdir(parents=True)
        status = destino / "ULTIMO_BACKUP.txt"
        status.write_text("ultimo backup valido", encoding="utf-8")
        for numero in range(61):
            (banco / f"estoque_antigo_{numero:02}.db").write_bytes(b"backup valido anterior")
        antes = {arquivo.name: arquivo.read_bytes() for arquivo in banco.iterdir()}
        resultado = self.executar_batch(script)
        self.assertNotEqual(resultado.returncode, 0)
        self.assertEqual(status.read_text(encoding="utf-8"), "ultimo backup valido")
        self.assertEqual({arquivo.name: arquivo.read_bytes() for arquivo in banco.iterdir()}, antes)
        self.assertNotIn(b"concluido com sucesso", (self.raiz / "backup_externo.log").read_bytes())

    @unittest.skipUnless(sys.platform == "win32", "O batch exige cmd.exe do Windows")
    def test_batch_conserva_principal_apos_copiar_61_diarios_antigos(self):
        script = self.preparar_batch()
        shutil.copyfile(self.origem, self.raiz / "estoque.db")
        diarios = self.raiz / "backups"
        diarios.mkdir()
        nomes = []
        for numero in range(61):
            dia = date(2020, 1, 1) + timedelta(days=numero)
            nome = f"estoque_{dia.isoformat()}_03-00-00_automatico.db"
            shutil.copyfile(self.origem, diarios / nome)
            nomes.append(nome)

        resultado = self.executar_batch(script)
        self.assertEqual(resultado.returncode, 0, (resultado.stdout, resultado.stderr))
        destino = self.raiz / "Backup_EstoqueLiras"
        banco = destino / "banco"
        novos = set(arquivo.name for arquivo in banco.glob("*.db")) - set(nomes)
        self.assertEqual(len(novos), 1)
        principal = banco / novos.pop()
        self.assertRegex(principal.name, r"^estoque_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}-\d{6}\.db$")
        self.assertTrue(principal.exists(), "A retencao removeu o backup principal recente")
        self.assertEqual(len(list(banco.glob("estoque_*.db"))), 60)
        self.assertTrue((banco / nomes[-1]).exists())
        self.assertFalse((banco / nomes[0]).exists())
        self.assertTrue((destino / "ULTIMO_BACKUP.txt").exists())
        with closing(sqlite3.connect(principal)) as copia:
            self.assertEqual(copia.execute("PRAGMA integrity_check").fetchall(), [("ok",)])


if __name__ == "__main__":
    unittest.main()
