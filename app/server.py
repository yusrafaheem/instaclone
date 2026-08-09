"""Application wiring: routes, static file serving, and the entrypoint.

Tornado's own IOLoop is the concurrency model here -- a single process,
single event-loop thread accepts and multiplexes many simultaneous client
connections without one thread per connection, and blocking work is
pushed to the thread pool in handlers/base.py. That combination (async
I/O for the network layer, a thread pool for CPU/blocking work) is the
same shape Instagram's own infrastructure uses under the hood, just at a
scale this single-process prototype doesn't attempt to match -- see
README.md for what would actually change to go from "this" to "handles
Instagram's real traffic."
"""

from __future__ import annotations

import logging

import tornado.ioloop
import tornado.web

from . import db, settings
from .handlers.auth_handlers import LoginHandler, SignupHandler
from .handlers.feed_handlers import ExploreFeedHandler, FollowingFeedHandler
from .handlers.misc_handlers import HealthHandler, MeHandler
from .handlers.post_handlers import PostCollectionHandler, PostDetailHandler
from .handlers.profile_handlers import BioHandler, ProfileHandler
from .handlers.social_handlers import CommentHandler, FollowHandler, LikeHandler

logger = logging.getLogger("instaclone")


def make_app(static_dir: str) -> tornado.web.Application:
    settings.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    return tornado.web.Application(
        [
            (r"/api/health", HealthHandler),
            (r"/api/me", MeHandler),
            (r"/api/auth/signup", SignupHandler),
            (r"/api/auth/login", LoginHandler),
            (r"/api/posts", PostCollectionHandler),
            (r"/api/posts/([0-9]+)", PostDetailHandler),
            (r"/api/posts/([0-9]+)/like", LikeHandler),
            (r"/api/posts/([0-9]+)/comments", CommentHandler),
            (r"/api/feed", FollowingFeedHandler),
            (r"/api/feed/explore", ExploreFeedHandler),
            (r"/api/users/me/bio", BioHandler),
            (r"/api/users/([a-zA-Z0-9_.]+)", ProfileHandler),
            (r"/api/users/([a-zA-Z0-9_.]+)/follow", FollowHandler),
            (
                r"/media/(.*)",
                tornado.web.StaticFileHandler,
                {"path": str(settings.MEDIA_DIR)},
            ),
            (
                r"/(.*)",
                tornado.web.StaticFileHandler,
                {"path": static_dir, "default_filename": "index.html"},
            ),
        ],
        debug=False,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    db.init_db()

    import pathlib

    static_dir = str(pathlib.Path(__file__).resolve().parent.parent / "static")
    app = make_app(static_dir)
    app.listen(settings.SERVER_PORT)
    logger.info("instaclone listening on http://localhost:%d", settings.SERVER_PORT)
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
