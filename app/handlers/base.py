"""Shared request-handling machinery every endpoint builds on.

The single most important thing here is run_blocking(): Tornado's whole
concurrency model is one thread running an event loop, handling many
connections by never blocking that thread on I/O. bcrypt hashing, Pillow
image processing, and SQLite calls are all *synchronous* and CPU/IO
bound -- calling them directly in a handler would stall every other
in-flight request for the duration. run_blocking() offloads them to a
thread pool via run_in_executor, which is what actually makes "handle a
lot of people" true for this server rather than just an aspiration in
the README.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import tornado.web

from .. import auth, db
from ..ratelimit import RateLimiter

# Sized a bit above the CPU count: this pool is for a mix of CPU-bound
# work (bcrypt, thumbnailing) and short blocking I/O (SQLite), so a
# modest amount of oversubscription keeps the CPU-bound work from
# starving quick DB calls behind it.
_executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="instaclone-worker")

rate_limiter = RateLimiter(requests_per_minute=120)


class ApiError(tornado.web.HTTPError):
    """Raised by handler code for expected, user-facing failures (bad
    input, not found, unauthorized) so BaseHandler can render them as
    consistent JSON instead of Tornado's default HTML error page."""


class BaseHandler(tornado.web.RequestHandler):
    def initialize(self) -> None:
        self.current_user_id: int | None = None
        self.current_username: str | None = None

    def prepare(self) -> None:
        # Authenticate first so the rate limit bucket is keyed by *user*
        # when we can identify one, and falls back to IP only for
        # anonymous requests. Keying purely by remote_ip would conflate
        # "many distinct real users behind the same NAT/proxy/load
        # generator" with "one abusive client hammering us" -- exactly
        # the distinction that matters for a site meant to serve a lot of
        # different people, and a mistake this project's own load test
        # caught: with IP-based limiting, every simulated user shared one
        # bucket because they all ran from localhost.
        self._authenticate()
        client_key = (
            f"user:{self.current_user_id}"
            if self.current_user_id is not None
            else f"ip:{self.request.remote_ip or 'unknown'}"
        )
        if not rate_limiter.allow(client_key):
            raise ApiError(429, reason="rate limit exceeded")

    def _authenticate(self) -> None:
        header = self.request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return
        token = header[len("Bearer "):]
        try:
            payload = auth.verify_token(token)
        except auth.InvalidToken:
            return
        self.current_user_id = int(payload["sub"])
        self.current_username = payload["username"]

    def require_auth(self) -> int:
        if self.current_user_id is None:
            raise ApiError(401, reason="authentication required")
        return self.current_user_id

    def write_json(self, data: Any, status: int = 200) -> None:
        self.set_status(status)
        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.finish(json.dumps(data))

    def write_error(self, status_code: int, **kwargs) -> None:
        reason = kwargs.get("reason") or self._reason or "error"
        self.write_json({"error": reason}, status=status_code)

    def json_body(self) -> dict:
        try:
            return json.loads(self.request.body or b"{}")
        except json.JSONDecodeError as e:
            raise ApiError(400, reason=f"invalid JSON body: {e}") from e

    async def run_blocking(self, fn: Callable, *args) -> Any:
        """Run a synchronous function (bcrypt, Pillow, sqlite3 calls) on
        the shared thread pool instead of the event loop thread."""
        loop = tornado.ioloop.IOLoop.current()
        return await loop.run_in_executor(_executor, fn, *args)

    def get_db(self):
        # get_connection() returns this worker thread's connection --
        # only safe to call from inside run_blocking, never directly on
        # the event loop thread.
        return db.get_connection()
