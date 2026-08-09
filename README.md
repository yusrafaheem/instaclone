# instaclone

A working Instagram-style photo feed, built from scratch: signup/login,
image posts with captions, a following feed and an explore feed, likes,
comments, follow/unfollow, and profile pages — all served by a real async
Python backend over a real SQLite database, with a vanilla HTML/CSS/JS
frontend. Runs entirely locally, no external services required.

74 automated tests pass end-to-end (`python -m unittest discover -s tests`),
and it's been load-tested locally up to 150 concurrent simulated users at
841 requests/sec with sub-3ms p95 latency and zero errors — real numbers,
captured by actually running it, in [`loadtest/results.md`](loadtest/results.md).

## Running it locally

```bash
pip install -r requirements.txt

# start the server (creates instaclone.db and media/ on first run)
python -m app.server
# -> serving on http://localhost:8000

# in another terminal, optionally seed some realistic data so the
# feed/explore pages aren't empty
python -m scripts.seed_data --users 500 --posts-per-user 3 --follows-per-user 15
# all seed accounts share the password: hunter22222 (e.g. user0 / hunter22222)
```

Then open `http://localhost:8000` in a browser: sign up, follow a few seeded
users, post a photo, like and comment.

Run the tests:

```bash
python -m unittest discover -s tests -v
```

Run the load test against a running server:

```bash
python -m loadtest.load_test --base-url http://localhost:8000 --concurrency 100 --duration 15
```

## Stack, and an honest note on why it's not the "real" Instagram stack

The brief was to get as close as practical to Instagram's real production
stack. Real Instagram (per their public engineering posts) runs on Django on
Python, PostgreSQL (via a custom sharding layer, originally Cassandra for
some data), Redis for caching and feed fan-out, and a React-based frontend.

