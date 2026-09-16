"""Who has demo access, and what they did with it -- one SQLite file.

Four tables:

- ``visitors``  one row per mailbox (keyed on ``emails.canonical``): when it asked
  for a code, when it first signed in, when its current session started and ends,
  whether it was revoked, when it was last seen.
- ``codes``     one row per sign-in email sent: the 6-digit code and the link
  token, both stored only as hashes, with an expiry and a wrong-guess count.
- ``grants``    one row per signed-in browser: the cookie token (hashed).
- ``events``    the usage log the admin page reads: pages, members and tickers
  opened, locked features clicked, sign-ins.

**The session.** The first sign-in starts a wall-clock window
(``DEMO_SESSION_MINUTES``, 45). Signing in again inside it -- another device, a
closed tab -- resumes the same window with the time left; it never restarts.
Once it ends the address stays ended: only the owner grants another, from
``/admin``.

Unlike the snapshot this state must survive a restart -- a session that resets
when the container does is no limit at all -- so the file lives on a Docker
volume (``.deploy/compose.yml``). Every write happens under one lock on one
connection; the API's worker threads and the housekeeping thread share it.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

DAY = 86400.0

# Kinds that say the person was using the demo, as opposed to asking for a code.
USAGE_KINDS = ("page", "member", "ticker", "locked")
ITEM_KINDS = ("member", "ticker")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS visitors (
    email       TEXT PRIMARY KEY,
    address     TEXT NOT NULL,
    created_at  REAL NOT NULL,
    verified_at REAL,
    started_at  REAL,
    expires_at  REAL,
    sessions    INTEGER NOT NULL DEFAULT 0,
    revoked_at  REAL,
    last_seen   REAL,
    signup_ip   TEXT,
    last_ip     TEXT,
    user_agent  TEXT
);
CREATE TABLE IF NOT EXISTS codes (
    id          INTEGER PRIMARY KEY,
    email       TEXT NOT NULL,
    code_hash   TEXT NOT NULL,
    link_hash   TEXT NOT NULL UNIQUE,
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    used_at     REAL,
    ip          TEXT
);
CREATE INDEX IF NOT EXISTS codes_by_email ON codes(email, created_at);
CREATE TABLE IF NOT EXISTS grants (
    token_hash  TEXT PRIMARY KEY,
    email       TEXT NOT NULL,
    created_at  REAL NOT NULL,
    last_seen   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS grants_by_email ON grants(email);
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY,
    email       TEXT NOT NULL,
    at          REAL NOT NULL,
    day         TEXT NOT NULL,
    kind        TEXT NOT NULL,
    detail      TEXT
);
CREATE INDEX IF NOT EXISTS events_by_email_day ON events(email, day, kind);
CREATE INDEX IF NOT EXISTS events_by_at ON events(at);
"""


def _hash(purpose: str, *parts: str) -> str:
    return hashlib.sha256(":".join((purpose, *parts)).encode("utf-8")).hexdigest()


def utc_day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


@dataclass(frozen=True)
class Visitor:
    email: str
    address: str
    created_at: float
    verified_at: float | None
    started_at: float | None
    expires_at: float | None
    sessions: int
    revoked_at: float | None
    last_seen: float | None

    def status(self, now: float) -> str:
        """``revoked`` | ``unverified`` (never signed in) | ``ready`` (a session the
        owner granted, not started yet) | ``active`` | ``ended``."""
        if self.revoked_at:
            return "revoked"
        if not self.verified_at:
            return "unverified"
        if self.expires_at is None:
            return "ready"
        if self.expires_at <= now:
            return "ended"
        return "active"


@dataclass(frozen=True)
class Verification:
    status: str  # ok | wrong | expired | used_up | unknown | ended
    email: str | None = None
    token: str | None = None
    visitor: Visitor | None = None
    attempts_left: int = 0
    first_session: bool = False  # this sign-in started the address's very first session


def _visitor(row: sqlite3.Row | None) -> Visitor | None:
    if row is None:
        return None
    return Visitor(
        email=row["email"],
        address=row["address"],
        created_at=row["created_at"],
        verified_at=row["verified_at"],
        started_at=row["started_at"],
        expires_at=row["expires_at"],
        sessions=int(row["sessions"] or 0),
        revoked_at=row["revoked_at"],
        last_seen=row["last_seen"],
    )


