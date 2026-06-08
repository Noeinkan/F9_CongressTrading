"""API-layer configuration read from environment variables.

Auth uses ``APP_USERNAME`` / ``APP_PASSWORD`` via ``src.config`` plus a few
API-only session and CORS knobs.
"""
from __future__ import annotations

import hashlib
import os

from ..config import app_password


def session_secret() -> str:
    """Secret used to sign the session cookie.

    Prefers ``APP_SESSION_SECRET``. Falls back to a value derived from the app
    password so single-secret deployments keep working; if neither is set (auth
    disabled), a fixed dev secret is used.
    """
    explicit = (os.getenv("APP_SESSION_SECRET") or "").strip()
    if explicit:
        return explicit
    pw = app_password().strip()
    if pw:
        return hashlib.sha256(f"f9-session::{pw}".encode("utf-8")).hexdigest()
    return "f9-congress-trading-dev-secret-change-me"


def session_cookie_name() -> str:
    return (os.getenv("APP_SESSION_COOKIE") or "f9_session").strip() or "f9_session"


def session_https_only() -> bool:
    """Mark the cookie Secure (HTTPS-only). Default off for local dev."""
    v = (os.getenv("APP_SESSION_HTTPS_ONLY") or "").strip().lower()
    return v in {"1", "true", "yes", "on"}


def session_max_age_seconds() -> int:
    raw = (os.getenv("APP_SESSION_MAX_AGE") or "").strip()
    if raw.isdigit():
        return int(raw)
    return 14 * 24 * 3600  # 14 days


def cors_origins() -> list[str]:
    """Comma-separated allowed origins for the frontend dev server.

    Defaults to the common Vite dev origins. With credentialed cookie auth the
    browser requires explicit origins (``*`` is not allowed alongside cookies).
    """
    raw = (os.getenv("APP_CORS_ORIGINS") or "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
