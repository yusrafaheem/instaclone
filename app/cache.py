"""A minimal cache-aside layer, shaped like the Redis calls it stands in
for (get/set/delete, TTL on every key) so swapping in real Redis later is
a matter of replacing this module's implementation, not the call sites in
feed_handlers.py.

Why a cache in front of the feed at all: the feed query is "posts from
everyone I follow, newest first" -- cheap for one user, but the same
handful of popular accounts' posts get re-fetched by every one of their
followers' feed loads. Caching the assembled feed page per (user, cursor)
for a short TTL turns N redundant DB round-trips into 1, which is exactly
the problem Instagram's real Memcached layer solves at a much larger
scale.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class _Entry:
    value: Any
    expires_at: float


class TTLCache:
    """Thread-safe in-process cache with per-key expiry.

    Single-process only -- a real deployment running multiple app servers
    needs a shared cache (Redis) so a write on server A invalidates what
    server B has cached, which this can't do. Documented as a known
    limitation in the README rather than hidden.
    """

    def __init__(self) -> None:
        self._data: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if entry.expires_at < time.time():
                del self._data[key]
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        with self._lock:
            self._data[key] = _Entry(value=value, expires_at=time.time() + ttl_seconds)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def delete_prefix(self, prefix: str) -> int:
        """Delete every key starting with ``prefix``. Used for
        invalidation: a new post from user U should invalidate every
        cached feed page keyed by ``feed:{follower_id}:*`` for U's
        followers -- but since we cache by *reader*, not by *poster*, the
        cheaper and correct move is a short TTL rather than tracking the
        follower graph just to invalidate precisely. This method exists
        for the narrower case of invalidating one user's own cached data
        (e.g. their profile) on demand."""
        with self._lock:
            keys = [k for k in self._data if k.startswith(prefix)]
            for k in keys:
                del self._data[k]
            return len(keys)

    def clear_all(self) -> None:
        """Drop every entry, regardless of TTL. Real request handling
        never needs this -- it's for the test suite, which reuses the
        one process-wide ``cache`` object below across every test case.
        Without clearing it between tests, a cache key that two unrelated
        tests happen to share (e.g. the anonymous explore feed's first
        page) lets one test's cached response leak into another's
        assertions, which is exactly the failure that motivated adding
        this method rather than a purely theoretical concern."""
        with self._lock:
            self._data.clear()


# One process-wide cache instance, imported by the handlers that need it.
cache = TTLCache()
