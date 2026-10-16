"""O backup deve liberar arquivos antes de sair, inclusive quando falha."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from sgliras import create_app
from sgliras.backups import fazer_backup, verificar_integridade_banco
from sgliras.database import init_db


class BackupConnectionTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'backup-tests-only',
                               'DATABASE': str(Path(folder.name) / 'test.db'),
                               'BACKUP_DIR': str(Path(folder.name) / 'backups')})
        with self.app.app_context():
            init_db()
        self.opened = []
        self.real_connect = sqlite3.connect

    def connect(self, path, *args, **kwargs):
        # Keep strong references so garbage collection cannot hide a missing close.
        connection = self.real_connect(path, *args, **kwargs)
        self.opened.append(connection)
        return connection

    def assert_all_closed(self):
        for connection in self.opened:
            try:
                with self.assertRaises(sqlite3.ProgrammingError):
                    connection.execute('SELECT 1')
            finally:
                connection.close()

    def test_success_closes_source_destination_and_integrity_connections(self):
        with self.app.app_context(), patch('sgliras.backups.sqlite3.connect', self.connect):
            name = fazer_backup('test')
            self.assertIsNotNone(name)
            self.assertEqual(verificar_integridade_banco(), (True, 'ok'))
            self.assertEqual(len(self.opened), 3)
            self.assert_all_closed()
        # Removals execute while the connection objects are still strongly referenced.
        Path(self.app.config['BACKUP_DIR'], name).unlink()
        Path(self.app.config['DATABASE']).unlink()

    def test_opening_destination_failure_closes_source(self):
        def connect(path, *args, **kwargs):
            if path != self.app.config['DATABASE']:
                raise sqlite3.OperationalError('Destino indisponível no teste')
            return self.connect(path, *args, **kwargs)
        with self.app.app_context(), patch('sgliras.backups.sqlite3.connect', connect):
            self.assertIsNone(fazer_backup('test'))
            self.assertEqual(len(self.opened), 1)
            self.assert_all_closed()

    def test_backup_failure_closes_both_connections(self):
        class FailingConnection(sqlite3.Connection):
            def backup(self, *args, **kwargs):
                raise sqlite3.OperationalError('Falha de cópia no teste')
        def connect(path, *args, **kwargs):
            return self.connect(path, *args, factory=FailingConnection, **kwargs)
        with self.app.app_context(), patch('sgliras.backups.sqlite3.connect', connect):
            self.assertIsNone(fazer_backup('test'))
            self.assertEqual(len(self.opened), 2)
            self.assert_all_closed()

    def test_integrity_failure_closes_connection(self):
        class FailingConnection(sqlite3.Connection):
            def execute(self, sql, *args, **kwargs):
                if sql == 'PRAGMA integrity_check':
                    raise sqlite3.OperationalError('Falha de integridade no teste')
                return super().execute(sql, *args, **kwargs)
        def connect(path, *args, **kwargs):
            return self.connect(path, *args, factory=FailingConnection, **kwargs)
        with self.app.app_context(), patch('sgliras.backups.sqlite3.connect', connect):
            result = verificar_integridade_banco()
            self.assertFalse(result[0])
            self.assertEqual(len(self.opened), 1)
            self.assert_all_closed()


if __name__ == '__main__':
    unittest.main()
