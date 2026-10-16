"""Integridade financeira em bancos descartáveis, sem acessar estoque.db."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import unittest

from sgliras import create_app
from sgliras.database import init_db


class FinanceStabilityTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = str(Path(directory.name) / 'finance.db')
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'finance-test-only',
                               'DATABASE': self.database,
                               'BACKUP_DIR': str(Path(directory.name) / 'backups')})
        with self.app.app_context():
            init_db()
        self.client = self.authenticated_client()

    def authenticated_client(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(usuario_id=1, usuario='admin', perfil='admin', nome='Administrador')
        return client

    def rows(self, sql, params=()):
        with sqlite3.connect(self.database) as db:
            return db.execute(sql, params).fetchall()

    def execute(self, sql, params=()):
        with sqlite3.connect(self.database) as db:
            db.execute(sql, params)

    def snapshot(self):
        return {table: self.rows(f'SELECT * FROM {table} ORDER BY id')
                for table in ('fin_contas_pagar', 'fin_paes_pagamento', 'fin_massa_entregas')}

    def delivery(self, amount=100, day='2026-10-01'):
        response = self.client.post('/api/fin/massa-entregas', json={
            'data': day, 'qtd_p': 10, 'valor_total': amount, 'observacao': 'Lote teste',
        })
        self.assertEqual(response.status_code, 201, response.json)
        return response.json['entrega_id'], response.json['conta_pagar_id']

    def test_bread_repeat_and_overlap_leave_database_unchanged(self):
        payment = {'datas': ['2026-10-01', '2026-10-02'], 'valor': 40}
        self.assertEqual(self.client.post('/api/fin/paes-pagamento', json=payment).status_code, 201)
        before = self.snapshot()
        for value in (payment, {'datas': ['2026-10-02', '2026-10-03'], 'valor': 40}):
            with self.subTest(value=value):
                self.assertEqual(self.client.post('/api/fin/paes-pagamento', json=value).status_code, 409)
                self.assertEqual(self.snapshot(), before)

    def test_concurrent_bread_payments_create_one_history_and_account(self):
        barrier = Barrier(2)

        def pay():
            client = self.authenticated_client()
            barrier.wait(timeout=10)
            return client.post('/api/fin/paes-pagamento', json={
                'datas': ['2026-10-01'], 'valor': 20,
            }).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: pay(), range(2)))
        self.assertEqual(sorted(results), [201, 409])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM fin_paes_pagamento'), [(1,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM fin_contas_pagar'), [(1,)])

    def test_bread_reversal_preserves_accounts_and_allows_new_payment(self):
        payment = {'datas': ['2026-10-01', '2026-10-02', '2026-10-03'], 'valor': 10.01}
        self.assertEqual(self.client.post('/api/fin/paes-pagamento', json=payment).status_code, 201)
        accounts = self.rows('SELECT id,valor FROM fin_contas_pagar ORDER BY id')
        self.assertEqual([row[1] for row in accounts], [3.34, 3.34, 3.33])
        pid = self.rows('SELECT id FROM fin_paes_pagamento')[0][0]
        response = self.client.delete(f'/api/fin/paes-pagamento/{pid}')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.rows('SELECT id,valor FROM fin_contas_pagar ORDER BY id'), accounts)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM fin_contas_pagar WHERE status='aberto' AND pago_em IS NULL"), [(3,)])
        self.assertEqual(self.client.post('/api/fin/paes-pagamento', json=payment).status_code, 201)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM fin_paes_pagamento'), [(1,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM fin_contas_pagar'), [(3,)])

    def test_bread_history_failure_rolls_back_accounts(self):
        self.execute("""CREATE TRIGGER fail_bread_history BEFORE INSERT ON fin_paes_pagamento
                        BEGIN SELECT RAISE(ABORT,'Falha simulada'); END""")
        before = self.snapshot()
        response = self.client.post('/api/fin/paes-pagamento', json={
            'datas': ['2026-10-01', '2026-10-02'], 'valor': 40,
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.snapshot(), before)

    def test_bread_launch_is_idempotent_and_preserves_account_values(self):
        days = {'dias': [{'data': '2026-10-01', 'valor': 20, 'paes_qtd': 10, 'preco': 2}]}
        self.assertEqual(self.client.post('/api/fin/paes-lancar-contas', json=days).json['criadas'], 1)
        self.assertEqual(self.client.post('/api/fin/paes-lancar-contas', json=days).json['criadas'], 0)
        before = self.snapshot()
        self.assertEqual(self.client.post('/api/fin/paes-pagamento', json={
            'datas': ['2026-10-01'], 'valor': 25,
        }).status_code, 409)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.client.post('/api/fin/paes-pagamento', json={
            'datas': ['2026-10-01'], 'valor': 20,
        }).status_code, 201)
        self.assertEqual(self.rows('SELECT valor,status FROM fin_contas_pagar'), [(20, 'pago')])

    def test_bread_account_paid_elsewhere_cannot_be_paid_again(self):
        self.client.post('/api/fin/paes-lancar-contas', json={
            'dias': [{'data': '2026-10-01', 'valor': 20}],
        })
        self.execute("UPDATE fin_contas_pagar SET status='pago',pago_em='2026-10-02'")
        before = self.snapshot()
        response = self.client.post('/api/fin/paes-pagamento', json={
            'datas': ['2026-10-01'], 'valor': 20,
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.snapshot(), before)

    def test_delivery_edit_synchronizes_account_and_preserves_omitted_fields(self):
        eid, cid = self.delivery()
        response = self.client.put(f'/api/fin/massa-entregas/{eid}', json={
            'data': '2026-10-02', 'valor_total': 150,
        })
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.rows('SELECT data,qtd_p,valor_total FROM fin_massa_entregas'),
                         [('2026-10-02', 10, 150)])
        self.assertEqual(self.rows('SELECT valor,vencimento,descricao FROM fin_contas_pagar WHERE id=?', (cid,)),
                         [(150, '2026-10-02', 'Massas — 2026-10-02')])

    def test_delete_unpaid_delivery_removes_account_with_foreign_keys_enabled(self):
        eid, cid = self.delivery()
        response = self.client.delete(f'/api/fin/massa-entregas/{eid}')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.rows('SELECT id FROM fin_massa_entregas'), [])
        self.assertEqual(self.rows('SELECT id FROM fin_contas_pagar'), [])
        self.assertEqual(self.rows('PRAGMA foreign_key_check'), [])

    def test_paid_delivery_rejects_edit_delete_and_repayment(self):
        eid, cid = self.delivery()
        response = self.client.post('/api/fin/massa-pagamento', json={'ids': [eid]})
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(response.json['valor_total'], 100)
        self.assertEqual(self.rows('SELECT pago FROM fin_massa_entregas'), [(1,)])
        self.assertEqual(self.rows('SELECT valor,status FROM fin_contas_pagar'), [(100, 'pago')])
        before = self.snapshot()
        for method, url, payload in (
            ('put', f'/api/fin/massa-entregas/{eid}', {'valor_total': 150}),
            ('delete', f'/api/fin/massa-entregas/{eid}', None),
            ('post', '/api/fin/massa-pagamento', {'ids': [eid]}),
        ):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url, json=payload)
                self.assertEqual(response.status_code, 409, response.json)
                self.assertEqual(self.snapshot(), before)

    def test_paid_account_also_blocks_delivery_changes(self):
        eid, cid = self.delivery()
        self.execute("UPDATE fin_contas_pagar SET status='pago' WHERE id=?", (cid,))
        before = self.snapshot()
        self.assertEqual(self.client.put(f'/api/fin/massa-entregas/{eid}', json={'valor_total': 150}).status_code, 409)
        self.assertEqual(self.client.delete(f'/api/fin/massa-entregas/{eid}').status_code, 409)
        self.assertEqual(self.snapshot(), before)

    def test_dough_payment_missing_or_paid_ids_does_not_partially_pay(self):
        first, _ = self.delivery()
        second, _ = self.delivery()
        before = self.snapshot()
        response = self.client.post('/api/fin/massa-pagamento', json={'ids': [first, 9999]})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.client.post('/api/fin/massa-pagamento', json={'ids': [first]}).status_code, 201)
        before = self.snapshot()
        response = self.client.post('/api/fin/massa-pagamento', json={'ids': [first, second]})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.snapshot(), before)

    def test_dough_payment_failure_rolls_back_the_entire_selection(self):
        first, _ = self.delivery()
        second, second_account = self.delivery()
        self.execute(f"""CREATE TRIGGER fail_second_payment BEFORE UPDATE OF status ON fin_contas_pagar
                          WHEN NEW.id={second_account} AND NEW.status='pago'
                          BEGIN SELECT RAISE(ABORT,'Falha simulada'); END""")
        before = self.snapshot()
        response = self.client.post('/api/fin/massa-pagamento', json={'ids': [first, second]})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.snapshot(), before)

    def test_delivery_edit_failure_rolls_back_both_values(self):
        eid, cid = self.delivery()
        self.execute("""CREATE TRIGGER fail_account_edit BEFORE UPDATE OF valor ON fin_contas_pagar
                        BEGIN SELECT RAISE(ABORT,'Falha simulada'); END""")
        before = self.snapshot()
        self.assertEqual(self.client.put(f'/api/fin/massa-entregas/{eid}', json={'valor_total': 150}).status_code, 409)
        self.assertEqual(self.snapshot(), before)

    def test_legacy_delivery_without_account_recovers_link_when_paid(self):
        self.execute("""INSERT INTO fin_massa_entregas (data,valor_total,usuario_id,criado_em)
                        VALUES ('2026-10-01',100,1,'2026-10-01')""")
        eid = self.rows('SELECT id FROM fin_massa_entregas')[0][0]
        response = self.client.post('/api/fin/massa-pagamento', json={'ids': [eid]})
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(self.rows("""SELECT e.pago,c.valor,c.status FROM fin_massa_entregas e
                                      JOIN fin_contas_pagar c ON c.id=e.conta_pagar_id"""), [(1, 100, 'pago')])

    def test_prices_for_same_date_are_updated_without_duplicates(self):
        for endpoint, field in (('/api/fin/preco-pao', 'preco'), ('/api/fin/massa-precos', 'preco_p')):
            for amount in (2, 3):
                response = self.client.post(endpoint, json={'vigente_de': '2026-10-01', field: amount})
                self.assertEqual(response.status_code, 201, response.json)
            response = self.client.get(endpoint)
            self.assertEqual(len(response.json), 1)
            self.assertEqual(response.json[0][field], 3)

    def test_invalid_payloads_are_rejected_without_writes(self):
        cases = [
            ('/api/fin/paes-pagamento', {'datas': '2026-10-01', 'valor': 20}),
            ('/api/fin/paes-pagamento', {'datas': ['2026-02-30'], 'valor': 20}),
            ('/api/fin/paes-pagamento', {'datas': ['2026-10-01'] * 2, 'valor': 20}),
            ('/api/fin/paes-pagamento', {'datas': ['2026-10-01'], 'valor': -1}),
            ('/api/fin/paes-pagamento', {'datas': ['2026-10-01'], 'valor': 'NaN'}),
            ('/api/fin/paes-lancar-contas', {'dias': [None]}),
            ('/api/fin/massa-entregas', {'data': '2026-10-01', 'valor_total': 'inf'}),
            ('/api/fin/massa-entregas', {'data': '2026-10-01', 'qtd_p': 0.5}),
            ('/api/fin/massa-entregas', {'data': '2026-10-01', 'qtd_p': -1}),
            ('/api/fin/massa-entregas', {'data': '2026-10-01', 'observacao': []}),
            ('/api/fin/massa-pagamento', {'ids': [1, 1]}),
            ('/api/fin/massa-pagamento', {'ids': [0]}),
            ('/api/fin/massa-pagamento', {'ids': [True]}),
            ('/api/fin/massa-pagamento', {'ids': [0.5]}),
            ('/api/fin/preco-pao', {'vigente_de': 'wrong', 'preco': 2}),
            ('/api/fin/massa-precos', {'vigente_de': '2026-10-01', 'preco_p': -1}),
        ]
        before = self.snapshot()
        for endpoint, payload in cases:
            with self.subTest(endpoint=endpoint, payload=payload):
                response = self.client.post(endpoint, json=payload)
                self.assertEqual(response.status_code, 400, response.json)
                self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
