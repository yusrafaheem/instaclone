from __future__ import annotations

import sqlite3
import time

from ..pagination import decode_cursor, encode_cursor


def create_post(
    conn: sqlite3.Connection, user_id: int, caption: str, image_path: str, thumb_path: str
) -> int:
    cur = conn.execute(
        "INSERT INTO posts (user_id, caption, image_path, thumb_path, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, caption, image_path, thumb_path, time.time()),
    )
    conn.commit()
    return cur.lastrowid


def get_post(conn: sqlite3.Connection, post_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT posts.*, users.username FROM posts "
        "JOIN users ON users.id = posts.user_id WHERE posts.id = ?",
        (post_id,),
    ).fetchone()


def delete_post(conn: sqlite3.Connection, post_id: int, user_id: int) -> bool:
    """Delete ``post_id`` if it's owned by ``user_id``. Returns whether a
    row was actually deleted, so the handler can tell "not found" apart
    from "not yours" without a separate ownership query."""
    cur = conn.execute("DELETE FROM posts WHERE id = ? AND user_id = ?", (post_id, user_id))
    conn.commit()
    return cur.rowcount > 0


def posts_by_user(
    conn: sqlite3.Connection, user_id: int, limit: int, cursor: str | None
) -> tuple[list[sqlite3.Row], str | None]:
    """A single user's posts, newest first, cursor-paginated. Used for
    profile pages."""
    decoded = decode_cursor(cursor)
    if decoded is None:
        rows = conn.execute(
            "SELECT posts.*, users.username FROM posts "
            "JOIN users ON users.id = posts.user_id "
            "WHERE posts.user_id = ? "
            "ORDER BY posts.created_at DESC, posts.id DESC LIMIT ?",
            (user_id, limit + 1),
        ).fetchall()
    else:
        created_at, row_id = decoded
        rows = conn.execute(
            "SELECT posts.*, users.username FROM posts "
            "JOIN users ON users.id = posts.user_id "
            "WHERE posts.user_id = ? "
            "AND (posts.created_at, posts.id) < (?, ?) "
            "ORDER BY posts.created_at DESC, posts.id DESC LIMIT ?",
            (user_id, created_at, row_id, limit + 1),
        ).fetchall()
    return _paginate(rows, limit)


def feed_for_follower(
    conn: sqlite3.Connection, follower_id: int, limit: int, cursor: str | None
) -> tuple[list[sqlite3.Row], str | None]:
    """Posts from everyone ``follower_id`` follows, newest first. This is
    the "following" feed -- the query joins through the follows table
    rather than pre-computing a fan-out feed table, which is the simple,
    correct choice at this scale (see README's scaling notes for what
    changes if this needs to serve millions of users)."""
    decoded = decode_cursor(cursor)
    if decoded is None:
        rows = conn.execute(
            """
            SELECT posts.*, users.username FROM posts
            JOIN follows ON follows.followee_id = posts.user_id
            JOIN users ON users.id = posts.user_id
            WHERE follows.follower_id = ?
            ORDER BY posts.created_at DESC, posts.id DESC
            LIMIT ?
            """,
            (follower_id, limit + 1),
        ).fetchall()
    else:
        created_at, row_id = decoded
        rows = conn.execute(
            """
            SELECT posts.*, users.username FROM posts
            JOIN follows ON follows.followee_id = posts.user_id
            JOIN users ON users.id = posts.user_id
            WHERE follows.follower_id = ?
            AND (posts.created_at, posts.id) < (?, ?)
            ORDER BY posts.created_at DESC, posts.id DESC
            LIMIT ?
            """,
            (follower_id, created_at, row_id, limit + 1),
        ).fetchall()
    return _paginate(rows, limit)


def explore_feed(
    conn: sqlite3.Connection, limit: int, cursor: str | None
) -> tuple[list[sqlite3.Row], str | None]:
    """Every post, newest first -- the "explore" / global feed shown to
    someone who isn't following anyone yet."""
    decoded = decode_cursor(cursor)
    if decoded is None:
        rows = conn.execute(
            "SELECT posts.*, users.username FROM posts "
            "JOIN users ON users.id = posts.user_id "
            "ORDER BY posts.created_at DESC, posts.id DESC LIMIT ?",
            (limit + 1,),
        ).fetchall()
    else:
        created_at, row_id = decoded
        rows = conn.execute(
            "SELECT posts.*, users.username FROM posts "
            "JOIN users ON users.id = posts.user_id "
            "WHERE (posts.created_at, posts.id) < (?, ?) "
            "ORDER BY posts.created_at DESC, posts.id DESC LIMIT ?",
            (created_at, row_id, limit + 1),
        ).fetchall()
    return _paginate(rows, limit)


def _paginate(rows: list[sqlite3.Row], limit: int) -> tuple[list[sqlite3.Row], str | None]:
    """Shared "did we fetch one extra row to detect more pages" logic --
    fetching limit+1 and trimming is cheaper than a separate COUNT query
    to determine has_more."""
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = None
    if has_more and page:
        last = page[-1]
        next_cursor = encode_cursor(last["created_at"], last["id"])
    return page, next_cursor
