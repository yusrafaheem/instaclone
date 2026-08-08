from __future__ import annotations

from .. import db
from ..models import social as social_model
from ..models import users as users_model
from .base import ApiError, BaseHandler


def _do_like(post_id: int, user_id: int) -> dict:
    conn = db.get_connection()
    social_model.like_post(conn, user_id, post_id)
    return {"like_count": social_model.like_count(conn, post_id), "liked": True}


def _do_unlike(post_id: int, user_id: int) -> dict:
    conn = db.get_connection()
    social_model.unlike_post(conn, user_id, post_id)
    return {"like_count": social_model.like_count(conn, post_id), "liked": False}


def _do_add_comment(post_id: int, user_id: int, body: str) -> dict:
    conn = db.get_connection()
    comment_id = social_model.add_comment(conn, post_id, user_id, body)
    return {"id": comment_id, "post_id": post_id, "body": body}


def _do_get_comments(post_id: int) -> list[dict]:
    conn = db.get_connection()
    rows = social_model.comments_for_post(conn, post_id)
    return [
        {
            "id": r["id"],
            "user_id": r["user_id"],
            "username": r["username"],
            "body": r["body"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def _do_follow(follower_id: int, followee_username: str) -> dict:
    conn = db.get_connection()
    target = users_model.get_user_by_username(conn, followee_username)
    if target is None:
        raise ApiError(404, reason="user not found")
    created = social_model.follow(conn, follower_id, target["id"])
    return {"following": True, "was_new": created}


def _do_unfollow(follower_id: int, followee_username: str) -> dict:
    conn = db.get_connection()
    target = users_model.get_user_by_username(conn, followee_username)
    if target is None:
        raise ApiError(404, reason="user not found")
    social_model.unfollow(conn, follower_id, target["id"])
    return {"following": False}


class LikeHandler(BaseHandler):
    async def post(self, post_id: str) -> None:
        user_id = self.require_auth()
        result = await self.run_blocking(_do_like, int(post_id), user_id)
        self.write_json(result)

    async def delete(self, post_id: str) -> None:
        user_id = self.require_auth()
        result = await self.run_blocking(_do_unlike, int(post_id), user_id)
        self.write_json(result)


class CommentHandler(BaseHandler):
    async def get(self, post_id: str) -> None:
        result = await self.run_blocking(_do_get_comments, int(post_id))
        self.write_json({"comments": result})

    async def post(self, post_id: str) -> None:
        user_id = self.require_auth()
        body = self.json_body()
        text = (body.get("body") or "").strip()
        if not text or len(text) > 1000:
            raise ApiError(400, reason="comment body must be 1-1000 characters")
        result = await self.run_blocking(_do_add_comment, int(post_id), user_id, text)
        self.write_json(result, status=201)


class FollowHandler(BaseHandler):
    async def post(self, username: str) -> None:
        user_id = self.require_auth()
        result = await self.run_blocking(_do_follow, user_id, username)
        self.write_json(result)

    async def delete(self, username: str) -> None:
        user_id = self.require_auth()
        result = await self.run_blocking(_do_unfollow, user_id, username)
        self.write_json(result)
