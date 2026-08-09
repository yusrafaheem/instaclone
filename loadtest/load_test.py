#!/usr/bin/env python3
"""A real concurrent load generator against a real, already-running
instaclone server -- not a simulation of one. Requires the target
database to already be seeded (see scripts/seed_data.py) with enough
users/posts/follows that the feed queries this hits aren't trivially
empty.

Two phases, deliberately kept separate:

1. Login phase (unlimited concurrency, not part of the reported
   numbers): authenticate a pool of virtual users once, up front. Login
   does a bcrypt comparison -- expensive on purpose, since that's what
   makes password hashing resistant to brute force -- and mixing that
   cost into the "how many feed requests can this server serve"
   measurement would answer a different question than the one this test
   is asking.
2. Load phase (fixed duration, fixed concurrency): each of N worker
   threads repeatedly makes one authenticated request at a time, chosen
   from a realistic weighted mix (mostly feed reads, some likes, some
   profile views), for the configured duration. Every request's latency
   and outcome is recorded and aggregated into throughput and latency
   percentiles at the end.

Usage:
    python3 -m loadtest.load_test --base-url http://localhost:8000 \\
        --concurrency 50 --duration 20 --auth-users 100
"""

from __future__ import annotations

import argparse
import random
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import requests


@dataclass
class Sample:
    endpoint: str
    latency_ms: float
    ok: bool  # 2xx/3xx
    rate_limited: bool = False  # 429, tracked separately from real errors


@dataclass
class Results:
    samples: list[Sample] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, sample: Sample) -> None:
        with self.lock:
            self.samples.append(sample)


