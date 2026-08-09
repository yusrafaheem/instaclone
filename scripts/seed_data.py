#!/usr/bin/env python3
"""Populate the database with a realistic volume of users, posts, and
follows -- so the load test in loadtest/load_test.py exercises a feed
query that actually has to join and filter real rows, not an empty
table. One bcrypt hash is computed once and reused for every seed user
(all seed accounts share the password "hunter22222") since the point is
data volume, not re-testing bcrypt's cost per user.

Run: python3 -m scripts.seed_data --users 500 --posts-per-user 3 --follows-per-user 15
"""

from __future__ import annotations

import argparse
import random
import time

from app import auth, db, settings

SEED_PASSWORD = "hunter22222"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=500)
    parser.add_argument("--posts-per-user", type=int, default=3)
    parser.add_argument("--follows-per-user", type=int, default=15)
    parser.add_argument("--seed", type=int, default=42, help="random seed for reproducibility")
    args = parser.parse_args()

    random.seed(args.seed)
    db.init_db()
    conn = db.get_connection()

    print(f"DB path: {settings.DB_PATH}")
    t0 = time.time()

    password_hash = auth.hash_password(SEED_PASSWORD)

    print(f"Creating {args.users} users...")
    now = time.time()
    user_rows = [
        (f"user{i}", f"user{i}@example.com", password_hash, "", now)
        for i in range(args.users)
    ]
    conn.executemany(
        "INSERT INTO users (username, email, password_hash, bio, created_at) VALUES (?, ?, ?, ?, ?)",
        user_rows,
    )
    conn.commit()
    user_ids = [
        row["id"]
        for row in conn.execute("SELECT id FROM users ORDER BY id").fetchall()
    ]

    print(f"Creating ~{args.users * args.posts_per_user} posts...")
    post_rows = []
    for uid in user_ids:
        n_posts = random.randint(max(0, args.posts_per_user - 2), args.posts_per_user + 2)
        for p in range(n_posts):
            created_at = now - random.uniform(0, 60 * 60 * 24 * 30)  # spread over 30 days
            post_rows.append(
                (uid, f"seed post {p} from user {uid}", "uploads/seed.jpg", "thumbs/seed.jpg", created_at)
            )
    conn.executemany(
        "INSERT INTO posts (user_id, caption, image_path, thumb_path, created_at) VALUES (?, ?, ?, ?, ?)",
        post_rows,
    )
    conn.commit()

    print(f"Creating ~{args.users * args.follows_per_user} follow edges...")
    follow_rows = set()
    for uid in user_ids:
        targets = random.sample(user_ids, min(args.follows_per_user, len(user_ids) - 1))
        for target in targets:
            if target != uid:
                follow_rows.add((uid, target, now))
    conn.executemany(
        "INSERT OR IGNORE INTO follows (follower_id, followee_id, created_at) VALUES (?, ?, ?)",
        list(follow_rows),
    )
    conn.commit()

    elapsed = time.time() - t0
    counts = {
        "users": conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"],
        "posts": conn.execute("SELECT COUNT(*) AS n FROM posts").fetchone()["n"],
        "follows": conn.execute("SELECT COUNT(*) AS n FROM follows").fetchone()["n"],
    }
    print(f"Done in {elapsed:.1f}s: {counts}")
    print(f"All seed users share the password: {SEED_PASSWORD!r}")


if __name__ == "__main__":
    main()
