"""Tests for the SQLite connection-management layer (app/db.py): thread-
local connections, the WAL/foreign-key pragmas, and the schema
init/reset helpers the rest of the test suite relies on."""

import tempfile
import unittest
from pathlib import Path

from app import db, settings


class TestGetConnection(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_db_path = settings.DB_PATH
        settings.DB_PATH = str(Path(self._tmpdir.name) / "test.db")
        db.close_and_forget()

    def tearDown(self):
        db.close_and_forget()
        settings.DB_PATH = self._orig_db_path
        self._tmpdir.cleanup()

    def test_get_connection_returns_same_object_on_repeated_calls(self):
        conn1 = db.get_connection()
        conn2 = db.get_connection()
        self.assertIs(conn1, conn2)

    def test_get_connection_creates_the_db_file(self):
        db.get_connection()
        self.assertTrue(Path(settings.DB_PATH).exists())

    def test_get_connection_reopens_when_db_path_changes(self):
        conn1 = db.get_connection()
        settings.DB_PATH = str(Path(self._tmpdir.name) / "other.db")
        conn2 = db.get_connection()
        self.assertIsNot(conn1, conn2)

    def test_wal_mode_is_enabled(self):
        conn = db.get_connection()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(mode.lower(), "wal")

    def test_foreign_keys_pragma_is_enabled(self):
        conn = db.get_connection()
        enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        self.assertEqual(enabled, 1)


class TestInitAndResetDb(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_db_path = settings.DB_PATH
        settings.DB_PATH = str(Path(self._tmpdir.name) / "test.db")
        db.close_and_forget()

    def tearDown(self):
        db.close_and_forget()
        settings.DB_PATH = self._orig_db_path
        self._tmpdir.cleanup()


if __name__ == "__main__":
    unittest.main()
