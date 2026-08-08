"""Central configuration. Everything that would differ between a laptop
run and a production deployment lives here, read from environment
variables with sane local-dev defaults -- so there's exactly one place to
look when moving this from SQLite to Postgres or from the in-memory cache
to Redis.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = os.environ.get("INSTACLONE_DB_PATH", str(BASE_DIR / "instaclone.db"))

MEDIA_DIR = Path(os.environ.get("INSTACLONE_MEDIA_DIR", str(BASE_DIR / "media")))
UPLOADS_DIR = MEDIA_DIR / "uploads"
THUMBS_DIR = MEDIA_DIR / "thumbs"

# Signing key for JWT session tokens. A throwaway default is fine for a
# local prototype; production would pull this from a secrets manager and
# rotate it, which is exactly why it's read from the environment here
# rather than hardcoded deeper in the auth module.
JWT_SECRET = os.environ.get("INSTACLONE_JWT_SECRET", "dev-secret-not-for-production")
JWT_ALGORITHM = "HS256"
JWT_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days

THUMBNAIL_SIZE = (320, 320)
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 MB

FEED_PAGE_SIZE = 20
FEED_CACHE_TTL_SECONDS = 30

RATE_LIMIT_REQUESTS_PER_MINUTE = 120

SERVER_PORT = int(os.environ.get("INSTACLONE_PORT", "8000"))
