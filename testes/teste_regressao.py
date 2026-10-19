"""Regressão HTTP com bancos temporários; nunca usa estoque.db real."""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest

from sgliras import create_app
from sgliras.banco_dados import init_db


def normalize(value):
    if isinstance(value, dict):
        return {k: ('<timestamp>' if k in ('criado_em', 'gerado_em') else normalize(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.app = create_app({
            'TESTING': True, 'SECRET_KEY': 'test-only',
            'DATABASE': str(Path(self.directory.name) / 'test.db'),
            'BACKUP_DIR': str(Path(self.directory.name) / 'backups'),
        })
        with self.app.app_context():
            self.senha_inicial = init_db()
        self.client = self.app.test_client()

    def login(self):
        response = self.client.post('/api/auth/login', json={
            'usuario': 'admin', 'senha': self.senha_inicial,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['ok'])

    def test_legacy_routes_and_responses_for_all_roles(self):
        baseline = json.loads((Path(__file__).parent / 'dados_referencia/http_anterior.json').read_text(encoding='utf-8'))
        added_routes = {'/api/movimentacoes/lote', '/api/fin/contas-pagar/lote'}
        routes = sorted((r.rule, r.endpoint, sorted(r.methods)) for r in self.app.url_map.iter_rules()
                        if r.rule not in added_routes)
        self.assertEqual(json.loads(json.dumps(routes)), baseline['routes'])
        for role in (None, 'admin', 'caixa', 'estoquista'):
            # Permissions now come from the current user record, not stale cookies.
            if role:
                with closing(sqlite3.connect(self.app.config['DATABASE'])) as db, db:
                    db.execute('UPDATE usuarios SET perfil=? WHERE id=1', (role,))
            with self.client.session_transaction() as session:
                session.clear()
                if role:
                    session.update(usuario_id=1, usuario='admin', nome='Administrador', perfil=role)
            for rule in self.app.url_map.iter_rules():
                if 'GET' not in rule.methods or rule.rule.startswith('/static'):
                    continue
                url = re.sub(r'<(?:[^:>]+:)?([^>]+)>', lambda m:
                             '2026-10-01' if m[1] == 'data' else
                             'missing.db' if m[1] == 'nome' else '1', rule.rule)
                with self.subTest(role=role, route=rule.rule):
                    response = self.client.get(url)
                    actual = {'status': response.status_code, 'json': response.get_json(),
                              'location': response.headers.get('Location')}
                    expected = baseline['responses'][f'{role}:{rule.rule}']
                    if role == 'admin' and rule.rule == '/api/status-backup':
                        # Physical file size changes when the schema grows; validate
                        # a positive reported size instead of the old page count.
                        self.assertGreater(actual['json']['tamanho_banco_kb'], 0)
                        actual['json'].pop('tamanho_banco_kb')
                        expected = {**expected, 'json': {k: v for k, v in expected['json'].items()
                                                        if k != 'tamanho_banco_kb'}}
                    self.assertEqual(normalize(actual), expected)

    def test_login_pages_assets_and_logout(self):
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'loginForm', response.data)
        self.assertEqual(self.client.post('/api/auth/login', json={
            'usuario': 'admin', 'senha': 'incorrect',
        }).status_code, 401)
        self.login()
        self.assertEqual(self.client.get('/api/auth/me').json['perfil'], 'admin')
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        for html in (response.data, self.client.get('/login', follow_redirects=True).data):
            for asset in re.findall(rb'(?:src|href)="(/static/[^\"]+)"', html):
                with self.subTest(asset=asset):
                    with self.client.get(asset.decode()) as asset_response:
                        self.assertEqual(asset_response.status_code, 200)
        for asset in ('/static/css/login.css', '/static/js/login.js'):
            with self.client.get(asset) as asset_response:
                self.assertEqual(asset_response.status_code, 200)
        self.client.post('/api/auth/logout')
        self.assertEqual(self.client.get('/api/auth/me').status_code, 401)

    def test_stock_recipe_finance_and_backup(self):
        self.login()
        response = self.client.post('/api/produtos', json={
            'nome': 'Ingrediente teste', 'codigo': 'TEST001', 'unidade': 'kg',
            'quantidade': 10, 'preco_custo': 4,
        })
        self.assertEqual(response.status_code, 201)
        product_id = response.json['id']
        response = self.client.post('/api/movimentacoes', json={
            'produto_id': product_id, 'tipo': 'saida', 'quantidade': 2,
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.get('/api/produtos').json[0]['quantidade'], 8)
        response = self.client.post('/api/movimentacoes', json={
            'produto_id': product_id, 'tipo': 'saida', 'quantidade': 9,
        })
        self.assertEqual(response.status_code, 400)
        response = self.client.post('/api/fichas', json={
            'nome': 'Receita teste', 'rendimento': 4, 'preco_venda': 6,
            'ingredientes': [{'produto_id': product_id, 'quantidade': 2, 'unidade': 'kg'}],
        })
        self.assertEqual(response.status_code, 201)
        recipe = self.client.get('/api/fichas').json[0]
        self.assertEqual(recipe['custo_total'], 8)
        self.assertEqual(recipe['custo_porcao'], 2)
        response = self.client.post('/api/fin/contas-pagar', json={
            'descricao': 'Compra teste', 'valor': 20, 'vencimento': '2026-10-01',
        })
        self.assertEqual(response.status_code, 201)
        account = self.client.get('/api/fin/contas-pagar').json[0]
        self.assertEqual(self.client.post(f"/api/fin/contas-pagar/{account['id']}/pagar").status_code, 200)
        self.assertEqual(self.client.get('/api/fin/contas-pagar').json[0]['status'], 'pago')
        response = self.client.post('/api/backups')
        self.assertEqual(response.status_code, 201)
        files = list(Path(self.app.config['BACKUP_DIR']).glob('*.db'))
        self.assertEqual(len(files), 1)
        with closing(sqlite3.connect(files[0])) as db, db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('SELECT quantidade FROM produtos').fetchone()[0], 8)
        # Initialization remains repeatable without clearing existing records.
        with self.app.app_context():
            init_db()
        self.assertEqual(len(self.client.get('/api/produtos').json), 1)

    def test_apps_have_isolated_databases(self):
        other = create_app({'TESTING': True, 'SECRET_KEY': 'another-test',
                            'DATABASE': str(Path(self.directory.name) / 'other.db'),
                            'BACKUP_DIR': str(Path(self.directory.name) / 'other-backups')})
        with other.app_context():
            init_db()
        self.login()
        self.client.post('/api/produtos', json={'nome': 'Isolado', 'codigo': 'ISO'})
        with other.test_client() as client:
            with client.session_transaction() as session:
                session.update(usuario_id=1, perfil='admin')
            self.assertEqual(client.get('/api/produtos').json, [])


if __name__ == '__main__':
    unittest.main()
