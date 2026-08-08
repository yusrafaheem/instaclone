"""The feed endpoints -- the highest-traffic part of the app by a wide
margin (every user hits this on every app open and every scroll), and
the one place caching is applied. See cache.py's docstring for why a
short TTL cache-aside layer, keyed by (user, cursor), is the right shape
here rather than per-post or per-follow-graph invalidation.
"""

from __future__ import annotations

from .. import db, settings
from ..cache import cache
from ..models import posts as posts_model
from .base import BaseHandler
from .post_handlers import _serialize_post


def _do_following_feed(user_id: int, cursor: str | None) -> dict:
    cache_key = f"feed:following:{user_id}:{cursor or ''}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    conn = db.get_connection()
    rows, next_cursor = posts_model.feed_for_follower(
        conn, user_id, settings.FEED_PAGE_SIZE, cursor
    )
    result = {
        "posts": [_serialize_post(r, user_id, conn) for r in rows],
        "next_cursor": next_cursor,
    }
    cache.set(cache_key, result, settings.FEED_CACHE_TTL_SECONDS)
    return result


def _do_explore_feed(viewer_id: int | None, cursor: str | None) -> dict:
    cache_key = f"feed:explore:{viewer_id or 'anon'}:{cursor or ''}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    conn = db.get_connection()
    rows, next_cursor = posts_model.explore_feed(conn, settings.FEED_PAGE_SIZE, cursor)
    result = {
        "posts": [_serialize_post(r, viewer_id, conn) for r in rows],
        "next_cursor": next_cursor,
    }
    cache.set(cache_key, result, settings.FEED_CACHE_TTL_SECONDS)
    return result


class FollowingFeedHandler(BaseHandler):
    async def get(self) -> None:
        user_id = self.require_auth()
        cursor = self.get_query_argument("cursor", default=None)
        result = await self.run_blocking(_do_following_feed, user_id, cursor)
        self.write_json(result)


class ExploreFeedHandler(BaseHandler):
    async def get(self) -> None:
        cursor = self.get_query_argument("cursor", default=None)
        result = await self.run_blocking(_do_explore_feed, self.current_user_id, cursor)
        self.write_json(result)
