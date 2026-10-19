"""Credenciais iniciais em bancos temporários, sem redefinir contas existentes."""
from contextlib import closing, redirect_stdout
from io import StringIO
from pathlib import Path
import runpy
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from sgliras import create_app
from sgliras.banco_dados import init_db
from sgliras.seguranca import hash_senha, verificar_senha


class PrimeiroAcessoTests(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.raiz = Path(pasta.name)
        self.app = self.aplicacao('primeiro')

    def aplicacao(self, nome):
        return create_app({
            'TESTING': True, 'SECRET_KEY': 'primeiro-acesso-apenas-testes',
            'DATABASE': str(self.raiz / f'{nome}.db'),
            'BACKUP_DIR': str(self.raiz / f'{nome}-backups'),
        })

    def inicializar(self, app=None):
        with (app or self.app).app_context():
            return init_db()

    def usuarios(self):
        with closing(sqlite3.connect(self.app.config['DATABASE'])) as banco:
            return banco.execute('SELECT usuario,senha,perfil,ativo FROM usuarios ORDER BY id').fetchall()

    def test_primeira_senha_e_aleatoria_e_login_recusa_senha_publica_antiga(self):
        senha = self.inicializar()
        self.assertGreaterEqual(len(senha), 24)
        usuario, armazenada, perfil, ativo = self.usuarios()[0]
        self.assertEqual((usuario, perfil, ativo), ('admin', 'admin', 1))
        self.assertNotEqual(armazenada, senha)
        self.assertTrue(verificar_senha(armazenada, senha))
        cliente = self.app.test_client()
        self.assertEqual(cliente.post('/api/auth/login', json={
            'usuario': 'admin', 'senha': 'admin123',
        }).status_code, 401)
        self.assertEqual(cliente.post('/api/auth/login', json={
            'usuario': 'admin', 'senha': senha,
        }).status_code, 200)

    def test_instalacoes_distintas_geram_senhas_distintas(self):
        self.assertNotEqual(self.inicializar(), self.inicializar(self.aplicacao('outra')))

    def test_reinicializacao_preserva_conta_e_nao_retorna_senha_novamente(self):
        self.inicializar()
        antes = self.usuarios()
        with patch('sgliras.banco_dados.secrets.token_urlsafe') as gerar:
            self.assertIsNone(self.inicializar())
        gerar.assert_not_called()
        self.assertEqual(self.usuarios(), antes)

    def test_instalacao_existente_preserva_senha_alterada_e_login_renomeado(self):
        self.inicializar()
        senha_alterada = hash_senha('senha-alterada-na-instalacao')
        with closing(sqlite3.connect(self.app.config['DATABASE'])) as banco, banco:
            banco.execute('UPDATE usuarios SET usuario=?,senha=? WHERE id=1', ('gerente', senha_alterada))
        antes = self.usuarios()
        self.assertIsNone(self.inicializar())
        self.assertEqual(self.usuarios(), antes)
        self.assertEqual(len(self.usuarios()), 1)
        self.assertTrue(verificar_senha(self.usuarios()[0][1], 'senha-alterada-na-instalacao'))

    def iniciar_servidor(self):
        saida = StringIO()
        with patch('sgliras.create_app', return_value=self.app), \
                patch('sgliras.configuracao.load_config', return_value={'host': '127.0.0.1', 'porta': 5000}), \
                patch('sgliras.copias_seguranca.backup_diario_necessario', return_value=False), \
                patch('waitress.serve'), redirect_stdout(saida):
            runpy.run_path(str(Path(__file__).resolve().parents[1] / 'app.py'), run_name='__main__')
        return saida.getvalue()

    def test_partida_mostra_senha_so_na_primeira_criacao(self):
        primeira = self.iniciar_servidor()
        linhas = [linha for linha in primeira.splitlines() if linha.startswith('Senha inicial: ')]
        self.assertEqual(len(linhas), 1)
        senha = linhas[0].removeprefix('Senha inicial: ')
        self.assertTrue(verificar_senha(self.usuarios()[0][1], senha))
        self.assertNotIn('admin123', primeira)
        segunda = self.iniciar_servidor()
        self.assertNotIn('Senha inicial:', segunda)
        self.assertNotIn(senha, segunda)
        self.assertNotIn('admin123', segunda)

    def test_falha_na_migracao_nao_publica_credencial_nem_efetiva_usuario(self):
        from sgliras import banco_dados

        inicializar = banco_dados._initialize_db

        def falhar_apos_criacao(conexao):
            inicializar(conexao)
            raise sqlite3.OperationalError('Falha simulada antes do commit')

        with patch('sgliras.banco_dados._initialize_db', side_effect=falhar_apos_criacao):
            with self.assertRaises(sqlite3.OperationalError):
                self.inicializar()
        with closing(sqlite3.connect(self.app.config['DATABASE'])) as banco:
            self.assertIsNone(banco.execute("SELECT name FROM sqlite_master WHERE name='usuarios'").fetchone())
        self.assertIsInstance(self.inicializar(), str)


if __name__ == '__main__':
    unittest.main()
