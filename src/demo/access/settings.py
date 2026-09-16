"""Access-gate settings. Every one is an environment variable with a default.

Numbers and switches live in ``.deploy/compose.yml``. The secrets live only in
``/opt/sites/congress-demo/.env`` on the server: the admin token and the mail
account.

The mail account uses the same variable names as Capsar (``W3_capsar_io``) and the
SearchForAlpha demo, so one block of credentials serves the whole portfolio:
``NEO_SMTP_HOST`` / ``_PORT`` / ``_USER`` / ``_PASS`` and ``EMAIL_FROM``, with the
generic ``SMTP_*`` names as a fallback. Neo is the mail host of noeinsolutions.com:
``smtp0001.neo.space``, signed in as the owner's mailbox, sending as
``support@noeinsolutions.com`` -- an alias of that mailbox, since Neo refuses any
other From. On the Hetzner server the port must be 587 (STARTTLS): outbound 465 is
blocked there, even though Capsar's local ``.env`` says 465.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}

MIN_ADMIN_TOKEN_LENGTH = 24
CONTACT_EMAIL = "support@noeinsolutions.com"


def _str(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _int(name: str, default: int, minimum: int = 1) -> int:
    """A positive number. ``0`` never means "no limit": it is raised to ``minimum``."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    return default


def _first(*names: str) -> str:
    """The first of ``names`` that is set and not blank."""
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _port(raw: str, default: int) -> int:
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


