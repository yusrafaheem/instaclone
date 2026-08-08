"""Per-client token-bucket rate limiting.

Without this, a single misbehaving client (buggy frontend retry loop, or
someone deliberately hammering the API) can exhaust the thread pool that
blocking work (bcrypt hashing, thumbnail generation, SQLite writes) runs
on, degrading the service for everyone else -- the opposite of "handle a
lot of people." A token bucket is the standard shape for this: each
client has a bucket that refills at a steady rate and is capped at a
burst size, so short bursts are tolerated but sustained abuse is capped.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class RateLimiter:
    def __init__(self, requests_per_minute: int) -> None:
        self._rate_per_second = requests_per_minute / 60.0
        self._capacity = float(requests_per_minute)
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def allow(self, client_key: str) -> bool:
        """Consume one token for ``client_key`` (typically an IP address
        or user id) and return whether the request should proceed."""
        now = time.time()
        with self._lock:
            bucket = self._buckets.get(client_key)
            if bucket is None:
                bucket = _Bucket(tokens=self._capacity, last_refill=now)
                self._buckets[client_key] = bucket

            elapsed = now - bucket.last_refill
            bucket.tokens = min(self._capacity, bucket.tokens + elapsed * self._rate_per_second)
            bucket.last_refill = now

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True
            return False
