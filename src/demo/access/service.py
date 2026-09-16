"""The access gate's state in one object: settings, store, mailer, and the hooks.

Built once per app by :func:`build_access` when ``DEMO_MODE`` is on and the gate
is not switched off. The rest of the demo reaches it through two hooks only:

- ``record(email, kind, detail)`` -- after something was opened or refused;
- ``visitor_for(request)`` -- who this browser is, from its access cookie.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

from starlette.requests import Request

from . import messages
from .mailer import ConsoleMailer, MailError, SmtpMailer, build_mailer
from .settings import AccessSettings
from .store import AccessStore, Visitor

logger = logging.getLogger(__name__)

ACCESS_COOKIE = "f9_demo_access"
PURGE_EVERY_SECONDS = 3600
# The same page opened again within this window is one event, not twenty: a
# dashboard page fires several API calls, and a filter change fires them again.
USAGE_DEDUPE_SECONDS = 600


def iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def client_ip(request: Request) -> str:
    # Only the web container can reach the API, and it passes on the X-Real-IP the
    # edge set from the real connection (.deploy/site-nginx.conf).
    header = (request.headers.get("x-real-ip") or "").strip()
    if header:
        return header[:64]
    return request.client.host if request.client else "unknown"


def public_base(settings: AccessSettings, request: Request) -> str:
    if settings.public_url:
        return settings.public_url
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",")[0].strip()
    host = request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def is_https(request: Request) -> bool:
    return (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip() == "https" or request.url.scheme == "https"


class DemoAccess:
    def __init__(self, settings: AccessSettings, store: AccessStore, mailer: ConsoleMailer | SmtpMailer) -> None:
        self.settings = settings
        self.store = store
        self.mailer = mailer
        self._seen: dict[tuple[str, str, str], float] = {}
        self._seen_lock = threading.Lock()
        self._started = False

    # ----------------------------------------------------------------- who

    def visitor_for(self, request: Request) -> Visitor | None:
        try:
            return self.store.grant(request.cookies.get(ACCESS_COOKIE), ip=client_ip(request))
        except Exception:  # noqa: BLE001 - a broken store closes the door, it does not crash the page
            logger.exception("reading demo access failed")
            return None

    def payload(self, visitor: Visitor | None) -> dict[str, Any]:
        """``access`` in ``/api/demo/status`` and in a successful sign-in."""
        s = self.settings
        now = self.store.now()
        status = visitor.status(now) if visitor is not None else "signed_out"
        if status in ("unverified", "ready"):
            status = "signed_out"
        signed_in = status in ("active", "ended", "revoked")
        return {
            "gate": True,
            "status": status,
            "address": visitor.address if visitor is not None and signed_in else None,
            "startedAt": iso(visitor.started_at) if visitor is not None and signed_in else None,
            "expiresAt": iso(visitor.expires_at) if visitor is not None and signed_in else None,
            "serverNow": iso(now),
            "codeMinutes": s.code_minutes,
            "retentionDays": s.retention_days,
            "privacy": messages.privacy(s),
        }

    # ----------------------------------------------------------------- usage

    def record(self, email: str, kind: str, detail: str | None = None, *, dedupe: bool = False) -> None:
        """Log what a signed-in person did. Tracking never breaks the demo."""
        if dedupe:
            key = (email, kind, detail or "")
            now = time.monotonic()
            with self._seen_lock:
                last = self._seen.get(key)
                if last is not None and now - last < USAGE_DEDUPE_SECONDS:
                    return
                self._seen[key] = now
                if len(self._seen) > 5000:
                    cutoff = now - USAGE_DEDUPE_SECONDS
                    self._seen = {k: v for k, v in self._seen.items() if v >= cutoff}
        try:
            self.store.record(email, kind, detail)
        except Exception:  # noqa: BLE001
            logger.exception("recording demo usage failed")

    # ----------------------------------------------------------------- the owner's notice

    def notify_signup(self, visitor: Visitor, request: Request) -> None:
        """One email to the owner per new person, off the request path."""
        s = self.settings
        if not s.notify_email:
            return
        mail = messages.signup_notice(s, visitor=visitor, admin_url=f"{public_base(s, request)}/admin")

        def send() -> None:
            try:
                self.mailer.send(mail)
            except MailError:
                logger.warning("demo access: the sign-up notice to the owner could not be sent")

        if isinstance(self.mailer, ConsoleMailer):
            send()  # synchronous, so a test can read the outbox
        else:
            threading.Thread(target=send, name="demo-signup-notice", daemon=True).start()

    # ----------------------------------------------------------------- background

    def purge(self) -> int:
        return self.store.purge(self.settings.retention_days)

    def check_mail(self) -> None:
        """Sign in to the mail server once and log whether sign-in codes can go out."""
        s = self.settings
        via = f" via relay {s.mail_relay}" if s.mail_relay else ""
        try:
            self.mailer.check()
        except MailError as exc:
            logger.error(
                "demo access: mail server %s:%s%s NOT usable (%s); every sign-in code will fail. "
                "Check NEO_SMTP_* in the server .env (port 587, password single-quoted) and that %s is an alias "
                "of the login mailbox.",
                s.smtp_host, s.smtp_port, via, exc, s.mail_from,
            )
            return
        logger.warning(
            "demo access: mail server %s:%s%s reachable, sign-in accepted, sending as %s",
            s.smtp_host, s.smtp_port, via, s.mail_from,
        )

    def start_background(self) -> None:
        """The hourly purge, and the start-up mail check. Idempotent."""
        if self._started:
            return
        self._started = True

        def housekeeping() -> None:
            while True:
                try:
                    removed = self.purge()
                    if removed:
                        logger.info("demo access: deleted %d visitors past the retention period", removed)
                except Exception:  # noqa: BLE001
                    logger.exception("demo access housekeeping failed")
                time.sleep(PURGE_EVERY_SECONDS)

        threading.Thread(target=housekeeping, name="demo-access-housekeeping", daemon=True).start()
        if self.settings.mail_backend == "smtp":
            threading.Thread(target=self.check_mail, name="demo-mail-check", daemon=True).start()


def build_access(settings: AccessSettings | None = None) -> DemoAccess | None:
    """The gate for this process, or None when it is switched off.

    Raises ``RuntimeError`` when the gate is on but cannot work: the server then
    refuses to start, the deploy health check fails and the previous release stays.
    """
    settings = settings or AccessSettings.from_env()
    if not settings.enabled:
        logger.warning("DEMO_ACCESS_GATE is off: the demo is open to anyone, and nothing is recorded")
        return None
    problems = settings.problems()
    if problems:
        raise RuntimeError("the demo access gate is misconfigured: " + "; ".join(problems))
    store = AccessStore(settings.db_path)
    return DemoAccess(settings, store, build_mailer(settings))
