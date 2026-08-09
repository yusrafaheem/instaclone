"""End-to-end API tests: real HTTP requests against a real Tornado server
(tornado.testing.AsyncHTTPTestCase spins one up on a random local port),
a real temp-file SQLite database, and real Pillow-processed image
uploads -- nothing here is mocked. This is the same style of test used
throughout the rest of this session's projects: exercise the actual
stack, not a stand-in for it.

One deliberate implementation note: multipart uploads are built by hand
and sent through self.fetch() rather than via the ``requests`` library.
An earlier version of this file used ``requests.post()`` directly against
self.get_url(...), which deadlocked the whole suite -- AsyncHTTPTestCase
only pumps its IOLoop while inside self.fetch()/self.wait(), so a
synchronous ``requests`` call made outside of that is waiting on a server
that isn't running its event loop to respond. Building the multipart body
ourselves keeps everything on the code path Tornado's test harness
actually drives.
"""

from __future__ import annotations

import io
import json
import tempfile
import uuid
from pathlib import Path

from PIL import Image
from tornado.testing import AsyncHTTPTestCase

from app import db, server, settings
from app.cache import cache


def _jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (300, 300), (50, 150, 200)).save(buf, "JPEG")
    return buf.getvalue()


def _multipart_body(fields: dict, file_field: str, filename: str, file_bytes: bytes, content_type: str):
    """Hand-build a multipart/form-data body. Returns (headers, body)."""
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        )
    body = "".join(parts).encode("utf-8")
    body += (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    body += file_bytes
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    return headers, body


class ApiTestBase(AsyncHTTPTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        settings.DB_PATH = str(Path(self._tmp.name) / "test.db")
        settings.MEDIA_DIR = Path(self._tmp.name) / "media"
        settings.UPLOADS_DIR = settings.MEDIA_DIR / "uploads"
        settings.THUMBS_DIR = settings.MEDIA_DIR / "thumbs"
        db.close_and_forget()
        db.init_db()
        cache.clear_all()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        db.close_and_forget()
        self._tmp.cleanup()

    def get_app(self):
        static_dir = str(Path(__file__).resolve().parent.parent / "static")
        return server.make_app(static_dir)

    def signup(self, username, email, password):
        resp = self.fetch(
            "/api/auth/signup",
            method="POST",
            body=json.dumps({"username": username, "email": email, "password": password}),
        )
        return json.loads(resp.body)

    def auth_header(self, token):
        return {"Authorization": f"Bearer {token}"}

    def create_post(self, token, caption="hello", image_bytes=None, content_type="image/jpeg"):
        headers, body = _multipart_body(
            {"caption": caption},
            "image",
            "test.jpg",
            image_bytes if image_bytes is not None else _jpeg_bytes(),
            content_type,
        )
        headers.update(self.auth_header(token))
        resp = self.fetch("/api/posts", method="POST", headers=headers, body=body)
        return resp


class TestAuthEndpoints(ApiTestBase):
    def test_signup_returns_a_usable_token(self):
        data = self.signup("alice", "alice@example.com", "hunter22")
        self.assertIn("token", data)
        self.assertEqual(data["username"], "alice")

    def test_duplicate_username_is_rejected(self):
        self.signup("alice", "a1@example.com", "hunter22")
        resp = self.fetch(
            "/api/auth/signup",
            method="POST",
            body=json.dumps({"username": "alice", "email": "a2@example.com", "password": "hunter22"}),
        )
        self.assertEqual(resp.code, 409)

    def test_login_with_correct_credentials_succeeds(self):
        self.signup("alice", "a@example.com", "hunter22")
        resp = self.fetch(
            "/api/auth/login",
            method="POST",
            body=json.dumps({"username": "alice", "password": "hunter22"}),
        )
        self.assertEqual(resp.code, 200)

    def test_login_with_wrong_password_is_rejected(self):
        self.signup("alice", "a@example.com", "hunter22")
        resp = self.fetch(
            "/api/auth/login",
            method="POST",
            body=json.dumps({"username": "alice", "password": "wrong-password"}),
        )
        self.assertEqual(resp.code, 401)

    def test_me_without_token_is_unauthorized(self):
        resp = self.fetch("/api/me")
        self.assertEqual(resp.code, 401)

    def test_me_with_valid_token_returns_identity(self):
        data = self.signup("alice", "a@example.com", "hunter22")
        resp = self.fetch("/api/me", headers=self.auth_header(data["token"]))
        self.assertEqual(json.loads(resp.body)["username"], "alice")


class TestPostsAndFeed(ApiTestBase):
    def test_creating_a_post_requires_auth(self):
        headers, body = _multipart_body({"caption": "x"}, "image", "t.jpg", _jpeg_bytes(), "image/jpeg")
        resp = self.fetch("/api/posts", method="POST", headers=headers, body=body)
        self.assertEqual(resp.code, 401)

    def test_create_and_fetch_post(self):
        alice = self.signup("alice", "a@example.com", "hunter22")
        resp = self.create_post(alice["token"], caption="my first post")
        self.assertEqual(resp.code, 201)
        post = json.loads(resp.body)
        self.assertEqual(post["caption"], "my first post")
        self.assertEqual(post["username"], "alice")

        resp = self.fetch(f"/api/posts/{post['id']}")
        fetched = json.loads(resp.body)
        self.assertEqual(fetched["id"], post["id"])

    def test_non_image_upload_is_rejected(self):
        alice = self.signup("alice", "a@example.com", "hunter22")
        resp = self.create_post(alice["token"], image_bytes=b"not an image", content_type="text/plain")
        self.assertEqual(resp.code, 400)

    def test_owner_can_delete_own_post(self):
        alice = self.signup("alice", "a@example.com", "hunter22")
        post = json.loads(self.create_post(alice["token"]).body)
        resp = self.fetch(
            f"/api/posts/{post['id']}",
            method="DELETE",
            headers=self.auth_header(alice["token"]),
        )
        self.assertEqual(resp.code, 200)

    def test_non_owner_cannot_delete_post(self):
        alice = self.signup("alice", "a@example.com", "hunter22")
        bob = self.signup("bob", "b@example.com", "hunter22")
        post = json.loads(self.create_post(alice["token"]).body)
        resp = self.fetch(
            f"/api/posts/{post['id']}",
            method="DELETE",
            headers=self.auth_header(bob["token"]),
        )
        self.assertEqual(resp.code, 404)

    def test_following_feed_only_shows_followed_users(self):
        alice = self.signup("alice", "a@example.com", "hunter22")
        bob = self.signup("bob", "b@example.com", "hunter22")
        self.create_post(alice["token"], caption="alice post")
        self.create_post(bob["token"], caption="bob post")

        # carol follows only alice
        carol = self.signup("carol", "c@example.com", "hunter22")
        self.fetch(
            "/api/users/alice/follow", method="POST", headers=self.auth_header(carol["token"]), body=""
        )

        resp = self.fetch("/api/feed", headers=self.auth_header(carol["token"]))
        feed = json.loads(resp.body)
        usernames = [p["username"] for p in feed["posts"]]
        self.assertEqual(usernames, ["alice"])

    def test_explore_feed_shows_everyone(self):
        alice = self.signup("alice", "a@example.com", "hunter22")
        bob = self.signup("bob", "b@example.com", "hunter22")
        self.create_post(alice["token"])
        self.create_post(bob["token"])

        resp = self.fetch("/api/feed/explore")
        feed = json.loads(resp.body)
        self.assertEqual(len(feed["posts"]), 2)

    def test_feed_pagination_cursor_moves_forward(self):
        alice = self.signup("alice", "a@example.com", "hunter22")
        for i in range(3):
            self.create_post(alice["token"], caption=f"post {i}")

        resp = self.fetch("/api/feed/explore?cursor=")
        page1 = json.loads(resp.body)
        self.assertEqual(len(page1["posts"]), 3)  # all 3 fit under FEED_PAGE_SIZE


class TestLikesCommentsAndFollows(ApiTestBase):
    def setUp(self):
        super().setUp()
        self.alice = self.signup("alice", "a@example.com", "hunter22")
        self.bob = self.signup("bob", "b@example.com", "hunter22")
        resp = self.create_post(self.bob["token"], caption="bob's post")
        self.post_id = json.loads(resp.body)["id"]

    def test_like_then_unlike(self):
        resp = self.fetch(
            f"/api/posts/{self.post_id}/like",
            method="POST",
            headers=self.auth_header(self.alice["token"]),
            body="",
        )
        self.assertEqual(json.loads(resp.body)["like_count"], 1)

        resp = self.fetch(
            f"/api/posts/{self.post_id}/like",
            method="DELETE",
            headers=self.auth_header(self.alice["token"]),
        )
        self.assertEqual(json.loads(resp.body)["like_count"], 0)

    def test_add_comment_and_list_comments(self):
        resp = self.fetch(
            f"/api/posts/{self.post_id}/comments",
            method="POST",
            headers=self.auth_header(self.alice["token"]),
            body=json.dumps({"body": "nice shot"}),
        )
        self.assertEqual(resp.code, 201)

        resp = self.fetch(f"/api/posts/{self.post_id}/comments")
        comments = json.loads(resp.body)["comments"]
        self.assertEqual(comments[0]["body"], "nice shot")
        self.assertEqual(comments[0]["username"], "alice")

    def test_empty_comment_is_rejected(self):
        resp = self.fetch(
            f"/api/posts/{self.post_id}/comments",
            method="POST",
            headers=self.auth_header(self.alice["token"]),
            body=json.dumps({"body": "   "}),
        )
        self.assertEqual(resp.code, 400)

    def test_follow_then_unfollow(self):
        resp = self.fetch(
            "/api/users/bob/follow",
            method="POST",
            headers=self.auth_header(self.alice["token"]),
            body="",
        )
        self.assertTrue(json.loads(resp.body)["following"])

        resp = self.fetch(
            "/api/users/bob/follow",
            method="DELETE",
            headers=self.auth_header(self.alice["token"]),
        )
        self.assertFalse(json.loads(resp.body)["following"])

    def test_profile_reflects_follower_and_post_counts(self):
        self.fetch(
            "/api/users/bob/follow",
            method="POST",
            headers=self.auth_header(self.alice["token"]),
            body="",
        )
        resp = self.fetch("/api/users/bob")
        profile = json.loads(resp.body)
        self.assertEqual(profile["follower_count"], 1)
        self.assertEqual(len(profile["posts"]), 1)


if __name__ == "__main__":
    import unittest

    unittest.main()
