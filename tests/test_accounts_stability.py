"""Contas financeiras: validação, parcelas atômicas e vínculos preservados."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from sgliras import create_app
from sgliras.database import init_db
from sgliras.routes import finance_accounts


class AccountsStabilityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = str(Path(self.directory.name) / "test.db")
        self.app = create_app({
            "TESTING": True, "SECRET_KEY": "test-only",
            "DATABASE": self.database,
            "BACKUP_DIR": str(Path(self.directory.name) / "backups"),
        })
        with self.app.app_context():
            init_db()
        self.client = self.authenticated_client()

    def authenticated_client(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(usuario_id=1, perfil="admin", usuario="admin")
        return client

    def account(self, **changes):
        return {"descricao": "Compra teste", "valor": 20,
                "vencimento": "2026-10-01", **changes}

    def rows(self, table="fin_contas_pagar"):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id")]

    def test_invalid_accounts_return_400_without_writes(self):
        invalid = [None, [], {}, self.account(descricao=" "), self.account(descricao=3),
                   self.account(valor="abc"), self.account(valor=0), self.account(valor=-2),
                   self.account(valor=True), self.account(valor="NaN"),
                   self.account(valor="Infinity"), self.account(vencimento="2026-02-30"),
                   self.account(vencimento="20261001"), self.account(categoria="inexistente"),
                   self.account(categoria=[]), self.account(fornecedor_id=999),
                   self.account(fornecedor_id="abc"), self.account(fornecedor_id=0),
                   self.account(observacao={})]
        for payload in invalid:
            with self.subTest(payload=payload):
                response = self.client.post("/api/fin/contas-pagar", json=payload)
                self.assertEqual(response.status_code, 400, response.get_json())
                self.assertIn("erro", response.get_json())
        self.assertEqual(self.rows(), [])
        for payload in [self.account(valor="nan"), self.account(categoria="Fornecedor"),
                        self.account(vencimento="ontem")]:
            response = self.client.post("/api/fin/contas-receber", json=payload)
            self.assertEqual(response.status_code, 400, response.get_json())
        self.assertEqual(self.rows("fin_contas_receber"), [])

    def test_supplier_and_valid_receivable(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            supplier_id = db.execute(
                "INSERT INTO fornecedores (nome,criado_em) VALUES ('Fornecedor teste','agora')"
            ).lastrowid
        response = self.client.post("/api/fin/contas-pagar", json=self.account(fornecedor_id=str(supplier_id)))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.rows()[0]["fornecedor_id"], supplier_id)
        response = self.client.post("/api/fin/contas-receber", json=self.account(categoria="Venda"))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.rows("fin_contas_receber")[0]["valor"], 20)
        self.assertEqual(self.client.get("/api/fin/contas-pagar?fornecedor_id=abc").status_code, 400)

    def test_edit_rejects_invalid_data_and_missing_account(self):
        self.client.post("/api/fin/contas-pagar", json=self.account())
        account_id = self.rows()[0]["id"]
        before = self.rows()
        response = self.client.put(f"/api/fin/contas-pagar/{account_id}", json=self.account(valor="bad"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.rows(), before)
        response = self.client.put("/api/fin/contas-pagar/999", json=self.account())
        self.assertEqual(response.status_code, 404)

    def test_category_rename_is_atomic_with_accounts_and_rejects_invalid_names(self):
        self.client.post("/api/fin/contas-pagar", json=self.account())
        categories = self.client.get("/api/fin/categorias-pagar").get_json()
        category_id = next(category["id"] for category in categories if category["nome"] == "Outros")
        url = f"/api/fin/categorias-pagar/{category_id}"
        response = self.client.put(url, json={"nome": "Fornecedor"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.rows()[0]["categoria"], "Outros")
        response = self.client.put(url, json={"nome": "Diversos"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.rows()[0]["categoria"], "Diversos")
        self.assertEqual(self.client.delete(url).status_code, 400)
        self.assertEqual(self.client.put(url, json={"nome": []}).status_code, 400)
        self.assertEqual(self.client.post("/api/fin/categorias-pagar", json={"nome": []}).status_code, 400)
        self.assertEqual(self.client.put("/api/fin/categorias-pagar/999", json={"nome": "Nova"}).status_code, 404)

    def test_batch_validates_every_installment_before_writing(self):
        for invalid_item in [self.account(valor=-10), self.account(fornecedor_id=999), []]:
            response = self.client.post("/api/fin/contas-pagar/lote", json={
                "operacao_id": "parcelas-invalidas", "itens": [self.account(), invalid_item],
            })
            self.assertEqual(response.status_code, 400, response.get_json())
            self.assertEqual(self.rows(), [])
        for payload in [{"itens": [self.account()]}, {"operacao_id": "vazia", "itens": []},
                        {"operacao_id": "objeto", "itens": {"descricao": "erro"}}]:
            self.assertEqual(self.client.post("/api/fin/contas-pagar/lote", json=payload).status_code, 400)

    def test_batch_retry_reuses_ids_and_conflict_preserves_original(self):
        payload = {"operacao_id": "parcelamento-1", "itens": [
            self.account(descricao="Compra 1/2"), self.account(descricao="Compra 2/2"),
        ]}
        first = self.client.post("/api/fin/contas-pagar/lote", json=payload)
        retry = self.client.post("/api/fin/contas-pagar/lote", json=payload)
        self.assertEqual(first.status_code, 201, first.get_json())
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(first.get_json(), retry.get_json())
        self.assertEqual(first.get_json()["criadas"], 2)
        self.assertEqual([row["id"] for row in self.rows()], first.get_json()["ids"])
        changed = {**payload, "itens": [self.account(valor=99)]}
        response = self.client.post("/api/fin/contas-pagar/lote", json=changed)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(self.rows()), 2)

    def test_batch_sql_failure_rolls_back_items_and_operation_key(self):
        original_insert = finance_accounts._inserir_conta_pagar
        calls = 0

        def fail_second(db, dados):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise sqlite3.OperationalError("falha simulada após primeira parcela")
            return original_insert(db, dados)

        payload = {"operacao_id": "retry-apos-falha", "itens": [self.account(), self.account()]}
        with patch.object(finance_accounts, "_inserir_conta_pagar", side_effect=fail_second):
            with self.assertLogs(self.app.logger, level="ERROR"):
                response = self.client.post("/api/fin/contas-pagar/lote", json=payload)
            self.assertEqual(response.status_code, 500)
        self.assertEqual(self.rows(), [])
        retry = self.client.post("/api/fin/contas-pagar/lote", json=payload)
        self.assertEqual(retry.status_code, 201, retry.get_json())
        self.assertEqual(len(self.rows()), 2)

    def test_concurrent_batch_retries_do_not_duplicate_installments(self):
        payload = {"operacao_id": "retry-simultaneo", "itens": [self.account(), self.account()]}

        def submit(_):
            response = self.authenticated_client().post("/api/fin/contas-pagar/lote", json=payload)
            return response.status_code, response.get_json()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))
        self.assertEqual(sorted(status for status, _ in results), [200, 201])
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(len(self.rows()), 2)

    def linked_delivery(self):
        self.client.post("/api/fin/contas-pagar", json=self.account())
        account_id = self.rows()[0]["id"]
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("""INSERT INTO fin_massa_entregas
                          (data,valor_total,conta_pagar_id,usuario_id,criado_em)
                          VALUES ('2026-10-01',20,?,1,'agora')""", (account_id,))
        return account_id

    def test_delivery_account_cannot_be_edited_or_deleted(self):
        account_id = self.linked_delivery()
        before = self.rows()
        response = self.client.put(f"/api/fin/contas-pagar/{account_id}", json=self.account(valor=99))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.delete(f"/api/fin/contas-pagar/{account_id}").status_code, 409)
        self.assertEqual(self.rows(), before)
        self.assertEqual(len(self.rows("fin_massa_entregas")), 1)

    def test_generic_payment_updates_delivery_once_and_preserves_timestamp(self):
        account_id = self.linked_delivery()
        url = f"/api/fin/contas-pagar/{account_id}/pagar"
        self.assertEqual(self.client.post(url).status_code, 200)
        paid_at = self.rows()[0]["pago_em"]
        self.assertIsNotNone(paid_at)
        self.assertEqual(self.rows()[0]["status"], "pago")
        self.assertEqual(self.rows("fin_massa_entregas")[0]["pago"], 1)
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertEqual(self.rows()[0]["pago_em"], paid_at)

    def test_delivery_sync_failure_rolls_back_generic_payment(self):
        account_id = self.linked_delivery()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("""CREATE TRIGGER simulate_delivery_failure BEFORE UPDATE OF pago
                          ON fin_massa_entregas BEGIN
                          SELECT RAISE(ABORT, 'falha simulada'); END""")
        with self.assertLogs(self.app.logger, level="WARNING"):
            response = self.client.post(f"/api/fin/contas-pagar/{account_id}/pagar")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.rows()[0]["status"], "aberto")
        self.assertIsNone(self.rows()[0]["pago_em"])
        self.assertEqual(self.rows("fin_massa_entregas")[0]["pago"], 0)

    def test_bread_generated_account_is_protected(self):
        self.client.post("/api/fin/contas-pagar", json=self.account(
            descricao="Pães — 2026-10-01", categoria="Fornecedor"))
        account_id = self.rows()[0]["id"]
        self.assertEqual(self.client.delete(f"/api/fin/contas-pagar/{account_id}").status_code, 409)
        self.assertEqual(self.client.put(f"/api/fin/contas-pagar/{account_id}", json=self.account()).status_code, 409)
        self.assertEqual(len(self.rows()), 1)
        # A categoria pode ter sido renomeada, sem perder o vínculo com pães.
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("UPDATE fin_contas_pagar SET categoria='Compras' WHERE id=?", (account_id,))
        self.assertEqual(self.client.delete(f"/api/fin/contas-pagar/{account_id}").status_code, 409)


if __name__ == "__main__":
    unittest.main()
