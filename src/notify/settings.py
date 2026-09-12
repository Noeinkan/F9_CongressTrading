"""Env-driven settings for outbound notifications.

Kept out of ``src/config.py`` on purpose: these are the alerting thresholds an
operator actually tunes on the VPS, and they only matter to ``src/notify/``.

Credentials reuse the same variable names as the other trackers on the same
host (``TELEGRAM_BOT_TOKEN`` / ``TELEGRAM_CHAT_ID``) so one bot can serve them
all without a second naming scheme to remember.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# Imported for its side effect: src/config.py calls load_dotenv() at import
# time. Without this, reaching the notifier by any route that does not go
# through the CLI (a systemd unit calling the module, a one-off python -c) would
# read an empty environment and report "not configured" even with a filled .env.
from .. import config as _config  # noqa: F401


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip().replace("_", "").replace(",", "")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    value = _env_float(name, float(default))
    try:
        return int(value)
    except (OverflowError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass(frozen=True)
class NotifySettings:
    """Everything the notifier reads from the environment."""

    bot_token: str
    chat_id: str
    enabled: bool

    # Event thresholds
    large_trade_usd: float
    option_trade_usd: float
    cluster_min_members: int
    cluster_window_days: int
    late_filing_days: int

    # Message shaping
    max_events_per_message: int
    flood_threshold: int

    # Delivery
    request_timeout: float
    max_retries: int
    retry_delay: float

    # Digest
    digest_weekday: int  # 0 = Monday, 6 = Sunday
    stale_ingest_days: int

    # Public address of the dashboard; empty means messages carry no links to it.
    dashboard_url: str = ""

    # Rows filed longer ago than this are loaded but never alerted on (0 = off).
    max_filing_age_days: int = 30

    @property
    def configured(self) -> bool:
        """True when a message could actually be delivered."""
        return bool(self.bot_token.strip() and self.chat_id.strip())

    @property
    def active(self) -> bool:
        return self.enabled and self.configured


def load_settings() -> NotifySettings:
    return NotifySettings(
        bot_token=(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip(),
        chat_id=(os.getenv("TELEGRAM_CHAT_ID") or "").strip(),
        enabled=_env_bool("CONGRESS_NOTIFY_ENABLED", True),
        # $100k floor: the disclosed *lower* bound must clear it, so a
        # "$100,001 - $250,000" bucket qualifies and a "$50,001 - $100,000"
        # does not. Conservative by design — ranges are all Congress discloses.
        large_trade_usd=_env_float("CONGRESS_NOTIFY_LARGE_TRADE_USD", 100_000.0),
        # Options are rare and directional, so they earn a lower bar.
        option_trade_usd=_env_float("CONGRESS_NOTIFY_OPTION_TRADE_USD", 15_000.0),
        cluster_min_members=_env_int("CONGRESS_NOTIFY_CLUSTER_MIN_MEMBERS", 3),
        cluster_window_days=_env_int("CONGRESS_NOTIFY_CLUSTER_WINDOW_DAYS", 45),
        # STOCK Act: a PTR is due 30 days after notice, 45 days after the trade.
        late_filing_days=_env_int("CONGRESS_NOTIFY_LATE_FILING_DAYS", 45),
        max_events_per_message=_env_int("CONGRESS_NOTIFY_MAX_EVENTS", 12),
        # Above this many new rows the run reports a summary instead of a list:
        # filing deadlines land hundreds of transactions in one night.
        flood_threshold=_env_int("CONGRESS_NOTIFY_FLOOD_THRESHOLD", 250),
        request_timeout=_env_float("CONGRESS_NOTIFY_TIMEOUT_SECONDS", 15.0),
        max_retries=_env_int("CONGRESS_NOTIFY_MAX_RETRIES", 3),
        retry_delay=_env_float("CONGRESS_NOTIFY_RETRY_DELAY_SECONDS", 5.0),
        digest_weekday=_env_int("CONGRESS_NOTIFY_DIGEST_WEEKDAY", 0),
        stale_ingest_days=_env_int("CONGRESS_NOTIFY_STALE_INGEST_DAYS", 10),
        dashboard_url=(os.getenv("CONGRESS_DASHBOARD_URL") or "").strip(),
        # A month, not a week: long enough that a pipeline outage of a few weeks
        # still delivers its alerts late, short enough that a backfill of old
        # filings stays silent.
        max_filing_age_days=_env_int("CONGRESS_NOTIFY_MAX_FILING_AGE_DAYS", 30),
    )
