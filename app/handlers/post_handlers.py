from __future__ import annotations

from .. import db, images
from ..models import posts as posts_model
from ..models import social as social_model
from .base import ApiError, BaseHandler


def _serialize_post(row, viewer_id: int | None, conn) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "username": row["username"],
        "caption": row["caption"],
        "image_url": f"/media/{row['image_path']}",
        "thumb_url": f"/media/{row['thumb_path']}",
        "created_at": row["created_at"],
        "like_count": social_model.like_count(conn, row["id"]),
        "liked_by_viewer": (
            social_model.has_liked(conn, viewer_id, row["id"]) if viewer_id else False
        ),
    }


def _do_create_post(user_id: int, caption: str, raw_bytes: bytes) -> dict:
    conn = db.get_connection()
    try:
        image_path, thumb_path = images.save_upload(raw_bytes, user_id)
    except images.InvalidImageError as e:
        raise ApiError(400, reason=str(e)) from None
    post_id = posts_model.create_post(conn, user_id, caption, image_path, thumb_path)
    # A brand-new post won't be visible in the poster's own cached
    # profile page, or in followers' cached feeds, until each of those
    # cache entries' short TTL expires (FEED_CACHE_TTL_SECONDS, currently
    # 30s) -- deliberately, per cache.py's docstring: tracking exactly
    # which cache keys a given post affects (every follower's feed page,
    # the poster's own profile page, every cursor position) isn't worth
    # the bookkeeping when "briefly stale" is an acceptable trade-off.
    row = posts_model.get_post(conn, post_id)
    return _serialize_post(row, user_id, conn)


def _do_get_post(post_id: int, viewer_id: int | None) -> dict:
    conn = db.get_connection()
    row = posts_model.get_post(conn, post_id)
    if row is None:
        raise ApiError(404, reason="post not found")
    return _serialize_post(row, viewer_id, conn)


def _do_delete_post(post_id: int, user_id: int) -> bool:
    conn = db.get_connection()
    return posts_model.delete_post(conn, post_id, user_id)


class PostCollectionHandler(BaseHandler):
    async def post(self) -> None:
        user_id = self.require_auth()

        files = self.request.files.get("image")
        if not files:
            raise ApiError(400, reason="an 'image' file field is required")
        raw_bytes = files[0]["body"]
        caption = (self.get_body_argument("caption", default="") or "").strip()[:2000]

        result = await self.run_blocking(_do_create_post, user_id, caption, raw_bytes)
        self.write_json(result, status=201)


class PostDetailHandler(BaseHandler):
    async def get(self, post_id: str) -> None:
        result = await self.run_blocking(_do_get_post, int(post_id), self.current_user_id)
        self.write_json(result)

    async def delete(self, post_id: str) -> None:
        user_id = self.require_auth()
        deleted = await self.run_blocking(_do_delete_post, int(post_id), user_id)
        if not deleted:
            raise ApiError(404, reason="post not found or not yours")
        self.write_json({"deleted": True})
