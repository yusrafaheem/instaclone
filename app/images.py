"""Image storage and thumbnail generation.

Thumbnailing on upload (rather than resizing on every request) is the
same trade Instagram makes: pay the CPU cost once, at write time, so
every subsequent feed read -- which happens far more often than any
single post is uploaded -- serves a small pre-sized file instead of
re-decoding and resizing a multi-megabyte original on each view.
"""

from __future__ import annotations

import io
import time
import uuid
from pathlib import Path

from PIL import Image

from . import settings


class InvalidImageError(Exception):
    pass


def save_upload(raw_bytes: bytes, user_id: int) -> tuple[str, str]:
    """Validate, store, and thumbnail an uploaded image.

    Returns (image_path, thumb_path) as paths relative to MEDIA_DIR,
    suitable for storing in the posts table and serving via the static
    file handler.
    """
    if len(raw_bytes) > settings.MAX_UPLOAD_BYTES:
        raise InvalidImageError(
            f"image exceeds {settings.MAX_UPLOAD_BYTES} byte limit"
        )

    try:
        image = Image.open(io.BytesIO(raw_bytes))
        image.load()
    except Exception as e:
        raise InvalidImageError(f"not a valid image: {e}") from e

    settings.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    settings.THUMBS_DIR.mkdir(parents=True, exist_ok=True)

    # Normalize to JPEG so the frontend doesn't need to handle every
    # source format the browser's file picker might hand us (HEIC, WebP,
    # PNG with alpha, etc).
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    filename = f"{user_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}.jpg"
    image_path = f"uploads/{filename}"
    thumb_path = f"thumbs/{filename}"

    image.save(settings.MEDIA_DIR / image_path, "JPEG", quality=88)

    thumb = image.copy()
    thumb.thumbnail(settings.THUMBNAIL_SIZE)
    thumb.save(settings.MEDIA_DIR / thumb_path, "JPEG", quality=80)

    return image_path, thumb_path
