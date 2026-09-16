"""``/admin`` -- who signed up, what they opened, and the three things to do about it.

Unlocked by ``DEMO_ADMIN_TOKEN`` (at least 24 characters, kept in the server's
``.env``). With no token set every ``/admin`` URL is a 404, so a fresh deployment
exposes nothing. nginx forwards ``/admin`` to the API (``.deploy/site-nginx.conf``);
the page is server-rendered and has nothing to do with the React app.

Sign-in is a form, never a token in the URL, so the token never lands in the nginx
access log. The cookie holds an HMAC of the token rather than the token itself;
changing the token signs every admin browser out. It is ``SameSite=Strict`` and
scoped to ``/admin``, which is what stops another site from submitting the
grant/revoke/delete forms on the owner's behalf.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import threading
import time
from collections import deque
from urllib.parse import parse_qs, quote

from fastapi import APIRouter, Request
from fastapi.exceptions import HTTPException
from starlette.responses import HTMLResponse, RedirectResponse, Response

from ..tiers import LOCKED_FEATURES
from .messages import PRODUCT, esc, fmt_time
from .service import DemoAccess, client_ip, is_https

ADMIN_COOKIE = "f9_demo_admin"
_HEADERS = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"}

_CSS = """
:root{color-scheme:light dark;--bg:#f8f9fa;--panel:#fff;--line:#dee2e6;--text:#212529;--muted:#6c757d;--accent:#fd7e14;
  --good:#2b8a3e;--bad:#c92a2a;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
@media (prefers-color-scheme:dark){:root{--bg:#1a1b1e;--panel:#25262b;--line:#373a40;--text:#e9ecef;--muted:#909296;--good:#69db7c;--bad:#ff8787}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 var(--sans);padding:24px 16px 48px}
main{max-width:1320px;margin:0 auto}
main.narrow{max-width:420px;margin-top:10vh}
.brand{font:600 12px/1 var(--mono);letter-spacing:.12em;color:var(--accent);text-transform:uppercase;margin:0 0 16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:22px}
h1{font-size:20px;margin:0 0 12px}h2{font-size:15px;margin:22px 0 10px}
label{display:block;font-weight:600;margin:0 0 6px}
input[type=password]{width:100%;padding:10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--text);font:15px var(--sans)}
button{cursor:pointer;border:0;border-radius:6px;background:var(--accent);color:#fff;font:600 14px var(--sans);padding:10px 14px;margin-top:12px}
.alert{border-left:3px solid var(--good);background:var(--panel);padding:8px 12px;margin:0 0 14px}
.alert.bad{border-left-color:var(--bad)}
.bar{display:flex;gap:12px;flex-wrap:wrap;align-items:center;justify-content:space-between;margin:0 0 14px}
.bar h1{margin:0}.bar .links{display:flex;gap:14px;align-items:center}
.bar button{margin:0;background:none;color:var(--accent);padding:0;text-decoration:underline}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:0 0 8px}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 14px}
.tile b{display:block;font:600 22px/1.2 var(--mono)}.tile span{font-size:12px;color:var(--muted)}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
td.n{text-align:right;font-family:var(--mono)}
.status{font:600 11px/1 var(--mono);padding:3px 6px;border-radius:4px;text-transform:uppercase;border:1px solid var(--line)}
.status.active{color:var(--good)}.status.revoked{color:var(--bad)}
td form{display:inline}
td form button{margin:0 6px 0 0;padding:4px 8px;font-size:12px;background:none;color:var(--text);border:1px solid var(--line)}
td form button.danger{color:var(--bad)}
.muted{color:var(--muted)}
"""


def _page(title: str, body: str, *, narrow: bool = False) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex,nofollow">'
        f"<title>{esc(title)} — {PRODUCT} demo</title><style>{_CSS}</style></head><body>"
        f'<main class="{"narrow" if narrow else ""}"><p class="brand">{PRODUCT} · demo admin</p>{body}</main>'
        "</body></html>"
    )


def _csv_cell(value: object) -> object:
    # A cell starting with = + - @ runs as a formula when the CSV opens in a
    # spreadsheet; the addresses in it were typed by strangers.
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


class _LoginLimiter:
    """At most ``limit`` sign-in attempts per IP per ``window`` seconds."""

    def __init__(self, limit: int = 5, window: float = 900) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        """Count one attempt. True means refuse it."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return True
            hits.append(now)
            if len(self._hits) > 1000:
                self._hits = {k: v for k, v in self._hits.items() if v}
            return False


_limiter = _LoginLimiter()

router = APIRouter(include_in_schema=False)


def _access(request: Request) -> DemoAccess:
    access = getattr(request.app.state, "demo_access", None)
    if access is None or not access.settings.admin_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    return access


def _cookie_value(access: DemoAccess) -> str:
    return hmac.new(access.settings.admin_token.encode(), b"f9-demo-admin-v1", hashlib.sha256).hexdigest()


def _authed(access: DemoAccess, request: Request) -> bool:
    return hmac.compare_digest(request.cookies.get(ADMIN_COOKIE, ""), _cookie_value(access))


async def _form(request: Request) -> dict[str, str]:
    raw = (await request.body())[:10_000].decode("utf-8", errors="replace")
    return {key: values[0] for key, values in parse_qs(raw, keep_blank_values=True).items()}


def _html(body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(body, status_code=status, headers=_HEADERS)


def _login_page(error: str | None = None, status: int = 200) -> HTMLResponse:
    alert = f'<p class="alert bad" role="alert">{esc(error)}</p>' if error else ""
    body = (
        '<div class="card"><h1>Demo admin</h1>'
        f"{alert}"
        '<form method="post" action="/admin/login">'
        '<label for="token">Admin token</label>'
        '<input id="token" name="token" type="password" autocomplete="current-password" required autofocus>'
        '<button type="submit">Open</button></form></div>'
    )
    return _html(_page("Admin", body, narrow=True), status)


def _redirect(location: str) -> RedirectResponse:
    return RedirectResponse(location, status_code=303, headers=_HEADERS)


@router.get("/admin")
def admin_home(request: Request) -> HTMLResponse:
    access = _access(request)
    if not _authed(access, request):
        return _login_page()
    s = access.settings
    store = access.store
    summary = store.summary()
    rows = store.visitor_rows()
    events = store.recent_events(100)
    done = request.query_params.get("done", "")

    tiles = "".join(
        f'<div class="tile"><b>{value}</b><span>{esc(label)}</span></div>'
        for label, value in (
            ("signed up (verified)", summary["signed_up"]),
            ("sessions running now", summary["running"]),
            ("new this week", summary["new_this_week"]),
            ("seen this week", summary["seen_this_week"]),
            ("locked clicks this week", summary["locked_this_week"]),
            ("emails in the last 24 h", f'{summary["codes_today"]} / {s.codes_per_day}'),
            ("asked, never verified", summary["never_verified"]),
        )
    )

    def actions(row: dict) -> str:
        email = esc(row["email"])
        hidden = f'<input type="hidden" name="email" value="{email}">'
        grant_label = f"+{s.session_minutes} min" if row["status"] == "active" else "Grant another session"
        revoke = (
            f'<form method="post" action="/admin/visitor">{hidden}<input type="hidden" name="action" value="revoke">'
            '<button type="submit">Revoke</button></form>'
            if row["status"] != "revoked"
            else ""
        )
        return (
            f'<form method="post" action="/admin/visitor">{hidden}<input type="hidden" name="action" value="grant">'
            f'<button type="submit">{esc(grant_label)}</button></form>'
            f"{revoke}"
            # The address stays out of the confirm() text: it was typed by a stranger and would run as script there.
            '<form method="post" action="/admin/visitor" onsubmit="return confirm(\'Delete this person and all their usage?\')">'
            f'{hidden}<input type="hidden" name="action" value="delete"><button type="submit" class="danger">Delete</button></form>'
        )

    visitor_rows = "".join(
        "<tr>"
        f'<td>{esc(r["address"])}</td>'
        f'<td><span class="status {esc(r["status"])}">{esc(r["status"])}</span></td>'
        f'<td>{esc(fmt_time(r["verified_at"]))}</td>'
        f'<td>{esc(fmt_time(r["started_at"]))}</td>'
        f'<td>{esc(fmt_time(r["expires_at"]))}</td>'
        f'<td>{esc(fmt_time(r["last_seen"]))}</td>'
        f'<td class="n">{r["sessions"]}</td><td class="n">{r["pages"]}</td>'
        f'<td class="n">{r["members"]}</td><td class="n">{r["tickers"]}</td><td class="n">{r["locked"]}</td>'
        f'<td>{esc(", ".join(r["top_items"]) or "—")}</td>'
        f'<td>{esc(r["last_ip"] or "—")}</td>'
        f"<td>{actions(r)}</td>"
        "</tr>"
        for r in rows
    ) or '<tr><td colspan="14" class="muted">Nobody has asked for a code yet.</td></tr>'

    event_rows = "".join(
        f'<tr><td>{esc(fmt_time(e["at"]))}</td><td>{esc(e["email"])}</td><td>{esc(e["kind"])}</td>'
        f'<td>{esc(e["detail"] or "")}</td></tr>'
        for e in events
    ) or '<tr><td colspan="4" class="muted">No activity yet.</td></tr>'

    locked = ", ".join(feature.label for feature in LOCKED_FEATURES)
    notice = f'<p class="alert">Done: {esc(done)}.</p>' if done else ""
    body = (
        '<div class="bar"><h1>Demo usage</h1><div class="links">'
        '<a href="/admin/visitors.csv">People CSV</a><a href="/admin/events.csv">Events CSV</a>'
        '<form method="post" action="/admin/logout"><button type="submit">Sign out</button></form>'
        "</div></div>"
        f'{notice}<div class="tiles">{tiles}</div>'
        '<h2>People</h2><div class="scroll"><table><thead><tr>'
        "<th>Email</th><th>Status</th><th>First sign-in</th><th>Session started</th><th>Access until</th>"
        "<th>Last seen</th><th>Sessions</th><th>Pages</th><th>Members</th><th>Tickers</th><th>Locked clicks</th>"
        "<th>Most opened</th><th>Last IP</th><th></th>"
        f"</tr></thead><tbody>{visitor_rows}</tbody></table></div>"
        '<h2>Latest 100 events</h2><div class="scroll"><table><thead><tr>'
        "<th>When</th><th>Account</th><th>What</th><th>Detail</th>"
        f"</tr></thead><tbody>{event_rows}</tbody></table></div>"
        f'<p class="muted">Times in UTC. One {s.session_minutes}-minute session per address, from the first sign-in; '
        f"locked: {esc(locked)}; people unseen for {s.retention_days} days are deleted with their usage.</p>"
    )
    return _html(_page("Admin", body))


@router.post("/admin/login")
async def admin_login(request: Request) -> Response:
    access = _access(request)
    if _limiter.hit(client_ip(request)):
        return _login_page("Too many attempts. Wait 15 minutes.", 429)
    token = (await _form(request)).get("token", "").strip()
    if not hmac.compare_digest(token.encode(), access.settings.admin_token.encode()):
        return _login_page("That token is not right.", 401)
    response = _redirect("/admin")
    response.set_cookie(
        ADMIN_COOKIE, _cookie_value(access), max_age=12 * 3600, httponly=True, samesite="strict",
        secure=is_https(request), path="/admin",
    )
    return response


@router.post("/admin/logout")
def admin_logout(request: Request) -> Response:
    _access(request)
    response = _redirect("/admin")
    response.delete_cookie(ADMIN_COOKIE, path="/admin")
    return response


@router.post("/admin/visitor")
async def admin_visitor(request: Request) -> Response:
    access = _access(request)
    if not _authed(access, request):
        return _redirect("/admin")
    form = await _form(request)
    email = form.get("email", "")
    action = form.get("action", "")
    store = access.store
    if action == "grant":
        changed = store.grant_session(email, access.settings.session_minutes)
        done = f"{email}: {changed}" if changed else None
    elif action == "revoke":
        done = f"{email} revoked" if store.revoke(email) else None
    elif action == "delete":
        done = f"{email} deleted with all their usage" if store.delete(email) else None
    else:
        raise HTTPException(status_code=400, detail="Unknown action")
    return _redirect("/admin?done=" + quote(done or f"nothing to change for {email}"))


def _csv(filename: str, header: list[str], rows) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow([_csv_cell(value) for value in row])
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={**_HEADERS, "Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/admin/visitors.csv")
def admin_visitors_csv(request: Request) -> Response:
    access = _access(request)
    if not _authed(access, request):
        raise HTTPException(status_code=404, detail="Not Found")
    columns = [
        "email", "address", "status", "requested_at", "verified_at", "started_at", "expires_at", "last_seen",
        "sessions", "pages", "members", "tickers", "locked", "codes_sent", "top_items", "signup_ip", "last_ip",
    ]
    times = {"requested_at", "verified_at", "started_at", "expires_at", "last_seen"}

    def values(row: dict):
        for column in columns:
            value = row[column]
            if column in times:
                value = fmt_time(value) if value else ""
            elif column == "top_items":
                value = " | ".join(value)
            yield value

    return _csv("demo-people.csv", columns, (list(values(r)) for r in access.store.visitor_rows()))


@router.get("/admin/events.csv")
def admin_events_csv(request: Request) -> Response:
    access = _access(request)
    if not _authed(access, request):
        raise HTTPException(status_code=404, detail="Not Found")
    return _csv(
        "demo-events.csv",
        ["at_utc", "email", "kind", "detail"],
        ([fmt_time(e["at"]), e["email"], e["kind"], e["detail"] or ""] for e in access.store.iter_events()),
    )


@router.api_route("/admin/{rest:path}", methods=["GET", "POST"])
def admin_unknown(rest: str) -> Response:
    raise HTTPException(status_code=404, detail="Not Found")


@router.get("/robots.txt")
def robots() -> Response:
    return Response("User-agent: *\nDisallow: /access\nDisallow: /admin\nDisallow: /api/\n", media_type="text/plain")
