"""Orchestration: read state, detect, render, send, advance state.

The ordering here is the part that matters operationally. The high-water mark
is advanced **only after Telegram confirms delivery**, so a network outage or
an expired token delays alerts rather than losing them: the next run picks up
the same rows and tries again. The same applies to the coordinated-cluster log.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable

import pandas as pd

from ..db import get_connection, init_db
from . import state as notify_state
from .digest import compute_digest_stats, render_digest
from .events import KIND_CLUSTER, Event, collect_events, is_urgent, recent_filings
from .format import (
    plural,
    render_bootstrap_message,
    render_event_message,
    render_failure_message,
    render_test_message,
)
from .links import DashboardLinks
from .query import (
    load_new_transactions,
    new_transaction_stats,
    newest_ingest_timestamp,
    prior_trade_count,
    total_transaction_count,
    transactions_ingested_since,
)
from .settings import NotifySettings, load_settings
from .telegram import SendResult, send_message

logger = logging.getLogger(__name__)

DIGEST_WINDOW_DAYS = 7

STATUS_SENT = "sent"
STATUS_PREVIEWED = "previewed"
STATUS_QUIET = "quiet"
STATUS_BOOTSTRAPPED = "bootstrapped"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"


@dataclass(frozen=True)
class RunOutcome:
    status: str
    message: str
    events: int = 0
    send: SendResult | None = None

    @property
    def ok(self) -> bool:
        return self.status != STATUS_FAILED


def _sent_status(result: SendResult) -> str:
    """A dry run must not report itself as "sent" in the cron log."""
    if not result.ok:
        return STATUS_FAILED
    return STATUS_PREVIEWED if result.previewed else STATUS_SENT


def _open_conn() -> sqlite3.Connection:
    conn = get_connection()
    init_db(conn)
    notify_state.init_notify_state(conn)
    return conn


def _days_since(timestamp: str) -> int | None:
    """Whole days between an SQLite UTC timestamp and now (None if unparsable)."""
    if not timestamp:
        return None
    try:
        parsed = pd.Timestamp(timestamp)
    except (ValueError, TypeError):
        return None
    if parsed is None or pd.isna(parsed):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize("UTC")
    delta = pd.Timestamp.now(tz=timezone.utc) - parsed
    return max(0, int(delta.days))


def _first_position_tagger(
    conn: sqlite3.Connection, up_to_id: int
) -> Callable[[pd.Series], list[str]]:
    """Tag a buy as the member's first recorded trade in that ticker.

    Buys only: a "first" sale just means the purchase predates our records.
    ``up_to_id`` is the run's high-water mark rather than the row's own id, so a
    member who traded the same ticker twice in one batch is not flagged twice —
    the second one is not a new position.
    """
    cache: dict[tuple[str, str], int] = {}

    def tagger(row: pd.Series) -> list[str]:
        member = str(row.get("member") or "").strip()
        ticker = str(row.get("ticker") or "").strip().upper()
        if not member or not ticker or not bool(row.get("is_buy")):
            return []
        key = (member, ticker)
        if key not in cache:
            cache[key] = prior_trade_count(conn, member, ticker, up_to_id=up_to_id)
        return ["first buy on record"] if cache[key] <= 1 else []

    return tagger


def _deliver(
    text: str, settings: NotifySettings, *, dry_run: bool, silent: bool = False
) -> SendResult:
    return send_message(text, settings, dry_run=dry_run, silent=silent)


def _not_configured_outcome(settings: NotifySettings) -> RunOutcome:
    reason = (
        "CONGRESS_NOTIFY_ENABLED is off"
        if settings.configured
        else "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set"
    )
    return RunOutcome(status=STATUS_SKIPPED, message=f"notifications inactive: {reason}")


# --------------------------------------------------------------------------- #
# Event alerts (nightly)
# --------------------------------------------------------------------------- #
def run_event_notifications(
    *, dry_run: bool = False, settings: NotifySettings | None = None
) -> RunOutcome:
    settings = settings or load_settings()
    if not settings.active and not dry_run:
        return _not_configured_outcome(settings)

    conn = _open_conn()
    try:
        if not notify_state.is_bootstrapped(conn):
            # First ever run: the database already holds years of history, so
            # announce that alerts are armed instead of replaying the backlog.
            # State is written only after the message lands, and never on a
            # dry run — otherwise a preview would silently arm the notifier.
            high_water = notify_state.max_transaction_id(conn)
            total = total_transaction_count(conn)
            text = render_bootstrap_message(high_water=high_water, total_rows=total)
            result = _deliver(text, settings, dry_run=dry_run)
            if result.ok and not dry_run:
                notify_state.mark_bootstrapped(conn, high_water)
                notify_state.record_event_run(conn)
            return RunOutcome(
                status=STATUS_BOOTSTRAPPED if result.ok else STATUS_FAILED,
                message=(
                    f"first run: {total:,} existing rows would be marked as seen "
                    f"(high-water id {high_water:,}); {result.summary}"
                ),
                send=result,
            )

        after_id = notify_state.last_transaction_id(conn)
        new_count, max_id = new_transaction_stats(conn, after_id)
        if new_count == 0:
            notify_state.record_event_run(conn)
            return RunOutcome(
                status=STATUS_QUIET, message="no new transactions since last run"
            )

        new_rows = load_new_transactions(conn, after_id)
        recent = recent_filings(new_rows, max_age_days=settings.max_filing_age_days)
        old_count = len(new_rows) - len(recent)
        backfill = (
            f"; {old_count:,} filed over {settings.max_filing_age_days} days ago, not alerted"
            if old_count
            else ""
        )
        context_frame = _load_context_frame() if not recent.empty else None
        events = collect_events(
            recent,
            context_frame=context_frame,
            large_trade_usd=settings.large_trade_usd,
            option_trade_usd=settings.option_trade_usd,
            late_filing_days=settings.late_filing_days,
            cluster_min_members=settings.cluster_min_members,
            cluster_window_days=settings.cluster_window_days,
            cluster_is_new=lambda key, members: notify_state.cluster_is_new(
                conn, key, members
            ),
            tagger=_first_position_tagger(conn, max_id),
        )

        text = render_event_message(
            events,
            new_row_count=len(recent),
            max_events=settings.max_events_per_message,
            flood_threshold=settings.flood_threshold,
            links=DashboardLinks(settings.dashboard_url),
        )
        if not text:
            notify_state.set_last_transaction_id(conn, max_id)
            notify_state.record_event_run(conn)
            return RunOutcome(
                status=STATUS_QUIET,
                message=(
                    f"{new_count:,} new row(s), none notable{backfill} "
                    f"(high-water id → {max_id:,})"
                ),
            )

        result = _deliver(
            text, settings, dry_run=dry_run, silent=not is_urgent(events)
        )
        if not result.ok:
            notify_state.record_event_run(conn, error=result.summary)
            return RunOutcome(
                status=STATUS_FAILED,
                message=(
                    f"{len(events)} event(s) NOT delivered, high-water left at "
                    f"{after_id:,} for retry: {result.summary}"
                ),
                events=len(events),
                send=result,
            )

        if not dry_run:
            _record_sent_clusters(conn, events)
            notify_state.set_last_transaction_id(conn, max_id)
        notify_state.record_event_run(conn)
        return RunOutcome(
            status=_sent_status(result),
            message=(
                f"{len(events)} event(s) from {len(recent):,} recent row(s){backfill} - "
                f"{result.summary}"
            ),
            events=len(events),
            send=result,
        )
    finally:
        conn.close()


def _load_context_frame() -> pd.DataFrame | None:
    """Full prepared history, for cluster detection. None if it cannot load.

    Cluster detection is the one rule that needs history rather than the new
    rows alone. A failure here must not cost the whole run: the single-row
    alerts are still worth sending.
    """
    try:
        from ..api.repository import load_transactions

        frame, _ = load_transactions()
        return frame
    except Exception as exc:  # noqa: BLE001 - cluster context is best-effort
        logger.warning("Cluster context unavailable (%s); skipping cluster alerts", exc)
        return None


def _record_sent_clusters(conn: sqlite3.Connection, events: list[Event]) -> None:
    for event in events:
        if event.kind != KIND_CLUSTER or not event.dedupe_key:
            continue
        notify_state.record_cluster(conn, event.dedupe_key, int(event.sort_value))


# --------------------------------------------------------------------------- #
# Weekly digest
# --------------------------------------------------------------------------- #
def run_weekly_digest(
    *,
    dry_run: bool = False,
    force: bool = False,
    cooldown_hours: float | None = None,
    settings: NotifySettings | None = None,
) -> RunOutcome:
    """Send the weekly roundup.

    Self-gating: safe to call from the nightly cron every night. It sends only
    on the configured weekday and never twice on the same date, so the server
    needs one cron entry rather than two.

    ``cooldown_hours`` holds even when ``force`` is set: the dashboard's Refresh
    passes it so a second click (easy to make without noticing) does not send
    a second digest. The sidebar's explicit "Send digest again" omits it.
    """
    settings = settings or load_settings()
    if not settings.active and not dry_run:
        return _not_configured_outcome(settings)

    today = datetime.now(timezone.utc).date()
    if not force and today.weekday() != settings.digest_weekday:
        return RunOutcome(
            status=STATUS_SKIPPED,
            message=(
                f"not digest day (today weekday {today.weekday()}, "
                f"configured {settings.digest_weekday})"
            ),
        )

    conn = _open_conn()
    try:
        today_iso = today.isoformat()
        if not force and notify_state.last_digest_date(conn) == today_iso:
            return RunOutcome(
                status=STATUS_SKIPPED, message=f"digest already sent on {today_iso}"
            )
        hours_ago = notify_state.hours_since_last_digest(conn)
        if cooldown_hours is not None and hours_ago is not None and hours_ago < cooldown_hours:
            return RunOutcome(
                status=STATUS_SKIPPED,
                message=(
                    f"digest already sent {hours_ago:.1f}h ago "
                    f"({notify_state.last_digest_at(conn)}); not repeated within "
                    f"{cooldown_hours:g}h"
                ),
            )

        ingested = transactions_ingested_since(conn, DIGEST_WINDOW_DAYS)
        frame = recent_filings(ingested, max_age_days=settings.max_filing_age_days)
        old_count = len(ingested) - len(frame)
        events = collect_events(
            frame,
            context_frame=None,
            large_trade_usd=settings.large_trade_usd,
            option_trade_usd=settings.option_trade_usd,
            late_filing_days=settings.late_filing_days,
            cluster_min_members=settings.cluster_min_members,
            cluster_window_days=settings.cluster_window_days,
        )
        stats = compute_digest_stats(
            frame,
            events=events,
            total_rows=total_transaction_count(conn),
            stale_days=_days_since(newest_ingest_timestamp(conn)),
            window_days=DIGEST_WINDOW_DAYS,
        )
        if old_count:
            stats = replace(
                stats,
                notes=(
                    f"{plural(old_count, 'row')} from older filings (filed over "
                    f"{settings.max_filing_age_days} days ago) were loaded this "
                    "week and are not counted above.",
                ),
            )
        text = render_digest(
            stats,
            stale_threshold_days=settings.stale_ingest_days,
            links=DashboardLinks(settings.dashboard_url),
        )
        # The digest is a scheduled read, not news: it arrives without a sound.
        result = _deliver(text, settings, dry_run=dry_run, silent=True)
        if not result.ok:
            return RunOutcome(
                status=STATUS_FAILED,
                message=f"digest NOT delivered: {result.summary}",
                send=result,
            )
        if not dry_run:
            notify_state.record_digest_sent(conn, today_iso)
        return RunOutcome(
            status=_sent_status(result),
            message=f"weekly digest - {result.summary}",
            send=result,
        )
    finally:
        conn.close()


def last_digest_sent_at() -> str:
    """UTC timestamp of the last delivered digest ('' if none), for the dashboard."""
    conn = _open_conn()
    try:
        return notify_state.last_digest_at(conn)
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Operational one-shots
# --------------------------------------------------------------------------- #
def send_test_message(
    *, dry_run: bool = False, settings: NotifySettings | None = None
) -> RunOutcome:
    """Prove the token and chat id work. The cheapest answer to 'is it alive'."""
    settings = settings or load_settings()
    if not settings.active and not dry_run:
        return _not_configured_outcome(settings)
    result = _deliver(render_test_message(), settings, dry_run=dry_run)
    return RunOutcome(status=_sent_status(result), message=result.summary, send=result)


def send_failure_alert(
    detail: str, *, dry_run: bool = False, settings: NotifySettings | None = None
) -> RunOutcome:
    """Report that the nightly job itself died.

    Called from the cron wrapper's error trap, so it deliberately touches no
    notification state: the pipeline is already in an unknown condition.
    """
    settings = settings or load_settings()
    if not settings.active and not dry_run:
        return _not_configured_outcome(settings)
    result = _deliver(render_failure_message(detail), settings, dry_run=dry_run)
    return RunOutcome(status=_sent_status(result), message=result.summary, send=result)
