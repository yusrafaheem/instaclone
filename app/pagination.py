"""Cursor-based pagination.

Real Instagram's feed API paginates by an opaque cursor, not a page
number or SQL OFFSET -- and for the same reason we do it here: OFFSET
pagination makes the database walk past and discard every earlier row on
each request (page 500 means scanning and throwing away 10,000 rows just
to get to the next 20), which gets slower as the feed grows and actively
punishes your most active users. A cursor encodes "everything strictly
after this point" and turns into an indexed range condition instead
(``WHERE (created_at, id) < (cursor_created_at, cursor_id)``), which
costs the same whether it's page 2 or page 5000.
"""

from __future__ import annotations

import base64
import json

TokenType = str | None


def encode_cursor(created_at: float, row_id: int) -> str:
    raw = json.dumps({"t": created_at, "id": row_id}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: TokenType) -> tuple[float, int] | None:
    """Return (created_at, id) from an opaque cursor string, or None if
    ``cursor`` is empty/missing (meaning "start from the newest post")."""
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        data = json.loads(raw)
        return float(data["t"]), int(data["id"])
    except (ValueError, KeyError, TypeError):
        # A malformed or tampered cursor degrades to "start over" rather
        # than a 500 error -- pagination state should never be able to
        # crash the request that carries it.
        return None
