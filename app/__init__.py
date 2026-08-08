"""instaclone: an Instagram-style photo feed, built to demonstrate the
same architectural decisions the real thing makes -- async request
handling, cursor-based pagination, cache-aside feed reads, and indexed
queries -- without requiring a database server, cache server, or npm/pip
network access to run.

See README.md for the honest list of what's substituted for what (and
why) versus a production deployment.
"""

__version__ = "0.1.0"