@dataclass(frozen=True)
class AccessSettings:
    enabled: bool = True                   # DEMO_ACCESS_GATE: false serves the demo to anyone, unrecorded (local runs only)
    db_path: str = "data/demo-access/access.sqlite3"  # DEMO_ACCESS_DB: visitors, codes, grants, usage events
    # The session
    session_minutes: int = 45              # DEMO_SESSION_MINUTES: one session per address, wall clock from the first sign-in
    retention_days: int = 365              # DEMO_RETENTION_DAYS: a visitor unseen this long is deleted with their usage
    # Sign-in codes
    code_minutes: int = 15                 # DEMO_CODE_MINUTES: a code or link stops working after this
    code_attempts: int = 5                 # DEMO_CODE_ATTEMPTS: wrong codes before that code is dead
    codes_per_email_per_hour: int = 3      # DEMO_CODES_PER_EMAIL_PER_HOUR: sign-in emails to one address
    codes_per_hour: int = 60               # DEMO_CODES_PER_HOUR: sign-in emails in total, per hour
    # Neo allows a mailbox about 1,000 sent emails a day, shared with the owner's
    # own mail and every other app on the account; a bot must not spend it.
    codes_per_day: int = 200               # DEMO_CODES_PER_DAY: sign-in emails in total, per day
    signups_per_ip_per_day: int = 5        # DEMO_SIGNUPS_PER_IP_PER_DAY: new addresses from one connection
    blocked_domains: frozenset[str] = field(default_factory=frozenset)  # DEMO_BLOCKED_EMAIL_DOMAINS: comma list, added to emails.DISPOSABLE_DOMAINS
    # Mail (secret file). Names shared with Capsar; SMTP_* is the fallback for each.
    mail_backend: str = "smtp"             # DEMO_MAIL_BACKEND: smtp | console (console logs the code; local runs and tests)
    smtp_host: str = ""                    # NEO_SMTP_HOST, else SMTP_HOST: smtp0001.neo.space
    smtp_port: int = 587                   # NEO_SMTP_PORT, else SMTP_PORT: 587 (the Hetzner server blocks 465)
    smtp_security: str = "auto"            # DEMO_SMTP_SECURITY: auto (465 -> ssl, else starttls) | ssl | starttls | none
    smtp_user: str = ""                    # NEO_SMTP_USER, else SMTP_USER: the mailbox login
    smtp_password: str = ""                # NEO_SMTP_PASS, else SMTP_PASS
    mail_from: str = ""                    # EMAIL_FROM, else SMTP_FROM, else the mailbox: Neo sends only as the mailbox or its aliases
    mail_relay: str = ""                   # DEMO_MAIL_RELAY: host:port of the relay container; empty dials the mail server directly
    notify_email: str = ""                 # DEMO_NOTIFY_EMAIL: the owner gets one line per new sign-up; empty sends nothing
    public_url: str = ""                   # DEMO_PUBLIC_URL: base of the link in the email; empty uses the request's host
    contact_email: str = CONTACT_EMAIL     # DEMO_CONTACT_EMAIL: on the privacy note, the ended page and the emails
    # Admin
    admin_token: str = ""                  # DEMO_ADMIN_TOKEN (secret file): unlocks /admin; unset or short and /admin 404s

    @classmethod
    def from_env(cls) -> "AccessSettings":
        base = cls()
        extra = {d.strip().lower() for d in _str("DEMO_BLOCKED_EMAIL_DOMAINS", "").split(",") if d.strip()}
        return cls(
            enabled=_bool("DEMO_ACCESS_GATE", base.enabled),
            db_path=_str("DEMO_ACCESS_DB", base.db_path),
            session_minutes=_int("DEMO_SESSION_MINUTES", base.session_minutes),
            retention_days=_int("DEMO_RETENTION_DAYS", base.retention_days),
            code_minutes=_int("DEMO_CODE_MINUTES", base.code_minutes),
            code_attempts=_int("DEMO_CODE_ATTEMPTS", base.code_attempts),
            codes_per_email_per_hour=_int("DEMO_CODES_PER_EMAIL_PER_HOUR", base.codes_per_email_per_hour),
            codes_per_hour=_int("DEMO_CODES_PER_HOUR", base.codes_per_hour),
            codes_per_day=_int("DEMO_CODES_PER_DAY", base.codes_per_day),
            signups_per_ip_per_day=_int("DEMO_SIGNUPS_PER_IP_PER_DAY", base.signups_per_ip_per_day),
            blocked_domains=frozenset(extra),
            mail_backend=_str("DEMO_MAIL_BACKEND", base.mail_backend).lower(),
            smtp_host=_first("NEO_SMTP_HOST", "SMTP_HOST"),
            smtp_port=_port(_first("NEO_SMTP_PORT", "SMTP_PORT"), base.smtp_port),
            smtp_security=_str("DEMO_SMTP_SECURITY", base.smtp_security).lower(),
            smtp_user=_first("NEO_SMTP_USER", "SMTP_USER"),
            # Not stripped: a password is taken exactly as written.
            smtp_password=os.environ.get("NEO_SMTP_PASS") or os.environ.get("SMTP_PASS") or "",
            mail_from=_first("EMAIL_FROM", "SMTP_FROM") or _first("NEO_SMTP_USER", "SMTP_USER"),
            mail_relay=_str("DEMO_MAIL_RELAY", base.mail_relay),
            notify_email=_str("DEMO_NOTIFY_EMAIL", base.notify_email),
            public_url=_str("DEMO_PUBLIC_URL", base.public_url).rstrip("/"),
            contact_email=_str("DEMO_CONTACT_EMAIL", base.contact_email) or CONTACT_EMAIL,
            admin_token=_str("DEMO_ADMIN_TOKEN", base.admin_token),
        )

    @property
    def admin_enabled(self) -> bool:
        return len(self.admin_token) >= MIN_ADMIN_TOKEN_LENGTH

    @property
    def tls_mode(self) -> str:
        """How the SMTP connection is encrypted. 465 is implicit TLS, 587 upgrades with STARTTLS."""
        if self.smtp_security == "auto":
            return "ssl" if self.smtp_port == 465 else "starttls"
        return self.smtp_security

    @property
    def relay_address(self) -> tuple[str, int] | None:
        """``DEMO_MAIL_RELAY`` as ``(host, port)``, or None to dial the mail server itself."""
        host, sep, port = self.mail_relay.rpartition(":")
        if not sep or not host or not port.isdigit():
            return None
        return host, int(port)

    def problems(self) -> list[str]:
        """What stops the gate from working. The server refuses to start on any:
        a gate nobody can pass is an outage, and a failed health check rolls back."""
        if not self.enabled:
            return []
        found = []
        if self.mail_backend not in ("smtp", "console"):
            found.append(f"DEMO_MAIL_BACKEND must be smtp or console, not {self.mail_backend!r}")
        if self.mail_backend == "smtp":
            if not self.smtp_host:
                found.append("NEO_SMTP_HOST (or SMTP_HOST) is not set, so no sign-in email can be sent")
            if not self.smtp_user or not self.smtp_password:
                found.append(
                    "NEO_SMTP_USER and NEO_SMTP_PASS (or SMTP_USER and SMTP_PASS) are needed to sign in to the mail server"
                )
            if self.smtp_security not in ("auto", "starttls", "ssl", "none"):
                found.append(f"DEMO_SMTP_SECURITY must be auto, ssl, starttls or none, not {self.smtp_security!r}")
            if self.mail_relay and self.relay_address is None:
                found.append(f"DEMO_MAIL_RELAY must be host:port, not {self.mail_relay!r}")
        return found

    def as_limits(self) -> dict[str, int]:
        return {
            "session_minutes": self.session_minutes,
            "code_minutes": self.code_minutes,
            "codes_per_email_per_hour": self.codes_per_email_per_hour,
            "codes_per_hour": self.codes_per_hour,
            "codes_per_day": self.codes_per_day,
            "signups_per_ip_per_day": self.signups_per_ip_per_day,
            "retention_days": self.retention_days,
        }
