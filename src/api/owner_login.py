"""Owner login for the production copy: email + hashed password, like SearchForAlpha.

``SITE_LOGIN_EMAIL`` + ``SITE_LOGIN_PASSWORD_HASH`` (a Werkzeug ``scrypt:`` or
``pbkdf2:`` hash, so the plain password never reaches the server and the same
hash works on all three sites). When the hash is set it replaces the legacy
``APP_USERNAME`` / ``APP_PASSWORD`` pair, and the app refuses to start unless
``SITE_LOGIN_EMAIL`` and a real ``APP_SESSION_SECRET`` (>= 32 characters) are
set too -- without the latter the session cookie would be signed with the
public dev secret. Five wrong tries from one IP lock the login for fifteen
minutes.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time

from ..config import site_login_email, site_login_password_hash

MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60
MIN_SECRET_LENGTH = 32


class LoginConfigError(RuntimeError):
    """The owner login cannot work, so the API must not start."""


def enabled() -> bool:
    return bool(site_login_password_hash())


def validate_config() -> None:
    if not enabled():
        return
    stored = site_login_password_hash()
    if not stored.startswith(("scrypt:", "pbkdf2:")) or stored.count("$") != 2:
        raise LoginConfigError("SITE_LOGIN_PASSWORD_HASH is not a Werkzeug hash (scrypt:... or pbkdf2:...)")
    if not site_login_email():
        raise LoginConfigError("SITE_LOGIN_PASSWORD_HASH is set but SITE_LOGIN_EMAIL is not")
    if len((os.getenv("APP_SESSION_SECRET") or "").strip()) < MIN_SECRET_LENGTH:
        raise LoginConfigError(
            f"the owner login needs APP_SESSION_SECRET of at least {MIN_SECRET_LENGTH} characters"
        )


def check_password_hash(stored: str, password: str) -> bool:
    """Verify ``password`` against a Werkzeug ``scrypt:`` or ``pbkdf2:`` hash."""
    try:
        method, salt, expected = stored.split("$", 2)
        parts = method.split(":")
        secret, salt_bytes = password.encode("utf-8"), salt.encode("utf-8")
        if parts[0] == "scrypt":
            n, r, p = (int(x) for x in parts[1:4]) if len(parts) == 4 else (2**15, 8, 1)
            actual = hashlib.scrypt(secret, salt=salt_bytes, n=n, r=r, p=p, maxmem=132 * n * r * p).hex()
        elif parts[0] == "pbkdf2":
            name = parts[1] if len(parts) > 1 else "sha256"
            iterations = int(parts[2]) if len(parts) > 2 else 1_000_000
            actual = hashlib.pbkdf2_hmac(name, secret, salt_bytes, iterations).hex()
        else:
            return False
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def verify(email: str, password: str) -> str | None:
    """The owner's email when both match, else None."""
    owner = site_login_email()
    given = email.strip().lower()
    if owner and hmac.compare_digest(given, owner) and check_password_hash(site_login_password_hash(), password):
        return owner
    return None


_failures: dict[str, list[float]] = {}
_lock = threading.Lock()


def _recent(ip: str, now: float) -> list[float]:
    recent = [t for t in _failures.get(ip, []) if now - t < LOCK_SECONDS]
    if recent:
        _failures[ip] = recent
    else:
        _failures.pop(ip, None)
    return recent


def locked(ip: str) -> bool:
    with _lock:
        return len(_recent(ip, time.monotonic())) >= MAX_FAILURES


def record(ip: str, ok: bool) -> None:
    with _lock:
        if ok:
            _failures.pop(ip, None)
        else:
            _failures.setdefault(ip, []).append(time.monotonic())