This environment has **no package-index network access** (`pip`/`npm` both
return 403 through the sandbox's proxy), so none of Django, psycopg2,
redis-py, or React/npm could actually be installed. Rather than fake it,
every substitution below is a deliberate, documented stand-in using only
what's preinstalled, chosen to be the closest available analog in both
behavior and the concepts it teaches:

| Real Instagram | This project | Why this substitute |
|---|---|---|
| Django | **Tornado** | Also a mature, batteries-included-ish Python web framework, but async-native, so it directly demonstrates the same "don't block the event loop" pattern that makes real high-concurrency Python services work, without needing an ASGI layer bolted on. |
| PostgreSQL (sharded) | **SQLite, WAL mode** | Real SQL, real transactions, real indexes, real query planning — the schema, indexing strategy, and query patterns here (see below) are written to be a near 1:1 port to Postgres. WAL mode specifically is what makes SQLite tolerate concurrent readers/writers at all, which is the property that matters for this exercise. |
| Redis | **Hand-rolled in-memory `TTLCache`** | Implements the same cache-aside interface (`get`/`set`/`delete`/prefix invalidation) an app would use against Redis. Swapping it for `redis-py` later is a one-file change in `app/cache.py`; every call site is already written against that interface, not against dict internals. |
| React | **Vanilla HTML/CSS/JS**, hash-based router | No build step needed, and the app.js code is organized the way a component-based frontend would be (one render function per view, one API wrapper) so the shape of a future React port is already visible. |

Everything else — bcrypt password hashing, JWT session tokens, Pillow for
thumbnailing, cursor-based pagination, composite DB indexes, cache-aside
reads, and token-bucket rate limiting — is the same technique or the same
library a real production Instagram-like service would use; none of that
was substituted.

**Path to the real stack**, if/when package installs are available: swap
`sqlite3` calls in `app/db.py` for `asyncpg`/`psycopg`, point `app/cache.py`
at `redis-py` behind the same interface, and add a Django/DRF or FastAPI
layer in front of (or replacing) the Tornado handlers — the model layer
(`app/models/`) and SQL schema (`app/schema.sql`) are written in
plain, portable SQL specifically so that swap doesn't require rewriting the
query logic.

## Architecture

```
static/            vanilla HTML/CSS/JS frontend (hash router, fetch-based API client)
app/
  server.py        Tornado app + route table + entrypoint
  settings.py       all config, env-var driven
  db.py             thread-local SQLite connections, WAL mode, schema init
  cache.py          Redis-shaped in-memory TTL cache
  auth.py           bcrypt hashing + JWT issue/verify
  pagination.py     opaque cursor encode/decode
  ratelimit.py      token-bucket rate limiter
  images.py         upload validation, RGB normalization, thumbnailing
  models/           SQL query functions (users, posts, social graph)
  handlers/         Tornado RequestHandlers (thin: parse -> call model -> respond)
scripts/seed_data.py   bulk-generate realistic test data
loadtest/load_test.py  concurrent load generator + latency percentiles
tests/                 74 tests: unit + real end-to-end HTTP tests
```

Every handler is thin by design: parse the request, call into `models/` (or
`cache`), serialize the response. All SQL lives in `app/models/`, not
scattered through handlers, so the query patterns are auditable in one place.

## What "architected to handle a lot of people" actually means here

- **Async I/O end to end.** Tornado's IOLoop runs on one thread and handles
  many simultaneous connections without a thread per connection; anything
  synchronous and blocking (bcrypt, Pillow, SQLite calls) is explicitly
  offloaded to a 16-worker thread pool via `run_in_executor`
  (`BaseHandler.run_blocking`), so one slow bcrypt hash never stalls someone
  else's feed request.
- **Cursor-based pagination**, not `OFFSET`. Feed and profile pages take an
  opaque `(created_at, id)` cursor, so fetching page 50 costs the same as
  page 1 — real Instagram's API does this for the same reason: `OFFSET`
  pagination gets linearly slower the deeper you page.
- **Indexes chosen from the actual queries**, not guessed: composite indexes
  on `(user_id, created_at DESC, id DESC)` for posts (matches the feed/
  profile ORDER BY exactly), `(follower_id)`/`(followee_id)` for the follow
  graph, `(post_id)` for likes and comments.
- **Cache-aside reads** with a 30s TTL in front of the two hottest queries
  (`/api/feed`, `/api/feed/explore`), trading brief staleness for far fewer
  DB hits under repeated polling — a real, documented trade-off, not
  hand-waved.
- **Per-user rate limiting**, keyed by authenticated user ID rather than IP,
  so one heavy user (or a shared NAT/proxy full of legitimate users) can't
  starve everyone else's budget. The load test actually caught this
  distinction mattering in practice — see `loadtest/results.md`.
- **WAL-mode SQLite** so reads don't block behind writes, standing in for
  connection-pooled Postgres; the query/index/transaction shape is written
  to port over directly.

## Load test results (real, not estimated)

Full methodology, raw output, and a discussion of an interesting rate-limit
interaction discovered during testing: [`loadtest/results.md`](loadtest/results.md).
Headline numbers, from actually running `loadtest/load_test.py` against a
locally running server seeded with 500 users / ~1500 posts / ~7500 follows:

| Concurrency | Throughput | p50 | p95 | p99 | Errors |
|---|---|---|---|---|---|
| 10  | 54.4 req/s  | 3.0 ms | -      | -      | 0 |
| 100 | 555.0 req/s | 1.0 ms | 2.5 ms | 12.7 ms | 0 |
| 150 | 841.0 req/s | 0.9 ms | 2.3 ms | 7.8 ms  | 0 |

Zero real errors at every scale tested. 150 concurrent users was the largest
scale the local sandbox's own tooling could complete within its command
timeout — not a limit observed in the server itself; see the results doc for
the full explanation.

## Testing philosophy

74 tests, all exercising real code paths rather than mocks wherever
practical:

- `tests/test_models.py` runs real SQL against a real in-memory SQLite
  database built from the actual `schema.sql`, not a mocked DB layer.
- `tests/test_api.py` uses `tornado.testing.AsyncHTTPTestCase` to spin up a
  real Tornado server on a real local port and drive it with real HTTP
  requests, including real multipart file uploads for image posts.
- `tests/test_images.py` runs real Pillow operations against real generated
  test images (not fixture files), checking thumbnail bounds, no-upscaling
  behavior, and RGBA-to-RGB normalization.
- `tests/test_auth.py` / `test_ratelimit.py` / `test_pagination.py` /
  `test_cache.py` cover the security- and correctness-critical primitives
  (password hashing round-trips, token tampering, rate-limit bucket refill
  timing, cursor corruption handling) in isolation.

Three real bugs were caught and fixed by actually running this project
end-to-end rather than by inspection: a missing `username` field in
serialized posts (traced with a manual curl smoke test before the test
suite existed), a thread-local DB connection that went stale across test
runs because worker threads persist between tests, and cross-test cache
pollution from the process-wide cache singleton. All three fixes are called
out in the relevant module docstrings.

## API overview

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/signup` | - | Create an account |
| POST | `/api/auth/login` | - | Get a JWT |
| GET | `/api/me` | required | Current user |
| GET | `/api/feed` | required | Following feed, cursor-paginated |
| GET | `/api/feed/explore` | optional | Explore feed (everyone), cursor-paginated |
| POST | `/api/posts` | required | Create a post (multipart image + caption) |
| GET/DELETE | `/api/posts/:id` | optional/required | Fetch or delete a post |
| POST/DELETE | `/api/posts/:id/like` | required | Like / unlike |
| GET/POST | `/api/posts/:id/comments` | optional/required | List / add comments |
| POST/DELETE | `/api/users/:username/follow` | required | Follow / unfollow |
| GET | `/api/users/:username` | optional | Profile + paginated posts |
| PATCH | `/api/me/bio` | required | Update bio |
| GET | `/api/health` | - | Liveness check |