class AccessStore:
    def __init__(self, path: str | Path, *, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock
        self._lock = threading.Lock()
        target = str(path)
        if target != ":memory:":
            Path(target).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(target, check_same_thread=False, timeout=10)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            if target != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def now(self) -> float:
        return self.clock()

    # ----------------------------------------------------------------- reads

    def visitor(self, email: str) -> Visitor | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM visitors WHERE email = ?", (email,)).fetchone()
        return _visitor(row)

    def codes_sent_since(self, since: float, *, email: str | None = None) -> int:
        sql = "SELECT COUNT(*) FROM codes WHERE created_at >= ?"
        args: tuple[Any, ...] = (since,)
        if email is not None:
            sql += " AND email = ?"
            args = (since, email)
        with self._lock:
            return int(self._conn.execute(sql, args).fetchone()[0])

    def new_visitors_from_ip_since(self, ip: str, since: float) -> int:
        with self._lock:
            return int(
                self._conn.execute(
                    "SELECT COUNT(*) FROM visitors WHERE signup_ip = ? AND created_at >= ?", (ip, since)
                ).fetchone()[0]
            )

    # ----------------------------------------------------------------- sign-in

    def create_code(self, *, email: str, address: str, ip: str, user_agent: str, minutes: int) -> tuple[str, str]:
        """Register a sign-in email about to be sent. Returns ``(code, link_token)``.

        Call ``sent`` once the mail server took it, or ``cancel_code`` if it did not.
        """
        now = self.clock()
        code = f"{secrets.randbelow(10**6):06d}"
        link = secrets.token_urlsafe(32)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO visitors (email, address, created_at, signup_ip, last_ip, user_agent) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (email, address, now, ip, ip, user_agent[:300]),
            )
            self._conn.execute("UPDATE visitors SET address = ?, last_ip = ? WHERE email = ?", (address, ip, email))
            self._conn.execute(
                "INSERT INTO codes (email, code_hash, link_hash, created_at, expires_at, ip) VALUES (?, ?, ?, ?, ?, ?)",
                (email, _hash("code", email, code), _hash("link", link), now, now + minutes * 60, ip),
            )
        return code, link

    def sent(self, email: str, kind: str = "code_sent") -> None:
        self.record(email, kind)

    def cancel_code(self, link_token: str) -> None:
        """Forget a code whose email never left. Otherwise the rate limits would
        count, against this address and this connection, a message that never
        arrived -- and a brand-new address would be kept for nothing."""
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT email FROM codes WHERE link_hash = ?", (_hash("link", link_token),)
            ).fetchone()
            if row is None:
                return
            self._conn.execute("DELETE FROM codes WHERE link_hash = ?", (_hash("link", link_token),))
            self._conn.execute(
                "DELETE FROM visitors WHERE email = ? AND verified_at IS NULL "
                "AND NOT EXISTS (SELECT 1 FROM codes WHERE codes.email = visitors.email)",
                (row["email"],),
            )

    def verify_code(self, email: str, code: str, *, session_minutes: int, max_attempts: int) -> Verification:
        now = self.clock()
        code = "".join(ch for ch in code if ch.isdigit())
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT * FROM codes WHERE email = ? AND used_at IS NULL ORDER BY created_at DESC LIMIT 1", (email,)
            ).fetchone()
            if row is None:
                return Verification("unknown", email)
            if row["expires_at"] <= now:
                return Verification("expired", email)
            if row["attempts"] >= max_attempts:
                return Verification("used_up", email)
            if not hmac.compare_digest(row["code_hash"], _hash("code", email, code)):
                attempts = row["attempts"] + 1
                self._conn.execute("UPDATE codes SET attempts = ? WHERE id = ?", (attempts, row["id"]))
                if attempts >= max_attempts:
                    return Verification("used_up", email)
                return Verification("wrong", email, attempts_left=max_attempts - attempts)
            return self._grant_locked(email, row["id"], now, session_minutes)

    def link_email(self, link_token: str) -> str | None:
        """The address a still-usable link belongs to, without consuming it."""
        with self._lock:
            row = self._conn.execute(
                "SELECT email FROM codes WHERE link_hash = ? AND used_at IS NULL AND expires_at > ?",
                (_hash("link", link_token), self.clock()),
            ).fetchone()
        return row["email"] if row else None

    def verify_link(self, link_token: str, *, session_minutes: int) -> Verification:
        now = self.clock()
        with self._lock, self._conn:
            row = self._conn.execute("SELECT * FROM codes WHERE link_hash = ?", (_hash("link", link_token),)).fetchone()
            if row is None:
                return Verification("unknown")
            if row["used_at"] is not None or row["expires_at"] <= now:
                return Verification("expired", row["email"])
            return self._grant_locked(row["email"], row["id"], now, session_minutes)

    def _grant_locked(self, email: str, code_id: int, now: float, session_minutes: int) -> Verification:
        self._conn.execute("UPDATE codes SET used_at = ? WHERE id = ?", (now, code_id))
        visitor = _visitor(self._conn.execute("SELECT * FROM visitors WHERE email = ?", (email,)).fetchone())
        if visitor is None:
            return Verification("unknown", email)
        status = visitor.status(now)
        if status in ("revoked", "ended"):
            return Verification("ended", email, visitor=visitor)
        first_session = False
        if status in ("unverified", "ready"):
            # The clock starts here, and only here: never on a later sign-in.
            first_session = visitor.sessions == 0
            self._conn.execute(
                "UPDATE visitors SET verified_at = COALESCE(verified_at, ?), started_at = ?, expires_at = ?, "
                "sessions = sessions + 1 WHERE email = ?",
                (now, now, now + session_minutes * 60, email),
            )
            self._insert_event(email, now, "signed_in", "session started")
        else:
            self._insert_event(email, now, "signed_in", "resumed")
        token = secrets.token_urlsafe(32)
        self._conn.execute(
            "INSERT INTO grants (token_hash, email, created_at, last_seen) VALUES (?, ?, ?, ?)",
            (_hash("grant", token), email, now, now),
        )
        self._conn.execute("UPDATE visitors SET last_seen = ? WHERE email = ?", (now, email))
        visitor = _visitor(self._conn.execute("SELECT * FROM visitors WHERE email = ?", (email,)).fetchone())
        return Verification("ok", email, token=token, visitor=visitor, first_session=first_session)

    def grant(self, token: str | None, *, ip: str | None = None) -> Visitor | None:
        """The visitor a browser's access cookie belongs to, or None."""
        if not token or len(token) > 128:
            return None
        now = self.clock()
        token_hash = _hash("grant", token)
        with self._lock:
            row = self._conn.execute(
                "SELECT v.*, g.last_seen AS grant_seen FROM grants g JOIN visitors v ON v.email = g.email "
                "WHERE g.token_hash = ?",
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            if now - row["grant_seen"] > 60:  # one write a minute per browser is plenty
                with self._conn:
                    self._conn.execute("UPDATE grants SET last_seen = ? WHERE token_hash = ?", (now, token_hash))
                    self._conn.execute(
                        "UPDATE visitors SET last_seen = ?, last_ip = COALESCE(?, last_ip) WHERE email = ?",
                        (now, ip, row["email"]),
                    )
        return _visitor(row)

    def revoke_grant(self, token: str | None) -> None:
        if not token:
            return
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM grants WHERE token_hash = ?", (_hash("grant", token),))

    # ----------------------------------------------------------------- usage

    def _insert_event(self, email: str, now: float, kind: str, detail: str | None) -> None:
        self._conn.execute(
            "INSERT INTO events (email, at, day, kind, detail) VALUES (?, ?, ?, ?, ?)",
            (email, now, utc_day(now), kind, (detail or None) and str(detail)[:200]),
        )

    def record(self, email: str, kind: str, detail: str | None = None) -> None:
        with self._lock, self._conn:
            self._insert_event(email, self.clock(), kind, detail)

    # ----------------------------------------------------------------- admin

    def summary(self) -> dict[str, int]:
        now = self.clock()
        week = now - 7 * DAY
        with self._lock:
            def q(sql: str, *args: Any) -> int:
                return int(self._conn.execute(sql, args).fetchone()[0] or 0)

            return {
                "signed_up": q("SELECT COUNT(*) FROM visitors WHERE verified_at IS NOT NULL"),
                "never_verified": q("SELECT COUNT(*) FROM visitors WHERE verified_at IS NULL"),
                "running": q(
                    "SELECT COUNT(*) FROM visitors WHERE revoked_at IS NULL AND expires_at > ?",
                    now,
                ),
                "new_this_week": q("SELECT COUNT(*) FROM visitors WHERE verified_at >= ?", week),
                "seen_this_week": q("SELECT COUNT(*) FROM visitors WHERE last_seen >= ?", week),
                "locked_this_week": q("SELECT COUNT(*) FROM events WHERE kind = 'locked' AND at >= ?", week),
                "codes_today": q("SELECT COUNT(*) FROM codes WHERE created_at >= ?", now - DAY),
            }

    def visitor_rows(self) -> list[dict[str, Any]]:
        now = self.clock()
        item_marks = ",".join("?" * len(ITEM_KINDS))
        with self._lock:
            visitors = self._conn.execute(
                "SELECT * FROM visitors ORDER BY COALESCE(last_seen, created_at) DESC"
            ).fetchall()
            counts = {
                row["email"]: row
                for row in self._conn.execute(
                    "SELECT email, "
                    "SUM(kind = 'page') AS pages, SUM(kind = 'member') AS members, "
                    "SUM(kind = 'ticker') AS tickers, SUM(kind = 'locked') AS locked, "
                    "SUM(kind = 'code_sent') AS codes_sent "
                    "FROM events GROUP BY email"
                )
            }
            items: dict[str, list[str]] = {}
            for row in self._conn.execute(
                f"SELECT email, detail, COUNT(*) AS n FROM events WHERE kind IN ({item_marks}) AND detail IS NOT NULL "
                "GROUP BY email, detail ORDER BY n DESC",
                ITEM_KINDS,
            ):
                items.setdefault(row["email"], []).append(row["detail"])
        rows = []
        for v in visitors:
            visitor = _visitor(v)
            assert visitor is not None
            c = counts.get(v["email"])

            def get(key: str, _c: sqlite3.Row | None = c) -> int:
                return int(_c[key] or 0) if _c is not None else 0

            rows.append(
                {
                    "email": v["email"],
                    "address": v["address"],
                    "status": visitor.status(now),
                    "requested_at": v["created_at"],
                    "verified_at": v["verified_at"],
                    "started_at": v["started_at"],
                    "expires_at": v["expires_at"],
                    "sessions": visitor.sessions,
                    "last_seen": v["last_seen"],
                    "signup_ip": v["signup_ip"],
                    "last_ip": v["last_ip"],
                    "pages": get("pages"),
                    "members": get("members"),
                    "tickers": get("tickers"),
                    "locked": get("locked"),
                    "codes_sent": get("codes_sent"),
                    "top_items": items.get(v["email"], [])[:6],
                }
            )
        return rows

    def recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(row) for row in self._conn.execute("SELECT * FROM events ORDER BY at DESC LIMIT ?", (limit,))]

    def iter_events(self) -> Iterator[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT email, at, kind, detail FROM events ORDER BY at").fetchall()
        for row in rows:
            yield dict(row)

    def grant_session(self, email: str, minutes: int) -> str | None:
        """The only way a person gets more time. Returns what changed, or None.

        A running session gets ``minutes`` more. Anything else -- ended, revoked,
        never started -- gets a fresh window that starts at their next sign-in;
        their browsers are signed out so that sign-in is where the clock starts.
        """
        now = self.clock()
        with self._lock, self._conn:
            row = self._conn.execute("SELECT * FROM visitors WHERE email = ?", (email,)).fetchone()
            visitor = _visitor(row)
            if visitor is None:
                return None
            if visitor.status(now) == "active":
                assert visitor.expires_at is not None
                self._conn.execute(
                    "UPDATE visitors SET expires_at = ? WHERE email = ?", (visitor.expires_at + minutes * 60, email)
                )
                done = f"added {minutes} minutes to the running session"
            else:
                self._conn.execute(
                    "UPDATE visitors SET started_at = NULL, expires_at = NULL, revoked_at = NULL WHERE email = ?",
                    (email,),
                )
                self._conn.execute("DELETE FROM grants WHERE email = ?", (email,))
                done = f"granted another {minutes}-minute session, starting at the next sign-in"
            self._insert_event(email, now, "admin", done)
        return done

    def revoke(self, email: str) -> bool:
        now = self.clock()
        with self._lock, self._conn:
            changed = self._conn.execute("UPDATE visitors SET revoked_at = ? WHERE email = ?", (now, email)).rowcount
            # Every browser signed in as this address is out at once.
            self._conn.execute("DELETE FROM grants WHERE email = ?", (email,))
            if changed:
                self._insert_event(email, now, "admin", "revoked")
        return bool(changed)

    def delete(self, email: str) -> bool:
        with self._lock, self._conn:
            changed = self._conn.execute("DELETE FROM visitors WHERE email = ?", (email,)).rowcount
            for table in ("codes", "grants", "events"):
                self._conn.execute(f"DELETE FROM {table} WHERE email = ?", (email,))
        return bool(changed)

    def purge(self, retention_days: int, unverified_days: int = 30) -> int:
        """Drop spent codes; visitors unseen for ``retention_days``, with everything
        about them; and addresses nobody verified within ``unverified_days`` --
        anyone can type anyone's address, so those are not kept for a year."""
        now = self.clock()
        cutoff = now - retention_days * DAY
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM codes WHERE expires_at < ?", (now - DAY,))
            stale = [
                row["email"]
                for row in self._conn.execute(
                    "SELECT email FROM visitors WHERE COALESCE(last_seen, created_at) < ? "
                    "OR (verified_at IS NULL AND created_at < ?)",
                    (cutoff, now - min(unverified_days, retention_days) * DAY),
                )
            ]
            for email in stale:
                for table in ("visitors", "codes", "grants", "events"):
                    self._conn.execute(f"DELETE FROM {table} WHERE email = ?", (email,))
            self._conn.execute("DELETE FROM events WHERE at < ?", (cutoff,))
            # An ended session keeps its grants, so the browser is told "your time
            # is up" rather than asked to sign in again.
            self._conn.execute("DELETE FROM grants WHERE last_seen < ?", (cutoff,))
        return len(stale)
