"""Pesquisa da listagem impressa com dados e banco exclusivamente temporários."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from sgliras import create_app
from sgliras.banco_dados import init_db


class PesquisaListagemTests(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.app = create_app({
            'TESTING': True,
            'SECRET_KEY': 'pesquisa-apenas-testes',
            'DATABASE': str(Path(pasta.name) / 'pesquisa.db'),
            'BACKUP_DIR': str(Path(pasta.name) / 'backups'),
        })
        with self.app.app_context():
            init_db()
        with closing(sqlite3.connect(self.app.config['DATABASE'])) as banco, banco:
            molhos = banco.execute(
                'INSERT INTO categorias (nome) VALUES (?)', ('Pesquisa Molhos',),
            ).lastrowid
            padaria = banco.execute(
                'INSERT INTO categorias (nome) VALUES (?)', ('Pesquisa Padaria',),
            ).lastrowid
            banco.executemany(
                '''INSERT INTO produtos
                   (nome,codigo,categoria_id,quantidade,preco_custo,ativo,criado_em)
                   VALUES (?,?,?,?,?,?,?)''',
                [
                    ('Molho de Pizza', 'MOL-001', molhos, 2, 3, 1, '2026-10-01'),
                    ('Molho Branco', 'MOL-002', molhos, 5, 2, 1, '2026-10-01'),
                    ('Pizza de Queijo', 'PIZ-001', padaria, 1, 12, 1, '2026-10-01'),
                    ('Polpa de Açaí', 'ACA-001', padaria, 4, 6, 1, '2026-10-01'),
                    ('Pão de Açúcar', 'PAO-001', padaria, 6, 2.5, 1, '2026-10-01'),
                    ('Molho de Pizza Especial', 'MOL-003', molhos, 100, 9, 0, '2026-10-01'),
                    ('Molho de Pizza Tradicional', 'MOL-004', padaria, 3, 4, 1, '2026-10-01'),
                ],
            )
        self.client = self.app.test_client()
        with self.client.session_transaction() as sessao:
            sessao['usuario_id'] = 1

    def listar(self, **filtros):
        resposta = self.client.get('/api/listagem-pdf', query_string=filtros)
        self.assertEqual(resposta.status_code, 200, resposta.get_json())
        return resposta.get_json()

    @staticmethod
    def itens(resposta):
        return [item for grupo in resposta['grupos'].values() for item in grupo]

    def nomes(self, resposta):
        return {item['nome'] for item in self.itens(resposta)}

    def test_palavras_fora_de_ordem_maiusculas_e_espacos(self):
        esperados = {'Molho de Pizza', 'Molho de Pizza Tradicional'}
        for busca in ('molho pizza', 'PIZZA MOLHO', '  pizza\t molho  '):
            with self.subTest(busca=busca):
                self.assertEqual(self.nomes(self.listar(nome=busca)), esperados)

    def test_busca_ignora_acentos_inclusive_unicode_decomposto(self):
        for busca in ('acai polpa', 'AÇAÍ POLPA', 'ac\u0327ai\u0301 polpa'):
            with self.subTest(busca=busca):
                self.assertEqual(self.nomes(self.listar(nome=busca)), {'Polpa de Açaí'})
        self.assertEqual(self.nomes(self.listar(nome='ACUCAR PAO')), {'Pão de Açúcar'})

    def test_exige_todas_as_palavras_no_mesmo_produto(self):
        for busca in ('pizza molho branco', 'acai queijo', 'produto inexistente'):
            with self.subTest(busca=busca):
                resposta = self.listar(nome=busca)
                self.assertEqual(resposta['grupos'], {})
                self.assertEqual(resposta['total_geral'], 0)

    def test_busca_vazia_retorna_todos_os_ativos(self):
        referencia = self.listar()
        self.assertEqual(len(self.itens(referencia)), 6)
        self.assertNotIn('Molho de Pizza Especial', self.nomes(referencia))
        self.assertEqual(referencia['total_geral'], 79)
        for busca in ('', '  \t\n  '):
            with self.subTest(busca=busca):
                resposta = self.listar(nome=busca)
                self.assertEqual(resposta['grupos'], referencia['grupos'])
                self.assertEqual(resposta['total_geral'], referencia['total_geral'])

    def test_busca_preserva_categoria_e_exclui_inativos(self):
        resposta = self.listar(nome='pizza molho', categoria='pesquisa molhos')
        self.assertEqual(set(resposta['grupos']), {'Pesquisa Molhos'})
        self.assertEqual(self.nomes(resposta), {'Molho de Pizza'})
        self.assertEqual(resposta['total_geral'], 6)
        self.assertEqual(
            self.nomes(self.listar(nome='pizza molho', categoria='Pesquisa Padaria')),
            {'Molho de Pizza Tradicional'},
        )

    def test_total_admin_considera_apenas_resultados_da_busca(self):
        resposta = self.listar(nome='pizza molho')
        self.assertTrue(resposta['eh_admin'])
        self.assertEqual(resposta['total_geral'], 18)
        self.assertEqual(
            {item['nome']: item['valor_total_item'] for item in self.itens(resposta)},
            {'Molho de Pizza': 6, 'Molho de Pizza Tradicional': 12},
        )

    def test_perfil_comum_pesquisa_sem_receber_totais_admin(self):
        with closing(sqlite3.connect(self.app.config['DATABASE'])) as banco, banco:
            banco.execute("UPDATE usuarios SET perfil='estoquista' WHERE id=1")
        resposta = self.listar(nome='PIZZA MOLHO')
        self.assertEqual(self.nomes(resposta), {'Molho de Pizza', 'Molho de Pizza Tradicional'})
        self.assertFalse(resposta['eh_admin'])
        self.assertIsNone(resposta['total_geral'])
        self.assertTrue(all(item['valor_total_item'] is None for item in self.itens(resposta)))


if __name__ == '__main__':
    unittest.main()
