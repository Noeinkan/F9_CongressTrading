"""Demo status: what the banner, the nav, the sign-in page and the wall need to know.

``GET /api/demo/status`` answers on every deployment, returning
``{"enabled": false}`` when the demo is off: it leaks nothing, and it lets the
same frontend build serve the private app and the public demo. It is never behind
the email gate, because the sign-in page reads it.

There is no sign-in route here any more. The one-click door (``POST
/api/demo/session``) is gone: the way in is a verified email
(:mod:`src.demo.access.gate`).
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from .access.settings import CONTACT_EMAIL, AccessSettings
from .config import demo_mode, snapshot_date, snapshot_label, source_url
from .tiers import public_locked

router = APIRouter(prefix="/api/demo", tags=["demo"])

# Pages with nothing behind them in the frozen snapshot. The Executive (OGE)
# route needs 278-T / 278e filings that this capture has none of, and a demo
# whose nav leads to a blank page reads as broken rather than as limited.
HIDDEN_ROUTES = ("/executive",)

NOTICE = (
    "You are in the public demo: a frozen copy of the data, read-only, "
    "with the disclosure ingest switched off."
)


@router.get("/status")
async def demo_status(request: Request) -> dict[str, object]:
    """Safe to call when the demo is off, and without signing in."""
    if not demo_mode():
        return {"enabled": False}
    access = getattr(request.app.state, "demo_access", None)
    if access is not None:
        visitor = await run_in_threadpool(access.visitor_for, request)
        settings = access.settings
        access_payload: dict[str, object] = access.payload(visitor)
    else:
        settings = AccessSettings.from_env()
        access_payload = {"gate": False}
    return {
        "enabled": True,
        "readOnly": True,
        "notice": NOTICE,
        "snapshotDate": snapshot_date(),
        "snapshotLabel": snapshot_label(),
        "hiddenRoutes": list(HIDDEN_ROUTES),
        "sourceUrl": source_url(),
        "contactEmail": settings.contact_email or CONTACT_EMAIL,
        "session": {"minutes": settings.session_minutes},
        "locked": public_locked(),
        "access": access_payload,
    }
