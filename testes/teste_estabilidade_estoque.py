"""Falhas, repetição e concorrência usam somente bancos temporários."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from sgliras import create_app
from sgliras.banco_dados import init_db


class StockStabilityTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test-only',
                               'DATABASE': str(Path(folder.name) / 'test.db'),
                               'BACKUP_DIR': str(Path(folder.name) / 'backups')})
        with self.app.app_context():
            init_db()
        self.client = self.authorized_client()
        response = self.client.post('/api/produtos', json={
            'nome': 'Teste', 'codigo': 'TEST', 'quantidade': 10,
        })
        self.assertEqual(response.status_code, 201)
        self.pid = response.json['id']

    def authorized_client(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(usuario_id=1, perfil='admin')
        return client

    def movement(self, **changes):
        return {'produto_id': self.pid, 'tipo': 'saida', 'quantidade': 2, **changes}

    def state(self):
        with closing(sqlite3.connect(self.app.config['DATABASE'])) as db, db:
            return (db.execute('SELECT quantidade FROM produtos WHERE id=?', (self.pid,)).fetchone()[0],
                    db.execute('SELECT COUNT(*) FROM movimentacoes').fetchone()[0],
                    db.execute('SELECT COUNT(*) FROM operacoes_idempotentes').fetchone()[0])

    def test_invalid_products_return_400_and_leave_data_unchanged(self):
        for changes in ({'nome': ''}, {'preco_venda': 'abc'}, {'quantidade': -1},
                        {'preco_custo': float('inf')}, {'preco_venda': float('nan')},
                        {'estoque_min': 0.5}, {'categoria_id': 9999}, {'validade': '2026-02-30'},
                        {'quantidade': True}, {'nome': 12}):
            with self.subTest(changes=changes):
                response = self.client.post('/api/produtos', json={
                    'nome': 'Outro', 'codigo': 'OTHER', **changes,
                })
                self.assertEqual(response.status_code, 400)
                self.assertIn('erro', response.json)
        for payload in ({}, [], None):
            self.assertEqual(self.client.post('/api/produtos', json=payload).status_code, 400)
        self.assertEqual(len(self.client.get('/api/produtos').json), 1)

    def test_product_update_validation_and_missing_product(self):
        self.assertEqual(self.client.put(f'/api/produtos/{self.pid}', json={
            'nome': 'Teste', 'codigo': 'TEST', 'preco_venda': 'abc',
        }).status_code, 400)
        self.assertEqual(self.client.put('/api/produtos/9999', json={
            'nome': 'Ausente', 'codigo': 'NONE',
        }).status_code, 404)
        self.assertEqual(self.state(), (10, 0, 0))

    def test_invalid_movements_are_rejected(self):
        for changes in ({'tipo': 'errado'}, {'tipo': 'ajuste', 'quantidade': -1},
                        {'quantidade': 0}, {'quantidade': 'NaN'}, {'quantidade': 'Infinity'},
                        {'produto_id': True}, {'produto_id': '1.5'}, {'produto_id': '1e100'},
                        {'validade': 'tomorrow'}):
            with self.subTest(changes=changes):
                response = self.client.post('/api/movimentacoes', json=self.movement(**changes))
                self.assertEqual(response.status_code, 400)
                self.assertIn('erro', response.json)
        self.assertEqual(self.state(), (10, 0, 0))

    def test_adjustment_zero_and_date_update(self):
        response = self.client.post('/api/movimentacoes', json=self.movement(tipo='ajuste', quantidade=0))
        self.assertEqual(response.status_code, 201)
        response = self.client.post('/api/movimentacoes', json=self.movement(
            tipo='entrada', quantidade=3, validade='2026-11-01'))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.get('/api/produtos').json[0]['validade'], '2026-11-01')
        self.assertEqual(self.state(), (3, 2, 0))

    def test_batch_rolls_back_if_later_product_has_insufficient_stock(self):
        payload = {'operacao_id': 'rollback', 'itens': [self.movement(), self.movement(quantidade=9)]}
        response = self.client.post('/api/movimentacoes/lote', json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.state(), (10, 0, 0))
        payload['itens'][1]['quantidade'] = 1
        self.assertEqual(self.client.post('/api/movimentacoes/lote', json=payload).status_code, 201)
        self.assertEqual(self.state(), (7, 2, 1))

    def test_failed_lookup_or_database_write_rolls_back_entire_batch(self):
        response = self.client.post('/api/movimentacoes/lote', json={
            'operacao_id': 'missing', 'itens': [self.movement(), self.movement(produto_id=9999)]})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.state(), (10, 0, 0))
        # A genuine SQLite failure after the first item must not commit it.
        with closing(sqlite3.connect(self.app.config['DATABASE'])) as db, db:
            db.execute('''CREATE TRIGGER fail_second BEFORE INSERT ON movimentacoes
                          WHEN NEW.observacao='fail' BEGIN SELECT RAISE(ABORT, 'test failure'); END''')
        response = self.client.post('/api/movimentacoes/lote', json={
            'operacao_id': 'write-failed', 'itens': [self.movement(), self.movement(observacao='fail')]})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.state(), (10, 0, 0))

    def test_retry_returns_saved_result_and_rejects_other_payload(self):
        payload = {'operacao_id': 'retry', 'itens': [self.movement()]}
        first = self.client.post('/api/movimentacoes/lote', json=payload)
        second = self.client.post('/api/movimentacoes/lote', json=payload)
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.json, second.json)
        payload['itens'][0]['quantidade'] = 3
        self.assertEqual(self.client.post('/api/movimentacoes/lote', json=payload).status_code, 409)
        self.assertEqual(self.state(), (8, 1, 1))

    def test_concurrent_retries_apply_once_and_concurrent_sales_cannot_overdraw(self):
        barrier = threading.Barrier(2)
        def send(key, amount):
            client = self.authorized_client()
            barrier.wait(timeout=5)
            return client.post('/api/movimentacoes/lote', json={
                'operacao_id': key, 'itens': [self.movement(quantidade=amount)]}).status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(send, 'concurrent', 2) for _ in range(2)]
            self.assertEqual(sorted(f.result() for f in futures), [200, 201])
        self.assertEqual(self.state(), (8, 1, 1))
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(send, f'sale-{i}', 5) for i in range(2)]
            self.assertEqual(sorted(f.result() for f in futures), [201, 400])
        self.assertEqual(self.state(), (3, 2, 2))

    def test_single_movement_can_be_retried_with_key(self):
        payload = self.movement(operacao_id='single-retry')
        self.assertEqual(self.client.post('/api/movimentacoes', json=payload).status_code, 201)
        self.assertEqual(self.client.post('/api/movimentacoes', json=payload).status_code, 200)
        self.assertEqual(self.state(), (8, 1, 1))

    def test_product_status_rejects_ambiguous_values(self):
        for value in ('0', 'false', [], {}, 2, None):
            self.assertEqual(self.client.put(f'/api/produtos/{self.pid}/ativo',
                                            json={'ativo': value}).status_code, 400)
        self.assertEqual(self.client.get('/api/produtos').json[0]['ativo'], 1)
        self.assertEqual(self.client.put(f'/api/produtos/{self.pid}/ativo',
                                        json={'ativo': False}).status_code, 200)
        self.assertEqual(self.client.get('/api/produtos').json[0]['ativo'], 0)

    def test_audit_failure_rolls_back_product_deletion(self):
        with closing(sqlite3.connect(self.app.config['DATABASE'])) as db, db:
            db.execute('''CREATE TRIGGER fail_audit BEFORE INSERT ON log_auditoria
                          BEGIN SELECT RAISE(ABORT, 'test failure'); END''')
        self.assertEqual(self.client.delete(f'/api/produtos/{self.pid}').status_code, 409)
        self.assertEqual(len(self.client.get('/api/produtos').json), 1)


if __name__ == '__main__':
    unittest.main()
