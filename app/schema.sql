-- instaclone schema
--
-- Written as plain SQL (not an ORM's auto-migration) so the indexing
-- choices are visible and intentional. Every foreign key and every column
-- used in a WHERE/ORDER BY on a hot path (the feed, a profile's posts, a
-- post's likes/comments) has a matching index -- these are exactly the
-- indexes you'd create on the equivalent PostgreSQL tables in production.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    email         TEXT NOT NULL UNIQUE,
    password_hash BLOB NOT NULL,
    bio           TEXT NOT NULL DEFAULT '',
    avatar_path   TEXT,
    created_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    caption      TEXT NOT NULL DEFAULT '',
    image_path   TEXT NOT NULL,
    thumb_path   TEXT NOT NULL,
    created_at   REAL NOT NULL
);

-- The feed query is "posts by these user_ids, newest first, paginated by
-- (created_at, id)" -- this composite index lets SQLite satisfy that
-- entirely from the index without a separate sort step.
CREATE INDEX IF NOT EXISTS idx_posts_user_created ON posts(user_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS follows (
    follower_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    followee_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at   REAL NOT NULL,
    PRIMARY KEY (follower_id, followee_id)
);

-- The feed's core query is "which user_ids does user X follow" -- indexed
-- so that lookup is O(log n) instead of a table scan per feed request.
CREATE INDEX IF NOT EXISTS idx_follows_follower ON follows(follower_id);
CREATE INDEX IF NOT EXISTS idx_follows_followee ON follows(followee_id);

CREATE TABLE IF NOT EXISTS likes (
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    post_id      INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    created_at   REAL NOT NULL,
    PRIMARY KEY (user_id, post_id)
);

CREATE INDEX IF NOT EXISTS idx_likes_post ON likes(post_id);

CREATE TABLE IF NOT EXISTS comments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id      INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body         TEXT NOT NULL,
    created_at   REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_comments_post_created ON comments(post_id, created_at ASC, id ASC);
