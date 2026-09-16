"""The front door: nothing past it without a verified email and a running session.

Flow, as a visitor meets it (the pages are React routes; this is their API):

1. Any ``/api/*`` call without an access cookie gets ``401 DEMO_SIGNED_OUT``;
   the app sends the browser to ``/access``.
2. ``POST /api/demo/access/request`` sends one email holding a 6-digit code and a
   link, both usable once for ``DEMO_CODE_MINUTES``.
3. The code (``POST .../code``) or the link (``GET .../link`` shows who it is for,
   ``POST .../link`` signs in) sets an opaque ``HttpOnly`` cookie whose hash is a
   row in ``grants``. The link never signs in on a GET: mail scanners open every
   link in an email, and would spend it before its owner clicked.
4. The first sign-in starts the session clock; signing in again inside the window
   resumes it. While it runs every request passes, and what the person opens is
   recorded against the address.
5. When it ends every call gets ``403 DEMO_EXPIRED`` -- never a login page -- and
   asking for a code again mails that inbox an "ended" note instead, so the page
   never reveals which addresses have had a session.

The middleware is registered last, so it runs first: a refused browser never
reaches the session cookie, the routers or the snapshot.
"""
from __future__ import annotations

import logging
from urllib.parse import unquote, urlencode

from fastapi import APIRouter, Request
from fastapi.exceptions import HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from . import emails, messages
from .mailer import MailError
from .service import ACCESS_COOKIE, DemoAccess, client_ip, is_https, public_base
from .store import DAY, Visitor

logger = logging.getLogger(__name__)

# Reachable without access: the sign-in API, the status probe the sign-in page
# reads, the health check, and the owner's page (it has its own token).
_OPEN_EXACT = {"/api/health", "/api/demo/status", "/admin", "/robots.txt"}
_OPEN_PREFIXES = ("/api/demo/access/", "/admin/")

# Page-level reads worth a line in the usage log; everything else a page loads is noise.
_PAGE_ENDPOINTS = {
    "/api/home/summary": "home",
    "/api/senate/summary": "senate",
    "/api/raw/transactions": "raw",
    "/api/review/summary": "review",
    "/api/patterns/summary": "patterns",
    "/api/members/summary": "members",
    "/api/tickers": "tickers",
}


def is_open_path(path: str) -> bool:
    return path in _OPEN_EXACT or path.startswith(_OPEN_PREFIXES)


def classify_usage(method: str, path: str, query: dict[str, str]) -> tuple[str, str] | None:
    """``(kind, detail)`` for a read worth recording, or None."""
    if method.upper() != "GET":
        return None
    path = path.rstrip("/")
    if path in _PAGE_ENDPOINTS:
        return "page", _PAGE_ENDPOINTS[path]
    parts = path.split("/")
    # /api/members/<member>/..., /api/tickers/<ticker>[/...]
    if len(parts) >= 4 and parts[1] == "api" and parts[2] in ("members", "tickers") and parts[3] != "summary":
        name = unquote(parts[3]).strip()
        if name:
            return ("member" if parts[2] == "members" else "ticker"), name[:80]
    if path == "/api/home/ticker_drilldown" and query.get("ticker"):
        return "ticker", query["ticker"].strip().upper()[:16]
    return None


def _refusal(status: int, code: str, detail: str, **extra: object) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code, "detail": detail, **extra},
        headers={"Cache-Control": "no-store"},
    )


def expired_response(access: DemoAccess, visitor: Visitor) -> JSONResponse:
    s = access.settings
    if visitor.revoked_at:
        detail = "Demo access for this address has been switched off."
    else:
        detail = f"Your {s.session_minutes} minutes with the demo are up."
    return _refusal(403, "DEMO_EXPIRED", detail, revoked=bool(visitor.revoked_at), contactEmail=s.contact_email)


class DemoAccessMiddleware(BaseHTTPMiddleware):
    """Refuse every gated request that does not carry a running session."""

    def __init__(self, app, access: DemoAccess) -> None:
        super().__init__(app)
        self.access = access

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method.upper() == "OPTIONS" or is_open_path(path):
            return await call_next(request)

        access = self.access
        visitor = await run_in_threadpool(access.visitor_for, request)
        now = access.store.now()
        status = visitor.status(now) if visitor is not None else "signed_out"
        if visitor is not None and status == "active":
            email = visitor.email
            request.scope["demo_email"] = email
            request.scope["demo_record"] = lambda kind, detail=None: access.record(email, kind, detail)
            usage = classify_usage(request.method, path, dict(request.query_params))
            if usage is not None:
                await run_in_threadpool(access.record, email, usage[0], usage[1], dedupe=True)
            return await call_next(request)
        if visitor is not None and status in ("ended", "revoked"):
            return expired_response(access, visitor)
        return _refusal(401, "DEMO_SIGNED_OUT", "Sign in with your email to use the demo.")


# --------------------------------------------------------------------------
# Sign-in API
# --------------------------------------------------------------------------

router = APIRouter(prefix="/api/demo/access", tags=["demo"])


class RequestBody(BaseModel):
    email: str = ""


class CodeBody(BaseModel):
    email: str = ""
    code: str = ""


class LinkBody(BaseModel):
    t: str = ""


def _access(request: Request) -> DemoAccess:
    access = getattr(request.app.state, "demo_access", None)
    if access is None:
        raise HTTPException(status_code=404, detail="Not Found")
    return access


def _signed_in(access: DemoAccess, request: Request, token: str, visitor: Visitor, first_session: bool) -> JSONResponse:
    response = JSONResponse({"status": "ok", "access": access.payload(visitor)}, headers={"Cache-Control": "no-store"})
    now = access.store.now()
    # Outlives the session, so the browser is told "your time is up", not "sign in".
    lifetime = max(0.0, (visitor.expires_at or now) - now) + 30 * DAY
    response.set_cookie(
        ACCESS_COOKIE, token, max_age=int(lifetime), httponly=True, samesite="lax", secure=is_https(request), path="/"
    )
    if first_session:
        access.notify_signup(visitor, request)
    return response


