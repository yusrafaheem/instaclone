"""SQLite connection management.

Tornado runs one process with an event loop plus a small thread pool for
blocking work (see server.py); SQLite connections aren't safe to share
across threads, so each worker thread gets its own connection via
thread-local storage rather than a single global connection or a
hand-rolled pool. WAL (write-ahead logging) mode is what makes this
workable under concurrent load: readers don't block writers and vice
versa, which is the piece of SQLite's design that makes it a reasonable
stand-in for Postgres in a single-node prototype -- multi-node
replication and sharding are the things it genuinely can't do, which is
why the README calls out Postgres as the production choice.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from . import settings

_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """Return this thread's SQLite connection, creating and configuring
    it on first use. Safe to call from any worker thread; never share the
    returned connection across threads.

    Also reopens if settings.DB_PATH has changed since this thread's
    connection was opened. That check matters more than it looks: the
    handlers' blocking work runs on a small *shared* ThreadPoolExecutor
    (see handlers/base.py) whose worker threads are reused across many
    requests -- and, in the test suite, across many tests. Without this
    check, a worker thread that already opened a connection for test A's
    temp database would keep serving that same (possibly now-deleted)
    connection for test B, even after test B points settings.DB_PATH at
    its own fresh temp file. This was caught by exactly that failure mode
    during development, not reasoned out in advance.
    """
    conn = getattr(_local, "conn", None)
    path = getattr(_local, "path", None)
    if conn is not None and path == settings.DB_PATH:
        return conn

    if conn is not None:
        conn.close()

    Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    _local.conn = conn
    _local.path = settings.DB_PATH
    return conn


def init_db() -> None:
    """Create tables and indexes if they don't already exist. Idempotent,
    safe to call on every server startup."""
    schema_path = Path(__file__).parent / "schema.sql"
    conn = get_connection()
    with open(schema_path, encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()


def reset_db() -> None:
    """Drop and recreate every table. Used by tests to get a clean slate
    per test case without spinning up a fresh subprocess."""
    conn = get_connection()
    conn.executescript(
        """
        DROP TABLE IF EXISTS comments;
        DROP TABLE IF EXISTS likes;
        DROP TABLE IF EXISTS follows;
        DROP TABLE IF EXISTS posts;
        DROP TABLE IF EXISTS users;
        """
    )
    conn.commit()
    init_db()


def close_and_forget() -> None:
    """Close this thread's connection and drop the thread-local reference,
    so the next get_connection() call reopens against whatever
    settings.DB_PATH currently points at. Exists for tests: each test
    case points DB_PATH at its own temp file, and without this the
    thread-local cache would keep serving the *previous* test's
    connection since get_connection() only opens once per thread."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None
        _local.path = None
