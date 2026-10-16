"""Validação, atomicidade e concorrência de inventário em bancos temporários."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from sgliras import create_app
from sgliras.banco_dados import init_db


class InventoryStabilityTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.app = create_app({
            'TESTING': True, 'SECRET_KEY': 'inventory-tests',
            'DATABASE': str(Path(folder.name) / 'inventory.db'),
            'BACKUP_DIR': str(Path(folder.name) / 'backups'),
        })
        with self.app.app_context():
            init_db()
        with closing(sqlite3.connect(self.app.config['DATABASE'])) as db, db:
            self.pid = db.execute('''
                INSERT INTO produtos (nome,codigo,quantidade,criado_em)
                VALUES ('Primeiro','INV1',10,'2026-10-01')
            ''').lastrowid
            self.other_pid = db.execute('''
                INSERT INTO produtos (nome,codigo,quantidade,criado_em)
                VALUES ('Segundo','INV2',20,'2026-10-01')
            ''').lastrowid
        self.client = self.authorized_client()

    def authorized_client(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(usuario_id=1, perfil='admin')
        return client

    def create_inventory(self):
        response = self.client.post('/api/inventarios', json={'titulo': 'Contagem teste'})
        self.assertEqual(response.status_code, 201)
        return response.json['id']

    def item(self, count=6, pid=None, **changes):
        return {'produto_id': self.pid if pid is None else pid,
                'quantidade_contada': count, **changes}

    def snapshot(self):
        with closing(sqlite3.connect(self.app.config['DATABASE'])) as db, db:
            return {
                'products': db.execute('SELECT id,quantidade FROM produtos ORDER BY id').fetchall(),
                'items': db.execute('''SELECT produto_id,quantidade_contada,diferenca,observacao
                                      FROM inventario_itens ORDER BY id''').fetchall(),
                'inventories': db.execute('SELECT status,finalizado_em FROM inventarios ORDER BY id').fetchall(),
                'movements': db.execute('SELECT COUNT(*) FROM movimentacoes').fetchone()[0],
            }

    def test_invalid_counts_rejected_without_partial_save_or_stock_change(self):
        inv = self.create_inventory()
        before = self.snapshot()
        for count in (-1, 'abc', 'NaN', 'Infinity', float('inf'), float('nan'), True, [], {}):
            payload = {'itens': [self.item(), self.item(count, pid=self.other_pid)]}
            for url, method in ((f'/api/inventarios/{inv}/itens', self.client.put),
                                ('/api/inventario/aplicar', self.client.post)):
                with self.subTest(url=url, count=count):
                    response = method(url, json=payload)
                    self.assertEqual(response.status_code, 400)
                    self.assertIn('erro', response.json)
                    self.assertEqual(self.snapshot(), before)

    def test_inventory_creation_validates_metadata_and_only_one_can_be_open(self):
        for payload in (None, [], {'titulo': []}, {'categoria': 1}, {'observacao': {}}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post('/api/inventarios', json=payload).status_code, 400)
                self.assertEqual(self.snapshot()['inventories'], [])
        barrier = threading.Barrier(2)

        def create():
            client = self.authorized_client()
            barrier.wait(timeout=5)
            return client.post('/api/inventarios', json={}).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(create) for _ in range(2)]
            self.assertEqual(sorted(f.result() for f in futures), [201, 400])
        self.assertEqual(len(self.snapshot()['inventories']), 1)

    def test_malformed_lists_and_unknown_or_duplicate_products_rejected(self):
        inv = self.create_inventory()
        before = self.snapshot()
        payloads = [None, [], {}, {'itens': {}}, {'itens': [None]},
                    {'itens': [self.item(), self.item(pid=99999)]},
                    {'itens': [self.item(), self.item()]},
                    {'itens': [self.item(pid=True)]},
                    {'itens': [self.item(pid=10**100)]},
                    {'itens': [self.item(observacao=123)]}]
        for payload in payloads:
            for url, method in ((f'/api/inventarios/{inv}/itens', self.client.put),
                                ('/api/inventario/aplicar', self.client.post)):
                with self.subTest(url=url, payload=payload):
                    self.assertEqual(method(url, json=payload).status_code, 400)
                    self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.client.post('/api/inventario/aplicar', json={'itens': []}).status_code, 400)
        self.assertEqual(self.client.put(f'/api/inventarios/{inv}/itens', json={
            'itens': [self.item(None, pid=99999)],
        }).status_code, 400)

    def test_partial_count_can_skip_uncounted_items_and_zero_is_valid(self):
        inv = self.create_inventory()
        response = self.client.put(f'/api/inventarios/{inv}/itens', json={
            'itens': [self.item(0), self.item(None, pid=self.other_pid)],
        })
        self.assertEqual(response.status_code, 200)
        response = self.client.post(f'/api/inventarios/{inv}/finalizar')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['ajustados'], 1)
        self.assertEqual(self.snapshot()['products'], [(self.pid, 0), (self.other_pid, 20)])
        self.assertEqual(response.json['abaixo_minimo'], [{'produto_id': self.pid, 'nome': 'Primeiro'}])

    def test_finalization_applies_absolute_count_even_if_equal_to_original_stock(self):
        inv = self.create_inventory()
        self.assertEqual(self.client.put(f'/api/inventarios/{inv}/itens', json={
            'itens': [self.item(10)],
        }).status_code, 200)
        # Uma saída posterior à abertura não deve tornar a contagem relativa.
        with closing(sqlite3.connect(self.app.config['DATABASE'])) as db, db:
            db.execute('UPDATE produtos SET quantidade=8 WHERE id=?', (self.pid,))
        response = self.client.post(f'/api/inventarios/{inv}/finalizar')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['ajustados'], 1)
        self.assertEqual(self.snapshot()['products'][0], (self.pid, 10))

    def test_finalized_inventory_cannot_be_saved_or_applied_again(self):
        inv = self.create_inventory()
        self.client.put(f'/api/inventarios/{inv}/itens', json={'itens': [self.item()]})
        self.assertEqual(self.client.post(f'/api/inventarios/{inv}/finalizar').status_code, 200)
        # Uma repetição da finalização não pode sobrescrever movimentos novos.
        with closing(sqlite3.connect(self.app.config['DATABASE'])) as db, db:
            db.execute('UPDATE produtos SET quantidade=5 WHERE id=?', (self.pid,))
        before = self.snapshot()
        self.assertEqual(self.client.post(f'/api/inventarios/{inv}/finalizar').status_code, 400)
        self.assertEqual(self.client.put(f'/api/inventarios/{inv}/itens', json={
            'itens': [self.item(2)],
        }).status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_saved_legacy_invalid_count_prevents_entire_finalization(self):
        inv = self.create_inventory()
        with closing(sqlite3.connect(self.app.config['DATABASE'])) as db, db:
            db.execute('''UPDATE inventario_itens SET quantidade_contada=6,diferenca=-4
                          WHERE produto_id=?''', (self.pid,))
            db.execute('''UPDATE inventario_itens SET quantidade_contada=-1,diferenca=-21
                          WHERE produto_id=?''', (self.other_pid,))
        before = self.snapshot()
        self.assertEqual(self.client.post(f'/api/inventarios/{inv}/finalizar').status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_database_failure_rolls_back_stock_movements_and_finalization(self):
        inv = self.create_inventory()
        self.client.put(f'/api/inventarios/{inv}/itens', json={
            'itens': [self.item(), self.item(12, pid=self.other_pid)],
        })
        with closing(sqlite3.connect(self.app.config['DATABASE'])) as db, db:
            db.execute(f'''CREATE TRIGGER fail_count BEFORE UPDATE OF quantidade ON produtos
                           WHEN NEW.id={self.other_pid}
                           BEGIN SELECT RAISE(ABORT, 'test failure'); END''')
        before = self.snapshot()
        self.assertEqual(self.client.post(f'/api/inventarios/{inv}/finalizar').status_code, 409)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.client.post('/api/inventario/aplicar', json={
            'itens': [self.item(), self.item(12, pid=self.other_pid)],
        }).status_code, 409)
        self.assertEqual(self.snapshot(), before)

    def test_two_concurrent_finalizations_apply_once(self):
        inv = self.create_inventory()
        self.client.put(f'/api/inventarios/{inv}/itens', json={'itens': [self.item()]})
        barrier = threading.Barrier(2)

        def finalize():
            client = self.authorized_client()
            barrier.wait(timeout=5)
            return client.post(f'/api/inventarios/{inv}/finalizar').status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(finalize) for _ in range(2)]
            self.assertEqual(sorted(f.result() for f in futures), [200, 400])
        self.assertEqual(self.snapshot()['products'][0], (self.pid, 6))
        self.assertEqual(self.snapshot()['movements'], 1)

    def test_concurrent_save_and_finalize_preserve_applied_count(self):
        inv = self.create_inventory()
        self.client.put(f'/api/inventarios/{inv}/itens', json={'itens': [self.item()]})
        barrier = threading.Barrier(2)

        def send(save):
            client = self.authorized_client()
            barrier.wait(timeout=5)
            if save:
                return client.put(f'/api/inventarios/{inv}/itens', json={
                    'itens': [self.item(3)],
                }).status_code
            return client.post(f'/api/inventarios/{inv}/finalizar').status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            save = executor.submit(send, True)
            finish = executor.submit(send, False)
            self.assertIn(save.result(), (200, 400))
            self.assertEqual(finish.result(), 200)
        state = self.snapshot()
        self.assertIn(state['products'][0][1], (3, 6))
        self.assertEqual(state['products'][0][1], state['items'][0][1])
        self.assertEqual(state['movements'], 1)
        self.assertEqual(state['inventories'][0][0], 'finalizado')


if __name__ == '__main__':
    unittest.main()
