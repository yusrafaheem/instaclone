from __future__ import annotations

from .base import ApiError, BaseHandler


class MeHandler(BaseHandler):
    """Lets the frontend ask "am I logged in, and as whom" on page load
    without re-parsing the JWT client-side."""

    async def get(self) -> None:
        if self.current_user_id is None:
            raise ApiError(401, reason="not authenticated")
        self.write_json({"user_id": self.current_user_id, "username": self.current_username})


class HealthHandler(BaseHandler):
    """Unauthenticated liveness check, the kind a load balancer or
    container orchestrator would poll -- deliberately skips the DB and
    cache so it stays fast and cheap even if those are struggling."""

    async def get(self) -> None:
        self.write_json({"status": "ok"})
