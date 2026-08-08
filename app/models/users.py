from __future__ import annotations

import sqlite3
import time


class UsernameTakenError(Exception):
    pass


class EmailTakenError(Exception):
    pass


def create_user(conn: sqlite3.Connection, username: str, email: str, password_hash: bytes) -> int:
    try:
        cur = conn.execute(
            "INSERT INTO users (username, email, password_hash, bio, created_at) "
            "VALUES (?, ?, ?, '', ?)",
            (username, email, password_hash, time.time()),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError as e:
        # UNIQUE constraint violation -- figure out which column so the
        # API can return a specific, actionable error message.
        conn.rollback()
        existing = conn.execute(
            "SELECT username, email FROM users WHERE username = ? OR email = ?",
            (username, email),
        ).fetchone()
        if existing and existing["username"] == username:
            raise UsernameTakenError(username) from e
        raise EmailTakenError(email) from e


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_by_username(conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def update_bio(conn: sqlite3.Connection, user_id: int, bio: str) -> None:
    conn.execute("UPDATE users SET bio = ? WHERE id = ?", (bio, user_id))
    conn.commit()


def update_avatar(conn: sqlite3.Connection, user_id: int, avatar_path: str) -> None:
    conn.execute("UPDATE users SET avatar_path = ? WHERE id = ?", (avatar_path, user_id))
    conn.commit()


def follower_count(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM follows WHERE followee_id = ?", (user_id,)
    ).fetchone()
    return row["n"]


def following_count(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM follows WHERE follower_id = ?", (user_id,)
    ).fetchone()
    return row["n"]
