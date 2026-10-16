"""Sessões atualizadas pelo banco e migrações sem perda de dados."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import unittest

from sgliras import create_app
from sgliras.banco_dados import get_db, init_db


class SessionsAndMigrationsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "test.db"
        self.app = create_app({
            "TESTING": True, "SECRET_KEY": "session-tests-only",
            "DATABASE": str(self.path),
            "BACKUP_DIR": str(Path(directory.name) / "backups"),
        })
        self.initialize()
        self.client = self.app.test_client()

    def initialize(self):
        with self.app.app_context():
            init_db()

    def execute(self, sql, parameters=()):
        with closing(sqlite3.connect(self.app.config["DATABASE"])) as db:
            result = db.execute(sql, parameters).fetchall()
            db.commit()
            return result

    def login(self):
        response = self.client.post("/api/auth/login", json={
            "usuario": "admin", "senha": "admin123",
        })
        self.assertEqual(response.status_code, 200)

    def assert_session_cleared(self):
        with self.client.session_transaction() as session:
            self.assertNotIn("usuario_id", session)
            self.assertNotIn("perfil", session)

    def test_disabled_user_loses_existing_session(self):
        self.login()
        self.execute("UPDATE usuarios SET ativo=0 WHERE usuario='admin'")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assert_session_cleared()
        self.assertEqual(self.client.get("/").headers["Location"], "/login")

    def test_removed_user_loses_existing_session(self):
        self.login()
        self.execute("DELETE FROM usuarios WHERE usuario='admin'")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assert_session_cleared()

    def test_current_role_name_and_login_replace_cached_values(self):
        self.login()
        self.execute("UPDATE usuarios SET perfil='caixa',nome='Caixa atual',usuario='novo-login' WHERE id=1")
        self.assertEqual(self.client.get("/api/usuarios").status_code, 403)
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["perfil"], "caixa")
        self.assertEqual(response.json["nome"], "Caixa atual")
        self.assertEqual(response.json["usuario"], "novo-login")
        self.assertNotIn("usuarios", response.json["permissoes"])
        self.execute("UPDATE usuarios SET perfil='admin' WHERE id=1")
        self.assertEqual(self.client.get("/api/usuarios").status_code, 200)

    def test_unknown_profile_invalidates_session_and_cannot_login(self):
        self.login()
        self.execute("UPDATE usuarios SET perfil='perfil-inexistente' WHERE id=1")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assert_session_cleared()
        response = self.client.post("/api/auth/login", json={
            "usuario": "admin", "senha": "admin123",
        })
        self.assertEqual(response.status_code, 401)
        self.assert_session_cleared()

    def test_invalid_session_identifiers_are_rejected(self):
        for identifier in (None, "1", [], {}, True, -1, 9999):
            with self.subTest(identifier=identifier):
                with self.client.session_transaction() as session:
                    session.update(usuario_id=identifier, perfil="admin")
                self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
                self.assert_session_cleared()

    def test_bad_login_payload_returns_validation_error(self):
        for payload in ([], "admin", 1, {}, {"usuario": [], "senha": "senha"},
                        {"usuario": "admin", "senha": 123}):
            with self.subTest(payload=payload):
                response = self.client.post("/api/auth/login", json=payload)
                self.assertEqual(response.status_code, 400)
                self.assert_session_cleared()

    def test_password_change_validates_payload_and_preserves_old_password_on_error(self):
        self.login()
        for payload in ([], {}, {"senha_atual": "admin123", "senha_nova": 123},
                        {"senha_atual": "admin123", "senha_nova": ""},
                        {"senha_atual": "incorreta", "senha_nova": "nova-senha"}):
            with self.subTest(payload=payload):
                response = self.client.put("/api/auth/senha", json=payload)
                self.assertEqual(response.status_code, 400)
        self.login()
        response = self.client.put("/api/auth/senha", json={
            "senha_atual": "admin123", "senha_nova": "nova-senha",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post("/api/auth/login", json={
            "usuario": "admin", "senha": "admin123",
        }).status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", json={
            "usuario": "admin", "senha": "nova-senha",
        }).status_code, 200)

    def test_malformed_stored_hash_does_not_crash_login(self):
        self.execute("UPDATE usuarios SET senha='scrypt:invalido' WHERE id=1")
        response = self.client.post("/api/auth/login", json={
            "usuario": "admin", "senha": "admin123",
        })
        self.assertEqual(response.status_code, 401)
        self.assert_session_cleared()

    def test_valid_legacy_password_is_upgraded(self):
        legacy_hash = hashlib.sha256(b"admin123").hexdigest()
        self.execute("UPDATE usuarios SET senha=? WHERE id=1", (legacy_hash,))
        self.login()
        stored_hash = self.execute("SELECT senha FROM usuarios WHERE id=1")[0][0]
        self.assertNotEqual(stored_hash, legacy_hash)
        self.assertTrue(stored_hash.startswith(("scrypt:", "pbkdf2:")))

    def test_context_teardown_closes_forgotten_connections_and_rolls_back(self):
        with self.app.app_context():
            already_closed = get_db()
            already_closed.close()
            forgotten = get_db()
            forgotten.execute("INSERT INTO categorias (nome) VALUES ('Não confirmado')")
        with self.assertRaises(sqlite3.ProgrammingError):
            forgotten.execute("SELECT 1")
        self.assertEqual(self.execute("SELECT id FROM categorias WHERE nome='Não confirmado'"), [])

    def test_user_creation_validates_fields_before_writing(self):
        self.login()
        valid = {"nome": "Novo usuário", "usuario": "novo", "senha": "senha-teste", "perfil": "caixa"}
        invalid = [[], None]
        invalid.extend({key: value for key, value in valid.items() if key != missing}
                       for missing in ("nome", "usuario", "senha"))
        invalid.extend(dict(valid, **{field: value}) for field, values in {
            "nome": (None, "", "   ", [], 123),
            "usuario": (None, "", [], 123),
            "senha": (None, "", "   ", [], 123),
            "perfil": (None, "inexistente", [], 123),
            "ativo": (None, "1", "0", 2, -1, 1.0, []),
        }.items() for value in values)
        for payload in invalid:
            with self.subTest(payload=payload):
                response = self.client.post("/api/usuarios", json=payload)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.execute("SELECT COUNT(*) FROM usuarios"), [(1,)])
        self.assertEqual(self.execute("SELECT COUNT(*) FROM log_auditoria"), [(0,)])

    def test_user_update_validates_fields_and_preserves_existing_password(self):
        self.login()
        valid = {"nome": "Administrador", "usuario": "admin", "perfil": "admin", "ativo": 1}
        invalid = [[], None]
        invalid.extend({key: value for key, value in valid.items() if key != missing}
                       for missing in ("nome", "usuario", "perfil"))
        invalid.extend(dict(valid, **{field: value}) for field, values in {
            "nome": (None, "", [], 123),
            "usuario": (None, "", [], 123),
            "senha": (None, "", [], 123),
            "perfil": (None, "inexistente", [], 123),
            "ativo": (None, "1", "0", 2, -1, 1.0, []),
        }.items() for value in values)
        before = self.execute("SELECT nome,usuario,senha,perfil,ativo FROM usuarios WHERE id=1")
        for payload in invalid:
            with self.subTest(payload=payload):
                response = self.client.put("/api/usuarios/1", json=payload)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.execute("SELECT nome,usuario,senha,perfil,ativo FROM usuarios WHERE id=1"), before)
        self.assertEqual(self.execute("SELECT COUNT(*) FROM log_auditoria"), [(0,)])
        self.assertEqual(self.client.put("/api/usuarios/1", json=dict(valid, nome="Nome atualizado")).status_code, 200)
        self.login()
        self.assertEqual(self.execute("SELECT nome FROM usuarios WHERE id=1"), [("Nome atualizado",)])

    def test_user_creation_honors_boolean_active_and_duplicate_login_is_conflict(self):
        self.login()
        payload = {"nome": "Inativo", "usuario": "inativo", "senha": "senha-teste", "ativo": False}
        self.assertEqual(self.client.post("/api/usuarios", json=payload).status_code, 201)
        self.assertEqual(self.execute("SELECT perfil,ativo FROM usuarios WHERE usuario='inativo'"), [("caixa", 0)])
        self.assertEqual(self.client.post("/api/usuarios", json=payload).status_code, 409)
        self.assertEqual(self.execute("SELECT COUNT(*) FROM usuarios"), [(2,)])
        self.assertEqual(self.execute("SELECT COUNT(*) FROM log_auditoria"), [(1,)])

    def test_user_update_duplicate_login_rolls_back_and_missing_user_is_404(self):
        self.login()
        self.assertEqual(self.client.post("/api/usuarios", json={
            "nome": "Outro", "usuario": "outro", "senha": "senha-teste",
        }).status_code, 201)
        other_id = self.execute("SELECT id FROM usuarios WHERE usuario='outro'")[0][0]
        payload = {"nome": "Outro alterado", "usuario": "admin", "perfil": "caixa", "ativo": 1}
        self.assertEqual(self.client.put(f"/api/usuarios/{other_id}", json=payload).status_code, 409)
        self.assertEqual(self.execute("SELECT nome,usuario FROM usuarios WHERE id=?", (other_id,)), [("Outro", "outro")])
        self.assertEqual(self.execute("SELECT COUNT(*) FROM log_auditoria"), [(1,)])
        self.assertEqual(self.client.put("/api/usuarios/99999", json=payload).status_code, 404)
        self.assertEqual(self.client.delete("/api/usuarios/99999").status_code, 404)

    def test_last_active_administrator_cannot_be_removed_disabled_or_demoted(self):
        self.login()
        payload = {"nome": "Administrador", "usuario": "admin", "perfil": "admin", "ativo": 1}
        for change in ({"ativo": False}, {"perfil": "caixa"}, {"ativo": 0, "perfil": "estoquista"}):
            with self.subTest(change=change):
                self.assertEqual(self.client.put("/api/usuarios/1", json=dict(payload, **change)).status_code, 409)
        self.assertEqual(self.client.delete("/api/usuarios/1").status_code, 409)
        self.assertEqual(self.execute("SELECT perfil,ativo FROM usuarios WHERE id=1"), [("admin", 1)])
        self.assertEqual(self.execute("SELECT COUNT(*) FROM log_auditoria"), [(0,)])
        # Um administrador desativado não permite retirar o último ativo.
        self.assertEqual(self.client.post("/api/usuarios", json={
            "nome": "Admin inativo", "usuario": "admin-inativo", "senha": "senha-teste",
            "perfil": "admin", "ativo": 0,
        }).status_code, 201)
        self.assertEqual(self.client.put("/api/usuarios/1", json=dict(payload, perfil="caixa")).status_code, 409)

    def test_another_active_administrator_allows_role_change(self):
        self.login()
        self.assertEqual(self.client.post("/api/usuarios", json={
            "nome": "Outro admin", "usuario": "outro-admin", "senha": "senha-teste",
            "perfil": "admin", "ativo": True,
        }).status_code, 201)
        response = self.client.put("/api/usuarios/1", json={
            "nome": "Administrador anterior", "usuario": "admin", "perfil": "caixa", "ativo": 1,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/usuarios").status_code, 403)
        self.assertEqual(self.client.get("/api/auth/me").json["perfil"], "caixa")
        self.assertEqual(self.execute("SELECT COUNT(*) FROM usuarios WHERE perfil='admin' AND ativo=1"), [(1,)])
        self.assertEqual(self.execute("SELECT acao FROM log_auditoria ORDER BY id"), [("criou",), ("editou",)])

    def test_concurrent_admin_changes_keep_one_active_administrator(self):
        self.login()
        self.assertEqual(self.client.post("/api/usuarios", json={
            "nome": "Outro admin", "usuario": "outro-admin", "senha": "senha-teste", "perfil": "admin",
        }).status_code, 201)
        other_id = self.execute("SELECT id FROM usuarios WHERE usuario='outro-admin'")[0][0]
        other_client = self.app.test_client()
        self.assertEqual(other_client.post("/api/auth/login", json={
            "usuario": "outro-admin", "senha": "senha-teste",
        }).status_code, 200)
        start = Barrier(2)

        def demote(arguments):
            client, user_id, login = arguments
            start.wait(timeout=5)
            return client.put(f"/api/usuarios/{user_id}", json={
                "nome": login, "usuario": login, "perfil": "caixa", "ativo": 1,
            }).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(demote, ((self.client, 1, "admin"), (other_client, other_id, "outro-admin"))))
        self.assertEqual(sorted(statuses), [200, 409])
        self.assertEqual(self.execute("SELECT COUNT(*) FROM usuarios WHERE perfil='admin' AND ativo=1"), [(1,)])

    def test_repeated_initialization_preserves_category_and_product(self):
        self.execute("INSERT INTO categorias (nome) VALUES ('Oficinas')")
        category_id = self.execute("SELECT id FROM categorias WHERE nome='Oficinas'")[0][0]
        self.execute(
            "INSERT INTO produtos (nome,codigo,categoria_id,quantidade,criado_em) VALUES (?,?,?,?,?)",
            ("Produto existente", "EXISTENTE", category_id, 7.5, "2026-01-01"),
        )
        for _ in range(2):
            self.initialize()
        self.assertEqual(self.execute("SELECT nome FROM categorias WHERE id=?", (category_id,)), [("Oficinas",)])
        self.assertEqual(self.execute("SELECT categoria_id,quantidade FROM produtos"), [(category_id, 7.5)])
        self.assertEqual(self.execute("PRAGMA foreign_key_check"), [])
        self.assertEqual(self.execute("SELECT COUNT(*) FROM usuarios WHERE usuario='admin'"), [(1,)])
        self.assertEqual(
            [row[1] for row in self.execute("PRAGMA table_info(operacoes_idempotentes)")],
            ["operacao_id", "usuario_id", "rota", "payload_hash", "resposta", "criado_em"],
        )

    def test_missing_legacy_columns_are_added_with_defaults(self):
        self.app.config["DATABASE"] = str(self.path.parent / "legacy.db")
        self.execute("""CREATE TABLE produtos (
            id INTEGER PRIMARY KEY, nome TEXT, codigo TEXT, quantidade REAL,
            preco_custo REAL, estoque_min INTEGER, criado_em TEXT
        )""")
        self.execute("INSERT INTO produtos VALUES (1,'Legado','L1',12,5,2,'2025-01-01')")
        self.initialize()
        self.assertEqual(self.execute("SELECT nome,quantidade,unidade,ativo FROM produtos"),
                         [("Legado", 12, "un", 1)])
        self.assertIn("conta_pagar_id", [row[1] for row in self.execute("PRAGMA table_info(fin_massa_entregas)")])
        self.initialize()
        self.assertEqual(self.execute("SELECT COUNT(*) FROM produtos"), [(1,)])

    def test_unexpected_migration_failure_rolls_back_and_remains_visible(self):
        self.app.config["DATABASE"] = str(self.path.parent / "unsupported-legacy.db")
        self.execute("CREATE TABLE dados_legados (id INTEGER PRIMARY KEY, nome TEXT)")
        self.execute("INSERT INTO dados_legados VALUES (1,'Preservado')")
        self.execute("CREATE VIEW produtos AS SELECT id,nome FROM dados_legados")
        before = self.execute("SELECT name,type,sql FROM sqlite_master ORDER BY name")
        with self.assertRaisesRegex(sqlite3.OperationalError, "view"):
            self.initialize()
        self.assertEqual(self.execute("SELECT name,type,sql FROM sqlite_master ORDER BY name"), before)
        self.assertEqual(self.execute("SELECT * FROM dados_legados"), [(1, "Preservado")])
        # Uma conexão nova consegue escrever após a falha: nenhuma transação
        # permanece aberta bloqueando o banco.
        self.execute("INSERT INTO dados_legados VALUES (2,'Ainda utilizável')")


if __name__ == "__main__":
    unittest.main()
