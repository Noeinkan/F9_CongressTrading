"""Locked features and the read-only guard for demo mode.

Two refusals, in this order:

1. **Locked** (``tiers.LOCKED_FEATURES``) — the CSV downloads and the Review-queue
   actions. Visible in the app, refused here with ``DEMO_LOCKED`` and the feature,
   so the wall can say what the visitor reached. Recorded against the address.
2. **Read-only** — every other write to ``/api/*``. Contract rule: what one
   visitor does must not change what the next one sees. A middleware rather than
   a per-router dependency, so a mutating route added next year is covered
   without anyone remembering to cover it.

Off entirely when ``DEMO_MODE`` is off — the middleware is still installed, but
every request falls straight through.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import demo_mode
from .tiers import locked_feature

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Writes that are not data. Signing in and out is session handling, and blocking
# sign-out would trap the visitor inside the demo. /api/login is reachable only
# past the email gate, and the demo deployment sets no APP_PASSWORD at all.
ALLOWED_WRITE_PATHS = frozenset({"/api/login", "/api/logout"})
ALLOWED_WRITE_PREFIXES = ("/api/demo/access/",)

MESSAGE = (
    "This is a read-only public demo, so nothing here can be changed. "
    "The full dashboard resolves review-queue rows and re-runs the "
    "disclosure ingest — both are switched off on this copy."
)


class DemoReadOnlyMiddleware(BaseHTTPMiddleware):
    """Refuse locked features and every state-changing API call while the demo is live."""

    async def dispatch(self, request: Request, call_next):
        if not demo_mode():
            return await call_next(request)
        path = request.url.path
        method = request.method.upper()
        feature = locked_feature(method, path)
        if feature is not None:
            record = request.scope.get("demo_record")
            if record is not None:
                record("locked", feature.key)
            return JSONResponse(
                status_code=403,
                content={"code": "DEMO_LOCKED", "feature": feature.key, "detail": feature.message},
            )
        if (
            method not in SAFE_METHODS
            and path.startswith("/api/")
            and path.rstrip("/") not in ALLOWED_WRITE_PATHS
            and not path.startswith(ALLOWED_WRITE_PREFIXES)
        ):
            return JSONResponse(
                status_code=403,
                content={"code": "DEMO_READ_ONLY", "detail": MESSAGE, "demo": True, "readOnly": True},
            )
        return await call_next(request)
