"""Demo endpoints: the status probe and the one-click sign-in.

``POST /api/demo/session`` is the security boundary — with ``DEMO_MODE`` off it
404s, so no demo session can be minted on a production deployment no matter what
the frontend asks for. ``GET /api/demo/status`` answers on both, returning
``{"enabled": false}`` when the demo is off: it leaks nothing, and it lets the
same frontend build serve the private app and the public demo.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.exceptions import HTTPException

from ..api.security import login_session
from .config import (
    demo_mode,
    demo_username,
    snapshot_date,
    snapshot_label,
    source_url,
)

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
def demo_status() -> dict[str, object]:
    """What the banner and the nav need to know. Safe to call when the demo is off."""
    if not demo_mode():
        return {"enabled": False}
    return {
        "enabled": True,
        "readOnly": True,
        "notice": NOTICE,
        "snapshotDate": snapshot_date(),
        "snapshotLabel": snapshot_label(),
        "hiddenRoutes": list(HIDDEN_ROUTES),
        "sourceUrl": source_url(),
    }


@router.post("/session")
def mint_demo_session(request: Request) -> dict[str, object]:
    """Sign the visitor in as the demo user, so the landing link is one click.

    The login gate stays in front of anyone arriving at the root URL; this is the
    door the ``Try the demo`` link on the landing page opens. 404 — not 403 —
    when the demo is off, so a production deployment does not advertise that the
    route exists at all.
    """
    if not demo_mode():
        raise HTTPException(status_code=404, detail="Not Found")
    user = demo_username()
    login_session(request, user)
    return {"user": user, "demo": True, "snapshotDate": snapshot_date()}