@router.post("/request")
def request_code(body: RequestBody, request: Request) -> JSONResponse:
    access = _access(request)
    s = access.settings
    address = emails.clean(body.email)
    if not emails.is_valid(address):
        return _refusal(400, "INVALID_EMAIL", "That does not look like an email address.")
    if emails.is_blocked(address, s.blocked_domains):
        return _refusal(400, "BLOCKED_DOMAIN", "Throwaway inboxes cannot start a session. Use an address you actually read.")

    store = access.store
    email = emails.canonical(address)
    now = store.now()
    ip = client_ip(request)
    if store.codes_sent_since(now - 3600, email=email) >= s.codes_per_email_per_hour:
        return _refusal(
            429, "RATE_LIMITED",
            "Several codes have already gone to this address in the last hour. Use the newest one, or ask again later.",
        )
    if store.codes_sent_since(now - 3600) >= s.codes_per_hour or store.codes_sent_since(now - DAY) >= s.codes_per_day:
        return _refusal(429, "RATE_LIMITED", "The demo is sending a lot of sign-in emails right now. Try again later.")
    existing = store.visitor(email)
    if existing is None and store.new_visitors_from_ip_since(ip, now - DAY) >= s.signups_per_ip_per_day:
        return _refusal(
            429, "RATE_LIMITED",
            f"Too many new addresses have started a session from your connection today. "
            f"Try again tomorrow, or write to {s.contact_email}.",
        )

    code, link = store.create_code(
        email=email, address=address, ip=ip, user_agent=request.headers.get("user-agent", ""), minutes=s.code_minutes
    )
    ended = existing is not None and existing.status(now) in ("ended", "revoked")
    if ended:
        assert existing is not None
        mail = messages.ended_mail(s, to=address, visitor=existing)
    else:
        link_url = f"{public_base(s, request)}/access/verify?{urlencode({'t': link})}"
        mail = messages.code_mail(s, to=address, code=code, link=link_url)
    try:
        access.mailer.send(mail)
    except MailError:
        store.cancel_code(link)
        return _refusal(
            503, "MAIL_FAILED",
            f"The sign-in email could not be sent just now. Try again in a minute; if it keeps failing, "
            f"write to {s.contact_email}.",
        )
    store.sent(email, "ended_note_sent" if ended else "code_sent")
    # The same answer either way: the page never says which addresses have had a session.
    return JSONResponse(
        {"status": "sent", "address": address, "codeMinutes": s.code_minutes}, headers={"Cache-Control": "no-store"}
    )


def _verification_response(access: DemoAccess, request: Request, result) -> JSONResponse:
    if result.status == "ok":
        return _signed_in(access, request, result.token, result.visitor, result.first_session)
    if result.status == "ended":
        return expired_response(access, result.visitor)
    return None  # type: ignore[return-value]


@router.post("/code")
def verify_code(body: CodeBody, request: Request) -> JSONResponse:
    access = _access(request)
    s = access.settings
    address = emails.clean(body.email)
    if not emails.is_valid(address):
        return _refusal(400, "CODE_DEAD", "Ask for a new sign-in code.")
    result = access.store.verify_code(
        emails.canonical(address), body.code, session_minutes=s.session_minutes, max_attempts=s.code_attempts
    )
    response = _verification_response(access, request, result)
    if response is not None:
        return response
    if result.status == "wrong":
        tries = "1 try" if result.attempts_left == 1 else f"{result.attempts_left} tries"
        return _refusal(400, "WRONG_CODE", f"That code is not right. {tries} left.", attemptsLeft=result.attempts_left)
    if result.status == "used_up":
        return _refusal(400, "CODE_DEAD", "Too many wrong codes. Ask for a new one.")
    return _refusal(400, "CODE_DEAD", "That code has expired or was already used. Ask for a new one.")


_LINK_DEAD = "That link has expired. Sign-in links work once, for a few minutes."


@router.get("/link")
def link_info(request: Request, t: str = "") -> JSONResponse:
    """Who a link is for. Does not sign in and does not spend the link."""
    access = _access(request)
    token = t.strip()
    email = access.store.link_email(token) if token and len(token) <= 128 else None
    visitor = access.store.visitor(email) if email else None
    if visitor is None:
        return _refusal(410, "LINK_DEAD", _LINK_DEAD)
    return JSONResponse({"address": visitor.address}, headers={"Cache-Control": "no-store"})


@router.post("/link")
def verify_link(body: LinkBody, request: Request) -> JSONResponse:
    access = _access(request)
    token = body.t.strip()
    if not token or len(token) > 128:
        return _refusal(410, "LINK_DEAD", _LINK_DEAD)
    result = access.store.verify_link(token, session_minutes=access.settings.session_minutes)
    response = _verification_response(access, request, result)
    if response is not None:
        return response
    return _refusal(410, "LINK_DEAD", _LINK_DEAD)


@router.post("/signout")
def sign_out(request: Request) -> JSONResponse:
    access = _access(request)
    access.store.revoke_grant(request.cookies.get(ACCESS_COOKIE))
    response = JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})
    response.delete_cookie(ACCESS_COOKIE, path="/")
    return response


@router.api_route("/{rest:path}", methods=["GET", "POST"], include_in_schema=False)
def unknown(rest: str) -> JSONResponse:
    # /api/demo/access/* is open, so anything unknown under it 404s here.
    raise HTTPException(status_code=404, detail="Not Found")
