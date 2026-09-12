"""Demo-mode configuration, read from the environment and the manifest.

``DEMO_MODE`` is the kill switch: unset or false and nothing in this package
does anything — the mint route 404s and the banner never renders.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from ..config import BASE_DIR

MANIFEST_PATH = BASE_DIR / "demo" / "demo.json"

_TRUE = {"1", "true", "yes", "on"}


def demo_mode() -> bool:
    """The kill switch. Default off, including in production."""
    return (os.getenv("DEMO_MODE") or "").strip().lower() in _TRUE


def demo_username() -> str:
    return (os.getenv("DEMO_USERNAME") or "demo").strip() or "demo"


def demo_password() -> str:
    """Password of the demo account.

    Published on the landing card, so it guards nothing — the real boundary is
    the read-only middleware plus the frozen snapshot this process serves.
    """
    return os.getenv("DEMO_PASSWORD") or "demo"


@lru_cache(maxsize=1)
def _manifest() -> dict[str, object]:
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def snapshot_date() -> str:
    """ISO date the fixture data was captured. Env wins over the manifest."""
    explicit = (os.getenv("DEMO_SNAPSHOT_DATE") or "").strip()
    if explicit:
        return explicit
    data = _manifest().get("data")
    if isinstance(data, dict):
        return str(data.get("snapshot") or "")
    return ""


_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def snapshot_label() -> str:
    """Human-readable snapshot line for the banner, e.g. ``Snapshot: 12 September 2026``.

    Formatted by hand rather than with ``strftime``: the no-pad day directive
    differs between Windows (``%#d``) and glibc (``%-d``), and this string is
    rendered on both.
    """
    iso = snapshot_date()
    if not iso:
        return "Frozen snapshot"
    try:
        from datetime import date

        d = date.fromisoformat(iso)
    except ValueError:
        return f"Snapshot: {iso}"
    return f"Snapshot: {d.day} {_MONTHS[d.month - 1]} {d.year}"


def source_url() -> str:
    """Where a visitor goes to see the real thing. Blank hides the link."""
    return (os.getenv("DEMO_SOURCE_URL") or "https://noeinsolutions.com/builds.html").strip()


def db_path_override() -> Path | None:
    """The snapshot this process serves, when ``CONGRESS_DB_PATH`` points at one."""
    raw = (os.getenv("CONGRESS_DB_PATH") or "").strip()
    return Path(raw) if raw else None
