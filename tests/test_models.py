"""Model-layer tests run against a real in-memory SQLite database (not
mocked) built from the actual schema.sql, so a schema/query mismatch
shows up here rather than only at request time."""

import sqlite3
import unittest
from pathlib import Path

from app.models import posts as posts_model
from app.models import social as social_model
from app.models import users as users_model

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "app" / "schema.sql"


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    return conn


class TestUsersModel(unittest.TestCase):
    def setUp(self):
        self.conn = _make_conn()

    def test_create_and_fetch_user(self):
        uid = users_model.create_user(self.conn, "alice", "alice@example.com", b"hash")
        row = users_model.get_user_by_id(self.conn, uid)
        self.assertEqual(row["username"], "alice")

    def test_duplicate_username_raises(self):
        users_model.create_user(self.conn, "alice", "a1@example.com", b"hash")
        with self.assertRaises(users_model.UsernameTakenError):
            users_model.create_user(self.conn, "alice", "a2@example.com", b"hash")

    def test_duplicate_email_raises(self):
        users_model.create_user(self.conn, "alice", "same@example.com", b"hash")
        with self.assertRaises(users_model.EmailTakenError):
            users_model.create_user(self.conn, "bob", "same@example.com", b"hash")

    def test_get_missing_user_returns_none(self):
        self.assertIsNone(users_model.get_user_by_username(self.conn, "nobody"))

    def test_update_bio(self):
        uid = users_model.create_user(self.conn, "alice", "a@example.com", b"hash")
        users_model.update_bio(self.conn, uid, "hello world")
        row = users_model.get_user_by_id(self.conn, uid)
        self.assertEqual(row["bio"], "hello world")

    def test_follower_and_following_counts(self):
        a = users_model.create_user(self.conn, "alice", "a@example.com", b"h")
        b = users_model.create_user(self.conn, "bob", "b@example.com", b"h")
        social_model.follow(self.conn, a, b)
        self.assertEqual(users_model.follower_count(self.conn, b), 1)
        self.assertEqual(users_model.following_count(self.conn, a), 1)
        self.assertEqual(users_model.follower_count(self.conn, a), 0)

    def test_update_avatar(self):
        uid = users_model.create_user(self.conn, "alice", "a@example.com", b"hash")
        users_model.update_avatar(self.conn, uid, "avatars/alice.jpg")
        row = users_model.get_user_by_id(self.conn, uid)
        self.assertEqual(row["avatar_path"], "avatars/alice.jpg")

    def test_get_user_by_id_returns_none_for_missing_id(self):
        self.assertIsNone(users_model.get_user_by_id(self.conn, 99999))

    def test_username_taken_error_message_contains_username(self):
        users_model.create_user(self.conn, "alice", "a1@example.com", b"hash")
        try:
            users_model.create_user(self.conn, "alice", "a2@example.com", b"hash")
            self.fail("expected UsernameTakenError")
        except users_model.UsernameTakenError as e:
            self.assertIn("alice", str(e))

    def test_email_taken_error_message_contains_email(self):
        users_model.create_user(self.conn, "alice", "same@example.com", b"hash")
        try:
            users_model.create_user(self.conn, "bob", "same@example.com", b"hash")
            self.fail("expected EmailTakenError")
        except users_model.EmailTakenError as e:
            self.assertIn("same@example.com", str(e))

    def test_create_user_ids_increment(self):
        a = users_model.create_user(self.conn, "alice", "a@example.com", b"h")
        b = users_model.create_user(self.conn, "bob", "b@example.com", b"h")
        self.assertGreater(b, a)

    def test_following_count_for_multiple_followees(self):
        a = users_model.create_user(self.conn, "alice", "a@example.com", b"h")
        b = users_model.create_user(self.conn, "bob", "b@example.com", b"h")
        c = users_model.create_user(self.conn, "carol", "c@example.com", b"h")
        social_model.follow(self.conn, a, b)
        social_model.follow(self.conn, a, c)
        self.assertEqual(users_model.following_count(self.conn, a), 2)


