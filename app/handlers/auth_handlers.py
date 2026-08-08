from __future__ import annotations

import re

from .. import auth, db
from ..models import users as users_model
from .base import ApiError, BaseHandler

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.]{3,30}$")


def _do_signup(username: str, email: str, password: str) -> dict:
    conn = db.get_connection()
    password_hash = auth.hash_password(password)
    try:
        user_id = users_model.create_user(conn, username, email, password_hash)
    except users_model.UsernameTakenError:
        raise ApiError(409, reason="username already taken") from None
    except users_model.EmailTakenError:
        raise ApiError(409, reason="email already registered") from None
    token = auth.issue_token(user_id, username)
    return {"token": token, "user_id": user_id, "username": username}


def _do_login(username: str, password: str) -> dict:
    conn = db.get_connection()
    row = users_model.get_user_by_username(conn, username)
    if row is None or not auth.verify_password(password, row["password_hash"]):
        raise ApiError(401, reason="invalid username or password")
    token = auth.issue_token(row["id"], row["username"])
    return {"token": token, "user_id": row["id"], "username": row["username"]}


class SignupHandler(BaseHandler):
    async def post(self) -> None:
        body = self.json_body()
        username = (body.get("username") or "").strip()
        email = (body.get("email") or "").strip().lower()
        password = body.get("password") or ""

        if not _USERNAME_RE.match(username):
            raise ApiError(
                400,
                reason="username must be 3-30 characters: letters, numbers, '.', '_'",
            )
        if "@" not in email:
            raise ApiError(400, reason="invalid email")
        if len(password) < 8:
            raise ApiError(400, reason="password must be at least 8 characters")

        result = await self.run_blocking(_do_signup, username, email, password)
        self.write_json(result, status=201)


class LoginHandler(BaseHandler):
    async def post(self) -> None:
        body = self.json_body()
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        if not username or not password:
            raise ApiError(400, reason="username and password required")

        result = await self.run_blocking(_do_login, username, password)
        self.write_json(result)
