from __future__ import annotations

from .. import db, settings
from ..cache import cache
from ..models import posts as posts_model
from ..models import social as social_model
from ..models import users as users_model
from .base import ApiError, BaseHandler
from .post_handlers import _serialize_post


def _do_get_profile(username: str, viewer_id: int | None, cursor: str | None) -> dict:
    cache_key = f"profile:{username}:{cursor or ''}"
    cached = cache.get(cache_key)
    if cached is not None:
        cached = dict(cached)  # don't leak viewer-specific mutation into the cached copy
    else:
        conn = db.get_connection()
        user = users_model.get_user_by_username(conn, username)
        if user is None:
            raise ApiError(404, reason="user not found")

        rows, next_cursor = posts_model.posts_by_user(
            conn, user["id"], settings.FEED_PAGE_SIZE, cursor
        )
        cached = {
            "user_id": user["id"],
            "username": user["username"],
            "bio": user["bio"],
            "avatar_url": f"/media/{user['avatar_path']}" if user["avatar_path"] else None,
            "follower_count": users_model.follower_count(conn, user["id"]),
            "following_count": users_model.following_count(conn, user["id"]),
            "posts": [_serialize_post(r, viewer_id, conn) for r in rows],
            "next_cursor": next_cursor,
        }
        cache.set(cache_key, cached, settings.FEED_CACHE_TTL_SECONDS)
        cached = dict(cached)

    if viewer_id is not None:
        conn = db.get_connection()
        cached["is_following"] = social_model.is_following(conn, viewer_id, cached["user_id"])
    else:
        cached["is_following"] = False
    return cached


def _do_update_bio(user_id: int, bio: str) -> dict:
    conn = db.get_connection()
    users_model.update_bio(conn, user_id, bio)
    # Unlike feed pages, a profile is looked up by username, and a bio
    # edit is rare and user-initiated (they're looking at their own
    # profile right after saving it) -- so it's worth the extra lookup to
    # invalidate precisely rather than make them wait out the TTL to see
    # their own change reflected.
    row = users_model.get_user_by_id(conn, user_id)
    if row is not None:
        cache.delete_prefix(f"profile:{row['username']}")
    return {"bio": bio}


class ProfileHandler(BaseHandler):
    async def get(self, username: str) -> None:
        cursor = self.get_query_argument("cursor", default=None)
        result = await self.run_blocking(
            _do_get_profile, username, self.current_user_id, cursor
        )
        self.write_json(result)


class BioHandler(BaseHandler):
    async def put(self) -> None:
        user_id = self.require_auth()
        body = self.json_body()
        bio = (body.get("bio") or "").strip()[:500]
        result = await self.run_blocking(_do_update_bio, user_id, bio)
        self.write_json(result)
