"""Authentication: signed httpOnly session cookie (Starlette SessionMiddleware)."""
from __future__ import annotations

import hmac

from fastapi import Request
from fastapi.exceptions import HTTPException

from ..config import app_auth_required, app_password, app_username

_SESSION_USER_KEY = "user"


def verify_credentials(username: str, password: str) -> bool:
    """Constant-time check against APP_USERNAME / APP_PASSWORD."""
    expected_password = app_password()
    if not expected_password.strip():
        return True

    if not hmac.compare_digest(password.encode("utf-8"), expected_password.encode("utf-8")):
        return False

    expected_username = app_username()
    if not expected_username:
        return True

    return hmac.compare_digest(username.encode("utf-8"), expected_username.encode("utf-8"))


def login_session(request: Request, username: str) -> None:
    request.session[_SESSION_USER_KEY] = username or "dashboard"


def logout_session(request: Request) -> None:
    request.session.pop(_SESSION_USER_KEY, None)


def current_user(request: Request) -> str | None:
    """The signed-in username, or None. When auth is disabled, returns 'anonymous'."""
    if not app_auth_required():
        return "anonymous"
    return request.session.get(_SESSION_USER_KEY)


def require_auth(request: Request) -> str:
    """FastAPI dependency: 401 unless authenticated (or auth disabled)."""
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
