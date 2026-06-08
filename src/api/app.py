"""FastAPI application factory for the congress-trading API.

Mounts session-cookie auth, CORS for the Vite dev server, and the per-page
routers. No Streamlit anywhere in this layer.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from ..config import DB_PATH, app_auth_required
from ..db import get_connection, init_db
from . import settings
from .repository import polygon_daily_bar_cache_size
from .routers import admin, home, members, patterns, raw, review, tickers
from .security import current_user, login_session, logout_session, require_auth


class LoginRequest(BaseModel):
    username: str = ""
    password: str = ""


def create_app() -> FastAPI:
    app = FastAPI(
        title="Congress Trading API",
        version="0.1.0",
        description="JSON analytics API backing the congress-trading dashboard.",
    )

    # Signed httpOnly session cookie (Starlette sets HttpOnly + SameSite=lax).
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret(),
        session_cookie=settings.session_cookie_name(),
        max_age=settings.session_max_age_seconds(),
        https_only=settings.session_https_only(),
        same_site="lax",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", tags=["meta"])
    def health() -> dict[str, object]:
        cache_rows = 0
        try:
            conn = get_connection(DB_PATH)
            try:
                init_db(conn)
                cache_rows = polygon_daily_bar_cache_size(conn)
            finally:
                conn.close()
        except OSError:
            cache_rows = 0
        return {
            "status": "ok",
            "auth_required": app_auth_required(),
            "polygon_cache_rows": cache_rows,
        }

    @app.post("/api/login", tags=["auth"])
    def login(payload: LoginRequest, request: Request) -> dict[str, object]:
        from .security import verify_credentials

        if not verify_credentials(payload.username.strip(), payload.password):
            raise HTTPException(status_code=401, detail="Invalid username or password.")
        username = payload.username.strip() or "dashboard"
        login_session(request, username)
        return {"user": username, "auth_required": app_auth_required()}

    @app.post("/api/logout", tags=["auth"])
    def logout(request: Request) -> dict[str, bool]:
        logout_session(request)
        return {"ok": True}

    @app.get("/api/me", tags=["auth"])
    def me(request: Request, user: str = Depends(require_auth)) -> dict[str, object]:
        return {"user": user, "auth_required": app_auth_required()}

    @app.get("/api/session", tags=["auth"])
    def session_status(request: Request) -> dict[str, object]:
        """Non-401 probe the frontend can call on load to decide login state."""
        return {
            "authenticated": current_user(request) is not None,
            "auth_required": app_auth_required(),
            "user": current_user(request),
        }

    app.include_router(admin.router)
    app.include_router(home.router)
    app.include_router(raw.router)
    app.include_router(review.router)
    app.include_router(patterns.router)
    app.include_router(members.router)
    app.include_router(tickers.router)
    return app


app = create_app()