class TestPostsModel(unittest.TestCase):
    def setUp(self):
        self.conn = _make_conn()
        self.user_id = users_model.create_user(self.conn, "alice", "a@example.com", b"h")

    def test_create_and_get_post(self):
        post_id = posts_model.create_post(self.conn, self.user_id, "hi", "img.jpg", "thumb.jpg")
        row = posts_model.get_post(self.conn, post_id)
        self.assertEqual(row["caption"], "hi")
        self.assertEqual(row["username"], "alice")

    def test_delete_post_by_owner_succeeds(self):
        post_id = posts_model.create_post(self.conn, self.user_id, "hi", "i", "t")
        self.assertTrue(posts_model.delete_post(self.conn, post_id, self.user_id))
        self.assertIsNone(posts_model.get_post(self.conn, post_id))

    def test_delete_post_by_non_owner_fails(self):
        other = users_model.create_user(self.conn, "bob", "b@example.com", b"h")
        post_id = posts_model.create_post(self.conn, self.user_id, "hi", "i", "t")
        self.assertFalse(posts_model.delete_post(self.conn, post_id, other))
        self.assertIsNotNone(posts_model.get_post(self.conn, post_id))

    def test_posts_by_user_pagination(self):
        for i in range(5):
            posts_model.create_post(self.conn, self.user_id, f"post {i}", "i", "t")
        page1, cursor1 = posts_model.posts_by_user(self.conn, self.user_id, limit=2, cursor=None)
        self.assertEqual(len(page1), 2)
        self.assertIsNotNone(cursor1)
        page2, cursor2 = posts_model.posts_by_user(self.conn, self.user_id, limit=2, cursor=cursor1)
        self.assertEqual(len(page2), 2)
        # No overlap between consecutive pages.
        self.assertEqual(set(p["id"] for p in page1) & set(p["id"] for p in page2), set())

    def test_posts_by_user_last_page_has_no_next_cursor(self):
        posts_model.create_post(self.conn, self.user_id, "only one", "i", "t")
        page, cursor = posts_model.posts_by_user(self.conn, self.user_id, limit=20, cursor=None)
        self.assertEqual(len(page), 1)
        self.assertIsNone(cursor)

    def test_feed_for_follower_only_shows_followed_users_posts(self):
        other = users_model.create_user(self.conn, "bob", "b@example.com", b"h")
        posts_model.create_post(self.conn, self.user_id, "alice's post", "i", "t")
        posts_model.create_post(self.conn, other, "bob's post", "i", "t")

        follower = users_model.create_user(self.conn, "carol", "c@example.com", b"h")
        social_model.follow(self.conn, follower, self.user_id)

        feed, _ = posts_model.feed_for_follower(self.conn, follower, limit=10, cursor=None)
        self.assertEqual(len(feed), 1)
        self.assertEqual(feed[0]["username"], "alice")

    def test_explore_feed_shows_everyones_posts(self):
        other = users_model.create_user(self.conn, "bob", "b@example.com", b"h")
        posts_model.create_post(self.conn, self.user_id, "a", "i", "t")
        posts_model.create_post(self.conn, other, "b", "i", "t")
        feed, _ = posts_model.explore_feed(self.conn, limit=10, cursor=None)
        self.assertEqual(len(feed), 2)

    def test_delete_post_returns_false_for_nonexistent_post(self):
        self.assertFalse(posts_model.delete_post(self.conn, 99999, self.user_id))

    def test_get_post_returns_none_for_missing_id(self):
        self.assertIsNone(posts_model.get_post(self.conn, 99999))

    def test_posts_by_user_empty_when_no_posts(self):
        page, cursor = posts_model.posts_by_user(self.conn, self.user_id, limit=10, cursor=None)
        self.assertEqual(page, [])
        self.assertIsNone(cursor)

    def test_feed_for_follower_empty_when_following_nobody(self):
        lonely = users_model.create_user(self.conn, "lonely", "l@example.com", b"h")
        feed, cursor = posts_model.feed_for_follower(self.conn, lonely, limit=10, cursor=None)
        self.assertEqual(feed, [])
        self.assertIsNone(cursor)

    def test_explore_feed_orders_newest_first(self):
        first = posts_model.create_post(self.conn, self.user_id, "older", "i", "t")
        second = posts_model.create_post(self.conn, self.user_id, "newer", "i", "t")
        feed, _ = posts_model.explore_feed(self.conn, limit=10, cursor=None)
        self.assertEqual([p["id"] for p in feed], [second, first])


class TestSocialModel(unittest.TestCase):
    def setUp(self):
        self.conn = _make_conn()
        self.alice = users_model.create_user(self.conn, "alice", "a@example.com", b"h")
        self.bob = users_model.create_user(self.conn, "bob", "b@example.com", b"h")
        self.post_id = posts_model.create_post(self.conn, self.bob, "hi", "i", "t")

    def test_like_and_unlike(self):
        self.assertTrue(social_model.like_post(self.conn, self.alice, self.post_id))
        self.assertEqual(social_model.like_count(self.conn, self.post_id), 1)
        self.assertTrue(social_model.has_liked(self.conn, self.alice, self.post_id))
        self.assertTrue(social_model.unlike_post(self.conn, self.alice, self.post_id))
        self.assertEqual(social_model.like_count(self.conn, self.post_id), 0)

    def test_liking_twice_is_idempotent(self):
        self.assertTrue(social_model.like_post(self.conn, self.alice, self.post_id))
        self.assertFalse(social_model.like_post(self.conn, self.alice, self.post_id))
        self.assertEqual(social_model.like_count(self.conn, self.post_id), 1)

    def test_comments_are_ordered_oldest_first(self):
        social_model.add_comment(self.conn, self.post_id, self.alice, "first")
        social_model.add_comment(self.conn, self.post_id, self.bob, "second")
        comments = social_model.comments_for_post(self.conn, self.post_id)
        self.assertEqual([c["body"] for c in comments], ["first", "second"])

    def test_follow_and_unfollow(self):
        self.assertTrue(social_model.follow(self.conn, self.alice, self.bob))
        self.assertTrue(social_model.is_following(self.conn, self.alice, self.bob))
        self.assertTrue(social_model.unfollow(self.conn, self.alice, self.bob))
        self.assertFalse(social_model.is_following(self.conn, self.alice, self.bob))

    def test_cannot_follow_self(self):
        self.assertFalse(social_model.follow(self.conn, self.alice, self.alice))

    def test_following_twice_is_idempotent(self):
        self.assertTrue(social_model.follow(self.conn, self.alice, self.bob))
        self.assertFalse(social_model.follow(self.conn, self.alice, self.bob))


if __name__ == "__main__":
    unittest.main()