def _login_one(base_url: str, username: str, password: str) -> str | None:
    resp = requests.post(
        f"{base_url}/api/auth/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    return resp.json()["token"] if resp.status_code == 200 else None


def login_pool(base_url: str, n: int, password: str) -> list[str]:
    """Authenticate the first ``n`` seed users (user0..user{n-1}) and
    return their tokens. Not part of the timed load phase.

    Logins are fired concurrently (not part of the measured phase, so
    there's no reason to serialize them) -- each one does a real bcrypt
    comparison on the server, and the server's own thread pool
    (handlers/base.py) is what actually bounds how many of these run at
    once, which is a real, useful thing to see: this phase's wall time is
    a rough proxy for "how fast can this server authenticate a burst of
    logins," distinct from the feed-read throughput the timed phase
    measures.
    """
    t0 = time.time()
    tokens: list[str] = []
    with ThreadPoolExecutor(max_workers=32) as pool:
        futures = [pool.submit(_login_one, base_url, f"user{i}", password) for i in range(n)]
        for future in as_completed(futures):
            token = future.result()
            if token:
                tokens.append(token)
    elapsed = time.time() - t0
    print(
        f"Logged in {len(tokens)}/{n} users in {elapsed:.2f}s "
        f"({elapsed / max(len(tokens), 1) * 1000:.0f}ms/login average, concurrent, bcrypt-dominated)"
    )
    return tokens


def worker(
    base_url: str,
    token: str,
    num_users: int,
    stop_at: float,
    results: Results,
    think_time_range: tuple[float, float],
) -> None:
    """Simulate one persistent logged-in user's session: repeatedly make
    one request from a realistic weighted mix, with a small random pause
    between requests (real people don't fire requests back-to-back at the
    network's speed limit). Each worker owns a single ``token`` for its
    entire run rather than drawing randomly from a shared pool -- so the
    per-user rate limit in base.py is being exercised the way it would be
    against real distinct users, not artificially tripped by many threads
    impersonating the same account.
    """
    session = requests.Session()
    rng = random.Random()
    while time.time() < stop_at:
        headers = {"Authorization": f"Bearer {token}"}
        roll = rng.random()

        if roll < 0.70:
            endpoint = "GET /api/feed"
            t0 = time.time()
            resp = session.get(f"{base_url}/api/feed", headers=headers, timeout=10)
        elif roll < 0.85:
            endpoint = "GET /api/feed/explore"
            t0 = time.time()
            resp = session.get(f"{base_url}/api/feed/explore", headers=headers, timeout=10)
        elif roll < 0.95:
            post_id = rng.randint(1, 1400)
            endpoint = "POST /api/posts/:id/like"
            t0 = time.time()
            resp = session.post(f"{base_url}/api/posts/{post_id}/like", headers=headers, timeout=10)
        else:
            username = f"user{rng.randint(0, num_users - 1)}"
            endpoint = "GET /api/users/:username"
            t0 = time.time()
            resp = session.get(f"{base_url}/api/users/{username}", headers=headers, timeout=10)

        latency_ms = (time.time() - t0) * 1000
        results.record(
            Sample(
                endpoint=endpoint,
                latency_ms=latency_ms,
                ok=resp.status_code < 400,
                rate_limited=resp.status_code == 429,
            )
        )
        time.sleep(rng.uniform(*think_time_range))


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(int(len(values) * p), len(values) - 1)
    return values[idx]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--concurrency", type=int, default=50, help="number of virtual users")
    parser.add_argument("--duration", type=float, default=20.0, help="seconds")
    parser.add_argument("--auth-users", type=int, default=100)
    parser.add_argument("--password", default="hunter22222")
    parser.add_argument("--think-time-min", type=float, default=0.05)
    parser.add_argument("--think-time-max", type=float, default=0.30)
    args = parser.parse_args()

    resp = requests.get(f"{args.base_url}/api/health", timeout=5)
    resp.raise_for_status()
    print(f"Server reachable at {args.base_url}")

    # One distinct logged-in user per concurrent worker, so --concurrency
    # workers need at least that many authenticated identities. If fewer
    # seed users were requested than the concurrency level, tokens are
    # reused round-robin -- which is a real scenario too (a user with
    # multiple open tabs/devices), just not the primary one this defaults
    # to modeling.
    tokens = login_pool(args.base_url, max(args.auth_users, args.concurrency), args.password)
    if not tokens:
        raise SystemExit("no users could log in -- did you run scripts/seed_data.py first?")

    results = Results()
    stop_at = time.time() + args.duration
    think_range = (args.think_time_min, args.think_time_max)
    threads = [
        threading.Thread(
            target=worker,
            args=(args.base_url, tokens[i % len(tokens)], len(tokens), stop_at, results, think_range),
        )
        for i in range(args.concurrency)
    ]

    print(f"Running {args.concurrency} concurrent virtual users for {args.duration}s...")
    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall_time = time.time() - t0

    samples = results.samples
    latencies = [s.latency_ms for s in samples]
    rate_limited = [s for s in samples if s.rate_limited]
    real_errors = [s for s in samples if not s.ok and not s.rate_limited]

    print()
    print("=== Load test results ===")
    print(f"Concurrency:      {args.concurrency}")
    print(f"Wall time:        {wall_time:.2f}s")
    print(f"Total requests:   {len(samples)}")
    print(
        f"Rate-limited:     {len(rate_limited)} "
        f"({len(rate_limited) / max(len(samples), 1) * 100:.2f}%) -- expected once a single "
        f"simulated user's request rate exceeds RATE_LIMIT_REQUESTS_PER_MINUTE"
    )
    print(f"Real errors:      {len(real_errors)} ({len(real_errors) / max(len(samples), 1) * 100:.2f}%)")
    print(f"Throughput:       {len(samples) / wall_time:.1f} req/s")
    if latencies:
        print(f"Latency p50:      {percentile(latencies, 0.50):.1f} ms")
        print(f"Latency p95:      {percentile(latencies, 0.95):.1f} ms")
        print(f"Latency p99:      {percentile(latencies, 0.99):.1f} ms")
        print(f"Latency max:      {max(latencies):.1f} ms")
        print(f"Latency mean:     {statistics.mean(latencies):.1f} ms")

    by_endpoint: dict[str, list[float]] = {}
    for s in samples:
        by_endpoint.setdefault(s.endpoint, []).append(s.latency_ms)
    print()
    print("Per-endpoint breakdown:")
    for endpoint, lats in sorted(by_endpoint.items()):
        print(
            f"  {endpoint:30s} n={len(lats):5d}  p50={percentile(lats, 0.5):6.1f}ms  "
            f"p95={percentile(lats, 0.95):6.1f}ms"
        )


if __name__ == "__main__":
    main()
