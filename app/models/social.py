"""Likes, comments, and follows -- the graph/interaction data around a
post, as opposed to the post content itself (posts.py)."""

from __future__ import annotations

import sqlite3
import time


def like_post(conn: sqlite3.Connection, user_id: int, post_id: int) -> bool:
    """Idempotent: liking an already-liked post is a no-op, not an
    error, matching how a real client (tap the heart twice by accident)
    expects this to behave. Returns whether this call actually created a
    new like."""
    try:
        conn.execute(
            "INSERT INTO likes (user_id, post_id, created_at) VALUES (?, ?, ?)",
            (user_id, post_id, time.time()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        conn.rollback()
        return False


def unlike_post(conn: sqlite3.Connection, user_id: int, post_id: int) -> bool:
    cur = conn.execute(
        "DELETE FROM likes WHERE user_id = ? AND post_id = ?", (user_id, post_id)
    )
    conn.commit()
    return cur.rowcount > 0


def like_count(conn: sqlite3.Connection, post_id: int) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM likes WHERE post_id = ?", (post_id,)).fetchone()
    return row["n"]


def has_liked(conn: sqlite3.Connection, user_id: int, post_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM likes WHERE user_id = ? AND post_id = ?", (user_id, post_id)
    ).fetchone()
    return row is not None


def add_comment(conn: sqlite3.Connection, post_id: int, user_id: int, body: str) -> int:
    cur = conn.execute(
        "INSERT INTO comments (post_id, user_id, body, created_at) VALUES (?, ?, ?, ?)",
        (post_id, user_id, body, time.time()),
    )
    conn.commit()
    return cur.lastrowid


def comments_for_post(conn: sqlite3.Connection, post_id: int, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT comments.*, users.username FROM comments "
        "JOIN users ON users.id = comments.user_id "
        "WHERE post_id = ? ORDER BY comments.created_at ASC, comments.id ASC LIMIT ?",
        (post_id, limit),
    ).fetchall()


def follow(conn: sqlite3.Connection, follower_id: int, followee_id: int) -> bool:
    if follower_id == followee_id:
        return False
    try:
        conn.execute(
            "INSERT INTO follows (follower_id, followee_id, created_at) VALUES (?, ?, ?)",
            (follower_id, followee_id, time.time()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        conn.rollback()
        return False


def unfollow(conn: sqlite3.Connection, follower_id: int, followee_id: int) -> bool:
    cur = conn.execute(
        "DELETE FROM follows WHERE follower_id = ? AND followee_id = ?",
        (follower_id, followee_id),
    )
    conn.commit()
    return cur.rowcount > 0


def is_following(conn: sqlite3.Connection, follower_id: int, followee_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM follows WHERE follower_id = ? AND followee_id = ?",
        (follower_id, followee_id),
    ).fetchone()
    return row is not None
