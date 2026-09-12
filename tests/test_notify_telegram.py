"""Delivery behaviour: splitting, escaping, retries, and loud failures."""
from __future__ import annotations

import requests

from src.notify.settings import NotifySettings
from src.notify.telegram import (
    TELEGRAM_MAX_CHARS,
    escape,
    send_message,
    split_message,
)


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
        max_retries=3,
        retry_delay=0.0,  # no sleeping in tests
        digest_weekday=0,
        stale_ingest_days=10,
    )
    base.update(over)
    return NotifySettings(**base)


class _Response:
    def __init__(self, status_code: int, description: str = ""):
        self.status_code = status_code
        self._description = description
        self.text = description

    def json(self) -> dict:
        return {"ok": self.status_code == 200, "description": self._description}


class _Session:
    """Replays a scripted list of responses and records every call."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url, data=None, timeout=None):
        self.calls.append({"url": url, "data": data, "timeout": timeout})
        if not self._responses:
            return _Response(200)
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


# --------------------------------------------------------------------------- #
# Splitting
# --------------------------------------------------------------------------- #
def test_short_message_is_one_chunk():
    assert split_message("hello\nworld") == ["hello\nworld"]


def test_empty_message_produces_no_chunks():
    assert split_message("") == []
    assert split_message("\n\n") == []


def test_long_message_splits_on_line_boundaries():
    line = "x" * 100
    text = "\n".join([line] * 60)  # 6059 chars, over the 4096 limit
    chunks = split_message(text)
    assert len(chunks) > 1
    assert all(len(c) <= TELEGRAM_MAX_CHARS for c in chunks)
    # No line was cut in half: every chunk is whole 100-char lines.
    for chunk in chunks:
        assert all(len(part) == 100 for part in chunk.split("\n"))


def test_single_overlong_line_is_hard_cut():
    chunks = split_message("y" * (TELEGRAM_MAX_CHARS + 50))
    assert len(chunks) == 2
    assert all(len(c) <= TELEGRAM_MAX_CHARS for c in chunks)


# --------------------------------------------------------------------------- #
# Escaping
# --------------------------------------------------------------------------- #
def test_escape_protects_telegram_html_parsing():
    """An asset name with '&' or '<' would otherwise get the message 400'd."""
    assert escape("AT&T <Class A>") == "AT&amp;T &lt;Class A&gt;"


# --------------------------------------------------------------------------- #
# Sending
# --------------------------------------------------------------------------- #
def test_successful_send_posts_once():
    session = _Session(_Response(200))
    result = send_message("hi", _settings(), session=session)
    assert result.ok
    assert result.chunks_sent == 1
    assert len(session.calls) == 1
    assert session.calls[0]["data"]["chat_id"] == "12345"
    assert session.calls[0]["data"]["parse_mode"] == "HTML"


def test_invalid_token_fails_permanently_without_retrying():
    """A 401 cannot be fixed by retrying the same payload in the same run."""
    session = _Session(_Response(401, "Unauthorized"))
    result = send_message("hi", _settings(), session=session)
    assert not result.ok
    assert result.permanent
    assert result.status_code == 401
    assert len(session.calls) == 1, "must not hammer Telegram with a bad token"
    assert "Unauthorized" in result.summary


def test_transient_error_is_retried_then_succeeds():
    session = _Session(_Response(500, "server error"), _Response(200))
    result = send_message("hi", _settings(), session=session)
    assert result.ok
    assert len(session.calls) == 2


def test_network_exception_is_retried_and_reported_when_exhausted():
    session = _Session(
        requests.exceptions.ConnectTimeout("boom"),
        requests.exceptions.ConnectTimeout("boom"),
        requests.exceptions.ConnectTimeout("boom"),
    )
    result = send_message("hi", _settings(max_retries=3), session=session)
    assert not result.ok
    assert not result.permanent, "a timeout may well succeed tomorrow"
    assert len(session.calls) == 3


def test_send_is_skipped_when_credentials_are_missing():
    session = _Session(_Response(200))
    result = send_message("hi", _settings(bot_token=""), session=session)
    assert not result.ok
    assert result.skipped
    assert session.calls == [], "no network call without credentials"
    assert "TELEGRAM_BOT_TOKEN" in result.summary


def test_disabled_flag_skips_sending_even_with_credentials():
    session = _Session(_Response(200))
    result = send_message("hi", _settings(enabled=False), session=session)
    assert result.skipped
    assert session.calls == []


def test_dry_run_never_touches_the_network(capsys):
    session = _Session(_Response(200))
    result = send_message("preview me", _settings(), session=session, dry_run=True)
    assert result.ok
    assert result.previewed
    assert session.calls == []
    assert "preview me" in capsys.readouterr().out
