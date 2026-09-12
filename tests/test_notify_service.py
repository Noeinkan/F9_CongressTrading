"""Orchestration invariants.

The one that matters most: a delivery failure must not advance the high-water
mark. If it did, a single Telegram outage would drop those events forever —
which is exactly how a notification channel goes quiet without anyone noticing.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.db import get_connection
from src.notify import service
from src.notify import state as notify_state
from src.notify.settings import NotifySettings
from src.notify.telegram import SendResult


def _settings(**over) -> NotifySettings:
    base = dict(
        bot_token="token",
        chat_id="12345",
        enabled=True,
        large_trade_usd=50_000.0,
        option_trade_usd=15_000.0,
        cluster_min_members=3,
        cluster_window_days=45,
        late_filing_days=45,
        max_events_per_message=12,
        flood_threshold=250,
        request_timeout=5.0,
        max_retries=1,
        retry_delay=0.0,
        digest_weekday=0,
        stale_ingest_days=10,
    )
    base.update(over)
    return NotifySettings(**base)


def _days_ago(days: int) -> str:
    """Relative dates: alerts skip filings older than a month, so fixed ones rot."""
    return (date.today() - timedelta(days=days)).isoformat()


@pytest.fixture(autouse=True)
def _no_cluster_context(monkeypatch):
    """Cluster context is covered in test_notify_events.

    Left live, ``_load_context_frame`` falls back to the repo's committed
    ``data/congress_trades.csv`` when the test database is empty, quietly
    pulling production rows into a unit test.
    """
    monkeypatch.setattr(service, "_load_context_frame", lambda: None)


class _Recorder:
    """Stands in for ``send_message``; records payloads, returns a fixed result."""

    def __init__(self, result: SendResult):
        self.result = result
        self.messages: list[str] = []
        self.silent: list[bool] = []

    def __call__(self, text, settings, *, session=None, dry_run=False, silent=False):
        self.messages.append(text)
        self.silent.append(silent)
        return self.result


def _seed_trade(
    conn,
    *,
    member: str = "Alice Example",
    ticker: str = "EXC",
    amount_low: float = 1_001.0,
    amount_high: float = 15_000.0,
    transaction_type: str = "P",
    transaction_date: str | None = None,
    filing_date: str | None = None,
    source_hash: str | None = None,
) -> int:
    transaction_date = transaction_date or _days_ago(12)
    filing_date = filing_date or _days_ago(3)
    row = conn.execute(
        "SELECT id FROM members WHERE full_name = ?", (member,)
    ).fetchone()
    if row is None:
        cur = conn.execute(
            """
            INSERT INTO members (full_name, normalized_name, chamber, state, party)
            VALUES (?, ?, 'House', 'CA', 'D')
            """,
            (member, member.lower().replace(" ", "")),
        )
        member_id = int(cur.lastrowid)
    else:
        member_id = int(row[0])

    # One filing per seeded trade, with a unique doc_id: filings carry a UNIQUE
    # constraint across member/chamber/type/date/doc_id/path.
    seq = int(conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0]) + 1
    cur = conn.execute(
        """
        INSERT INTO filings (
            member_id, chamber, filing_type, filing_date, doc_id,
            source_url, raw_document_path, source_hash
        ) VALUES (?, 'House', 'PTR', ?, ?, '', '', ?)
        """,
        (member_id, filing_date, f"doc-{seq}", f"f{seq}"),
    )
    filing_id = int(cur.lastrowid)

    unique = source_hash or f"h{filing_id}-{ticker}-{amount_low}"
    cur = conn.execute(
        """
        INSERT INTO transactions (
            filing_id, transaction_date, asset_name_raw, asset_name_normalized,
            asset_type, ticker, transaction_type, amount_low, amount_high,
            amount_range_raw, source_hash
        ) VALUES (?, ?, ?, ?, 'stock', ?, ?, ?, ?, ?, ?)
        """,
        (
            filing_id,
            transaction_date,
            f"{ticker} Common Stock",
            ticker.lower(),
            ticker,
            transaction_type,
            amount_low,
            amount_high,
            f"${amount_low:,.0f} - ${amount_high:,.0f}",
            unique,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def _arm(conn) -> None:
    """Put the notifier in its normal steady state (backlog already seen)."""
    notify_state.init_notify_state(conn)
    notify_state.mark_bootstrapped(conn, notify_state.max_transaction_id(conn))


# --------------------------------------------------------------------------- #
# Bootstrap
# --------------------------------------------------------------------------- #
def test_first_run_arms_instead_of_replaying_the_backlog(monkeypatch):
    conn = get_connection()
    try:
        _seed_trade(conn, amount_low=100_000.0, amount_high=250_000.0)
        _seed_trade(conn, ticker="AAA", amount_low=100_000.0, amount_high=250_000.0)
        max_id = notify_state.max_transaction_id(conn)
    finally:
        conn.close()

    sender = _Recorder(SendResult(ok=True, chunks_sent=1))
    monkeypatch.setattr(service, "send_message", sender)

    outcome = service.run_event_notifications(settings=_settings())
    assert outcome.status == service.STATUS_BOOTSTRAPPED
    assert len(sender.messages) == 1
    assert "alerts armed" in sender.messages[0]
    # Two large trades existed, and neither was announced.
    assert "$100K" not in sender.messages[0]

    conn = get_connection()
    try:
        assert notify_state.last_transaction_id(conn) == max_id
        assert notify_state.is_bootstrapped(conn)
    finally:
        conn.close()


def test_failed_bootstrap_does_not_arm_so_it_retries(monkeypatch):
    conn = get_connection()
    try:
        _seed_trade(conn)
    finally:
        conn.close()

    sender = _Recorder(SendResult(ok=False, status_code=401, error="Unauthorized"))
    monkeypatch.setattr(service, "send_message", sender)

    outcome = service.run_event_notifications(settings=_settings())
    assert outcome.status == service.STATUS_FAILED

    conn = get_connection()
    try:
        assert not notify_state.is_bootstrapped(conn)
        assert notify_state.last_transaction_id(conn) == 0
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Steady state
# --------------------------------------------------------------------------- #
def test_notable_trade_is_sent_and_the_mark_advances(monkeypatch):
    conn = get_connection()
    try:
        _arm(conn)
        new_id = _seed_trade(conn, amount_low=50_001.0, amount_high=100_000.0)
    finally:
        conn.close()

    sender = _Recorder(SendResult(ok=True, chunks_sent=1))
    monkeypatch.setattr(service, "send_message", sender)

    outcome = service.run_event_notifications(settings=_settings())
    assert outcome.status == service.STATUS_SENT
    assert outcome.events == 1
    assert "EXC" in sender.messages[0]
    assert sender.silent == [False], "a large trade is worth a notification sound"

    conn = get_connection()
    try:
        assert notify_state.last_transaction_id(conn) == new_id
    finally:
        conn.close()


def test_first_buy_tag_is_never_put_on_a_sale(monkeypatch):
    conn = get_connection()
    try:
        _arm(conn)
        _seed_trade(conn, ticker="BUYS", amount_low=50_001.0, amount_high=100_000.0)
        _seed_trade(
            conn, ticker="SELLS", amount_low=50_001.0, amount_high=100_000.0,
            transaction_type="S",
        )
    finally:
        conn.close()

    sender = _Recorder(SendResult(ok=True, chunks_sent=1))
    monkeypatch.setattr(service, "send_message", sender)
    service.run_event_notifications(settings=_settings())

    lines = sender.messages[0].splitlines()
    buy = next(line for line in lines if "BUYS" in line)
    sell = next(line for line in lines if "SELLS" in line)
    assert "first buy on record" in buy
    assert "first buy on record" not in sell


def test_run_with_only_late_filings_is_delivered_silently(monkeypatch):
    conn = get_connection()
    try:
        _arm(conn)
        _seed_trade(conn, transaction_date=_days_ago(100), filing_date=_days_ago(5))
    finally:
        conn.close()

    sender = _Recorder(SendResult(ok=True, chunks_sent=1))
    monkeypatch.setattr(service, "send_message", sender)
    outcome = service.run_event_notifications(settings=_settings())
    assert outcome.status == service.STATUS_SENT
    assert sender.silent == [True]


def test_delivery_failure_leaves_the_mark_for_the_next_run(monkeypatch):
    conn = get_connection()
    try:
        _arm(conn)
        before = notify_state.last_transaction_id(conn)
        _seed_trade(conn, amount_low=50_001.0, amount_high=100_000.0)
    finally:
        conn.close()

    failing = _Recorder(SendResult(ok=False, status_code=500, error="server error"))
    monkeypatch.setattr(service, "send_message", failing)
    outcome = service.run_event_notifications(settings=_settings())
    assert outcome.status == service.STATUS_FAILED
    assert not outcome.ok

    conn = get_connection()
    try:
        assert notify_state.last_transaction_id(conn) == before, (
            "an outage must delay alerts, never drop them"
        )
        assert "500" in notify_state.get_state(
            conn, notify_state.LAST_DELIVERY_ERROR
        )
    finally:
        conn.close()

    # The retry on the next night delivers the same event.
    working = _Recorder(SendResult(ok=True, chunks_sent=1))
    monkeypatch.setattr(service, "send_message", working)
    retry = service.run_event_notifications(settings=_settings())
    assert retry.status == service.STATUS_SENT
    assert "EXC" in working.messages[0]


def test_quiet_run_sends_nothing_but_still_advances_the_mark(monkeypatch):
    conn = get_connection()
    try:
        _arm(conn)
        new_id = _seed_trade(conn, amount_low=1_001.0, amount_high=15_000.0)
    finally:
        conn.close()

    sender = _Recorder(SendResult(ok=True, chunks_sent=1))
    monkeypatch.setattr(service, "send_message", sender)

    outcome = service.run_event_notifications(settings=_settings())
    assert outcome.status == service.STATUS_QUIET
    assert sender.messages == [], "an unremarkable trade must not produce a message"

    conn = get_connection()
    try:
        assert notify_state.last_transaction_id(conn) == new_id, (
            "rows already judged unremarkable must not be re-examined forever"
        )
    finally:
        conn.close()


def test_backfilled_old_filings_are_loaded_but_never_announced(monkeypatch):
    conn = get_connection()
    try:
        _arm(conn)
        new_id = _seed_trade(
            conn,
            ticker="OLD",
            amount_low=500_001.0,
            amount_high=1_000_000.0,
            transaction_date="2023-05-01",
            filing_date="2023-05-20",
        )
    finally:
        conn.close()

    sender = _Recorder(SendResult(ok=True, chunks_sent=1))
    monkeypatch.setattr(service, "send_message", sender)

    outcome = service.run_event_notifications(settings=_settings())
    assert outcome.status == service.STATUS_QUIET
    assert sender.messages == [], "a 2023 filing loaded tonight is not today's news"
    assert "not alerted" in outcome.message

    conn = get_connection()
    try:
        assert notify_state.last_transaction_id(conn) == new_id
    finally:
        conn.close()


def test_backfill_does_not_hide_a_recent_filing_in_the_same_batch(monkeypatch):
    conn = get_connection()
    try:
        _arm(conn)
        _seed_trade(
            conn, ticker="OLD", amount_low=500_001.0, amount_high=1_000_000.0,
            transaction_date="2023-05-01", filing_date="2023-05-20",
        )
        _seed_trade(conn, ticker="NEW", amount_low=50_001.0, amount_high=100_000.0)
    finally:
        conn.close()

    sender = _Recorder(SendResult(ok=True, chunks_sent=1))
    monkeypatch.setattr(service, "send_message", sender)

    outcome = service.run_event_notifications(settings=_settings())
    assert outcome.status == service.STATUS_SENT
    assert "NEW" in sender.messages[0]
    assert "OLD" not in sender.messages[0]
    assert "1 new disclosure row" in sender.messages[0]


def test_age_limit_zero_turns_the_guard_off(monkeypatch):
    conn = get_connection()
    try:
        _arm(conn)
        _seed_trade(
            conn, ticker="OLD", amount_low=500_001.0, amount_high=1_000_000.0,
            transaction_date="2023-05-01", filing_date="2023-05-20",
        )
    finally:
        conn.close()

    sender = _Recorder(SendResult(ok=True, chunks_sent=1))
    monkeypatch.setattr(service, "send_message", sender)

    outcome = service.run_event_notifications(settings=_settings(max_filing_age_days=0))
    assert outcome.status == service.STATUS_SENT
    assert "OLD" in sender.messages[0]


def test_no_new_rows_is_silent(monkeypatch):
    conn = get_connection()
    try:
        _arm(conn)
    finally:
        conn.close()

    sender = _Recorder(SendResult(ok=True, chunks_sent=1))
    monkeypatch.setattr(service, "send_message", sender)

    outcome = service.run_event_notifications(settings=_settings())
    assert outcome.status == service.STATUS_QUIET
    assert sender.messages == []


def test_inactive_settings_skip_without_touching_the_database(monkeypatch):
    sender = _Recorder(SendResult(ok=True))
    monkeypatch.setattr(service, "send_message", sender)
    outcome = service.run_event_notifications(settings=_settings(bot_token=""))
    assert outcome.status == service.STATUS_SKIPPED
    assert "TELEGRAM_BOT_TOKEN" in outcome.message
    assert sender.messages == []


# --------------------------------------------------------------------------- #
# Digest gating
# --------------------------------------------------------------------------- #
def test_digest_skips_when_today_is_not_the_configured_weekday(monkeypatch):
    sender = _Recorder(SendResult(ok=True, chunks_sent=1))
    monkeypatch.setattr(service, "send_message", sender)
    # Pick whichever weekday today is not, so the test is date-independent.
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date().weekday()
    outcome = service.run_weekly_digest(settings=_settings(digest_weekday=(today + 1) % 7))
    assert outcome.status == service.STATUS_SKIPPED
    assert sender.messages == []


def test_digest_sends_once_per_day(monkeypatch):
    conn = get_connection()
    try:
        _seed_trade(conn)
    finally:
        conn.close()

    sender = _Recorder(SendResult(ok=True, chunks_sent=1))
    monkeypatch.setattr(service, "send_message", sender)

    first = service.run_weekly_digest(settings=_settings(), force=True)
    assert first.status == service.STATUS_SENT
    assert len(sender.messages) == 1

    # force=True bypasses the guard; without it the same day is a no-op.
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date()
    second = service.run_weekly_digest(
        settings=_settings(digest_weekday=today.weekday())
    )
    assert second.status == service.STATUS_SKIPPED
    assert len(sender.messages) == 1


def test_digest_cooldown_holds_even_when_forced(monkeypatch):
    """A second Refresh click must not send a second digest; the explicit resend may."""
    conn = get_connection()
    try:
        _seed_trade(conn)
    finally:
        conn.close()

    sender = _Recorder(SendResult(ok=True, chunks_sent=1))
    monkeypatch.setattr(service, "send_message", sender)

    first = service.run_weekly_digest(settings=_settings(), force=True, cooldown_hours=12)
    assert first.status == service.STATUS_SENT
    assert service.last_digest_sent_at().endswith("Z")

    second = service.run_weekly_digest(settings=_settings(), force=True, cooldown_hours=12)
    assert second.status == service.STATUS_SKIPPED
    assert "already sent" in second.message
    assert len(sender.messages) == 1

    resend = service.run_weekly_digest(settings=_settings(), force=True)
    assert resend.status == service.STATUS_SENT
    assert len(sender.messages) == 2


def test_failed_digest_does_not_start_the_cooldown(monkeypatch):
    conn = get_connection()
    try:
        _seed_trade(conn)
    finally:
        conn.close()

    monkeypatch.setattr(service, "send_message", _Recorder(SendResult(ok=False, error="401")))
    failed = service.run_weekly_digest(settings=_settings(), force=True, cooldown_hours=12)
    assert failed.status == service.STATUS_FAILED
    assert service.last_digest_sent_at() == ""

    sender = _Recorder(SendResult(ok=True, chunks_sent=1))
    monkeypatch.setattr(service, "send_message", sender)
    retry = service.run_weekly_digest(settings=_settings(), force=True, cooldown_hours=12)
    assert retry.status == service.STATUS_SENT


def test_digest_leaves_backfilled_rows_out_of_the_week(monkeypatch):
    conn = get_connection()
    try:
        _seed_trade(conn, ticker="NEW")
        _seed_trade(conn, ticker="OLD", transaction_date="2023-05-01", filing_date="2023-05-20")
    finally:
        conn.close()

    sender = _Recorder(SendResult(ok=True, chunks_sent=1))
    monkeypatch.setattr(service, "send_message", sender)

    outcome = service.run_weekly_digest(settings=_settings(), force=True)
    assert outcome.status == service.STATUS_SENT
    text = sender.messages[0]
    assert "1 new row" in text
    assert "1 row from older filings" in text


def test_failure_alert_does_not_touch_notification_state(monkeypatch):
    sender = _Recorder(SendResult(ok=True, chunks_sent=1))
    monkeypatch.setattr(service, "send_message", sender)
    outcome = service.send_failure_alert("ingest-all died", settings=_settings())
    assert outcome.status == service.STATUS_SENT
    assert "ingest-all died" in sender.messages[0]
