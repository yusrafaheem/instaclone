"""Password hashing and session tokens.

Passwords are hashed with bcrypt (adaptive cost, salted automatically) --
never stored or compared in plain text. Sessions are stateless JWTs
signed with HS256: the server verifies a signature instead of doing a DB
lookup on every request, which matters under load (no session-table read
on the hot path of every authenticated request).
"""

from __future__ import annotations

import time

import bcrypt
import jwt

from . import settings


def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())


def verify_password(password: str, password_hash: bytes) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), bytes(password_hash))
    except ValueError:
        # Malformed hash (shouldn't happen from our own hash_password, but
        # a corrupt DB row shouldn't crash the request).
        return False


def issue_token(user_id: int, username: str) -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + settings.JWT_TTL_SECONDS,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


class InvalidToken(Exception):
    """Raised for any token that doesn't verify: expired, wrong
    signature, or malformed. Handlers catch this one type rather than
    every PyJWT-specific exception class."""


def verify_token(token: str) -> dict:
    """Return the decoded payload for a valid token, or raise
    InvalidToken."""
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError as e:
        raise InvalidToken(str(e)) from e
