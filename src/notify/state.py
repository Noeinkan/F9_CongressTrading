"""Persistent state so the notifier never repeats itself.

Two tables, created on demand in the tracker's own SQLite (kept out of
``src/db.py`` so the notification feature stays self-contained):

``notification_state``
    Key/value scratchpad. The important key is ``last_transaction_id``: the
    high-water mark of rows already considered. New rows are simply those with
    a larger ``transactions.id``, which survives re-runs of the same night's
    cron without re-alerting.

``notification_cluster_log``
    Remembers which coordinated-trading clusters were reported and with how
    many members. A cluster is re-announced only when it *grows* — "3 members
    in NVDA" is news once; "5 members in NVDA" is news again.

**Bootstrap matters.** The database holds years of history, so the very first
run must not try to alert on all of it. ``bootstrap_if_needed`` stamps the
current maximum id as already-seen and reports that it did, which turns the
first run into a single confirmation message instead of a flood.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

LAST_TRANSACTION_ID = "last_transaction_id"
BOOTSTRAPPED_AT = "bootstrapped_at"
LAST_DIGEST_DATE = "last_digest_date"
LAST_EVENT_RUN_AT = "last_event_run_at"
LAST_DELIVERY_ERROR = "last_delivery_error"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def init_notify_state(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_cluster_log (
            cluster_key TEXT PRIMARY KEY,
            members INTEGER NOT NULL DEFAULT 0,
            sent_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def get_state(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute(
        "SELECT value FROM notification_state WHERE key = ?", (key,)
    ).fetchone()
    if row is None:
        return default
    value = row[0] if not isinstance(row, sqlite3.Row) else row["value"]
    return default if value is None else str(value)


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO notification_state (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                       updated_at = excluded.updated_at
        """,
        (key, str(value), _utc_now_iso()),
    )
    conn.commit()


def get_int_state(conn: sqlite3.Connection, key: str, default: int = 0) -> int:
    raw = get_state(conn, key, "").strip()
    if not raw:
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def max_transaction_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM transactions").fetchone()
    return int(row[0] or 0) if row else 0


def last_transaction_id(conn: sqlite3.Connection) -> int:
    return get_int_state(conn, LAST_TRANSACTION_ID, 0)


def set_last_transaction_id(conn: sqlite3.Connection, value: int) -> None:
    set_state(conn, LAST_TRANSACTION_ID, str(int(value)))


def is_bootstrapped(conn: sqlite3.Connection) -> bool:
    return bool(get_state(conn, BOOTSTRAPPED_AT, "").strip())


def mark_bootstrapped(conn: sqlite3.Connection, high_water: int) -> None:
    """Record the existing backlog as already seen.

    Deliberately separate from reading the mark: the caller only commits this
    once the "alerts armed" message has actually been delivered, so a failed
    first run retries instead of silently swallowing the backlog.
    """
    set_last_transaction_id(conn, high_water)
    set_state(conn, BOOTSTRAPPED_AT, _utc_now_iso())


def cluster_is_new(conn: sqlite3.Connection, cluster_key: str, members: int) -> bool:
    """True when this cluster was never reported, or has grown since."""
    row = conn.execute(
        "SELECT members FROM notification_cluster_log WHERE cluster_key = ?",
        (cluster_key,),
    ).fetchone()
    if row is None:
        return True
    return int(members) > int(row[0] or 0)


def record_cluster(conn: sqlite3.Connection, cluster_key: str, members: int) -> None:
    conn.execute(
        """
        INSERT INTO notification_cluster_log (cluster_key, members, sent_at)
        VALUES (?, ?, ?)
        ON CONFLICT(cluster_key) DO UPDATE SET members = excluded.members,
                                               sent_at = excluded.sent_at
        """,
        (cluster_key, int(members), _utc_now_iso()),
    )
    conn.commit()


def record_event_run(conn: sqlite3.Connection, *, error: str = "") -> None:
    set_state(conn, LAST_EVENT_RUN_AT, _utc_now_iso())
    set_state(conn, LAST_DELIVERY_ERROR, error)


def last_digest_date(conn: sqlite3.Connection) -> str:
    return get_state(conn, LAST_DIGEST_DATE, "").strip()


def set_last_digest_date(conn: sqlite3.Connection, iso_date: str) -> None:
    set_state(conn, LAST_DIGEST_DATE, iso_date)
