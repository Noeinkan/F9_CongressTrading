"""Read-only guard for demo mode.

Contract rule: what one visitor does must not change what the next one sees. The
dashboard has five mutating endpoints (three review-queue actions, two refresh
controls) and one of them starts an ingest run, so the guard is a middleware
rather than a per-router dependency: a new mutating route added later is covered
without anyone remembering to cover it.

Off entirely when ``DEMO_MODE`` is off — the middleware is still installed, but
every request falls straight through.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import demo_mode

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# The only writes a demo visitor is allowed: signing in and out. Session
# handling is not data, and blocking it would lock the visitor out of the demo.
ALLOWED_WRITE_PATHS = frozenset(
    {
        "/api/login",
        "/api/logout",
        "/api/demo/session",
    }
)

MESSAGE = (
    "This is a read-only public demo, so nothing here can be changed. "
    "The full dashboard resolves review-queue rows and re-runs the "
    "disclosure ingest — both are switched off on this copy."
)


class DemoReadOnlyMiddleware(BaseHTTPMiddleware):
    """Reject every state-changing API call while the demo is live."""

    async def dispatch(self, request: Request, call_next):
        if (
            demo_mode()
            and request.method.upper() not in SAFE_METHODS
            and request.url.path.rstrip("/") not in ALLOWED_WRITE_PATHS
            and request.url.path.startswith("/api/")
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": MESSAGE, "demo": True, "readOnly": True},
            )
        return await call_next(request)
