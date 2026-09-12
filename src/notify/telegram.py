"""Telegram delivery for tracker alerts.

Two deliberate differences from a fire-and-forget sender:

* **A failure is returned, never swallowed.** Callers get a ``SendResult`` and
  the CLI turns a failure into a non-zero exit code, so the nightly cron log
  records it. A bad bot token cannot be reported *over Telegram*, so the log
  and the exit code are the only channels that still work.
* **No permanent self-disable.** A 4xx marks the result ``permanent`` (there is
  no point retrying an invalid token within the same run) but the next run
  tries again — a token fixed in the morning must not need a restart to take
  effect.
"""
from __future__ import annotations

import logging
import re
import sys
import time
from dataclasses import dataclass
from html import escape as _html_escape
from html import unescape as _html_unescape

import requests

from .settings import NotifySettings

logger = logging.getLogger(__name__)

# Telegram rejects sendMessage bodies longer than this.
TELEGRAM_MAX_CHARS = 4096

# Status codes where retrying the same payload cannot help.
_PERMANENT_STATUS = frozenset({400, 401, 403, 404})


def escape(text: object) -> str:
    """Escape text for Telegram's HTML parse mode."""
    return _html_escape(str("" if text is None else text), quote=False)


@dataclass(frozen=True)
class SendResult:
    ok: bool
    status_code: int | None = None
    error: str = ""
    attempts: int = 0
    permanent: bool = False
    chunks_sent: int = 0
    skipped: bool = False
    previewed: bool = False

    @property
    def summary(self) -> str:
        if self.skipped:
            # Name the reason: "not configured" and "switched off" need
            # different fixes, and the log is where an operator looks.
            return f"skipped ({self.error or 'notifications not configured'})"
        if self.previewed:
            return f"previewed, not sent ({self.chunks_sent} message(s))"
        if self.ok:
            return f"sent ({self.chunks_sent} message(s), {self.attempts} attempt(s))"
        detail = self.error or "unknown error"
        status = f"HTTP {self.status_code}" if self.status_code else "no response"
        kind = "permanent" if self.permanent else "transient"
        return f"FAILED [{kind}] {status}: {detail}"


_TAG = re.compile(r"<[^>]+>")


def visible_length(text: str) -> int:
    """Length as Telegram counts it against the 4096 limit.

    The limit applies *after* HTML parsing, so tags and link addresses do not
    count, and it is measured in UTF-16 code units, so an emoji counts as two.
    Measuring raw HTML instead split a message full of dashboard links in two
    while it was well under the limit.
    """
    visible = _html_unescape(_TAG.sub("", text))
    return len(visible.encode("utf-16-le")) // 2


def split_message(text: str, limit: int = TELEGRAM_MAX_CHARS) -> list[str]:
    """Split a message on line boundaries so no chunk exceeds ``limit``.

    Every rendered line carries balanced tags, so a line boundary is always a
    safe cut. A single line longer than the limit is hard-cut; alert lines are
    built from bounded fields, so that path is a safety net rather than the
    normal case.
    """
    text = text.strip("\n")
    if not text:
        return []
    if visible_length(text) <= limit:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.split("\n"):
        while visible_length(line) > limit:
            if current:
                chunks.append("\n".join(current))
                current, current_len = [], 0
            chunks.append(line[:limit])
            line = line[limit:]
        # +1 for the newline that will rejoin this line to the previous one.
        extra = visible_length(line) + (1 if current else 0)
        if current_len + extra > limit:
            chunks.append("\n".join(current))
            current, current_len = [line], len(line)
        else:
            current.append(line)
            current_len += extra
    if current:
        chunks.append("\n".join(current))
    return [c for c in chunks if c.strip()]


def _print_preview(text: str) -> None:
    """Print a message on a console that may not speak UTF-8.

    ``--dry-run`` is what an operator uses to preview an alert, and a Windows
    console defaults to cp1252: printing the emoji headers raises
    ``UnicodeEncodeError`` and loses the preview entirely. Unrepresentable
    characters degrade to ``?`` here; the real payload goes out as UTF-8 over
    HTTP and is unaffected.
    """
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    safe = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    sys.stdout.write(safe + "\n")


def _api_url(settings: NotifySettings) -> str:
    return f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"


def _post_once(
    url: str,
    payload: dict[str, object],
    settings: NotifySettings,
    session: requests.Session | None,
) -> tuple[bool, int | None, str]:
    poster = session.post if session is not None else requests.post
    try:
        response = poster(url, data=payload, timeout=settings.request_timeout)
    except requests.exceptions.RequestException as exc:  # network, DNS, timeout
        return False, None, str(exc)
    if response.status_code == 200:
        return True, 200, ""
    # Telegram puts a human-readable reason in the JSON body; fall back to text.
    detail = ""
    try:
        body = response.json()
        detail = str(body.get("description") or "").strip()
    except (ValueError, AttributeError):
        detail = (getattr(response, "text", "") or "").strip()[:200]
    return False, response.status_code, detail


def send_message(
    text: str,
    settings: NotifySettings,
    *,
    session: requests.Session | None = None,
    dry_run: bool = False,
    silent: bool = False,
) -> SendResult:
    """Deliver ``text`` (Telegram HTML) to the configured chat.

    ``silent`` delivers without a notification sound: the message still lands
    and shows as unread, it just does not buzz the phone.
    """
    chunks = split_message(text)
    if not chunks:
        return SendResult(ok=True, chunks_sent=0)

    if dry_run:
        for chunk in chunks:
            _print_preview(chunk)
            _print_preview("-" * 40)
        return SendResult(ok=True, chunks_sent=len(chunks), previewed=True)

    if not settings.active:
        reason = (
            "CONGRESS_NOTIFY_ENABLED is off"
            if settings.configured
            else "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set"
        )
        logger.warning("Telegram send skipped: %s", reason)
        return SendResult(ok=False, error=reason, skipped=True)

    url = _api_url(settings)
    attempts = 0
    sent = 0
    for chunk in chunks:
        payload = {
            "chat_id": settings.chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if silent:
            payload["disable_notification"] = True
        for attempt in range(max(1, settings.max_retries)):
            attempts += 1
            ok, status, detail = _post_once(url, payload, settings, session)
            if ok:
                sent += 1
                break
            if status in _PERMANENT_STATUS:
                logger.error(
                    "Telegram rejected the message permanently (HTTP %s): %s. "
                    "Check TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID.",
                    status,
                    detail,
                )
                return SendResult(
                    ok=False,
                    status_code=status,
                    error=detail,
                    attempts=attempts,
                    permanent=True,
                    chunks_sent=sent,
                )
            logger.warning(
                "Telegram send failed (attempt %s/%s, HTTP %s): %s",
                attempt + 1,
                settings.max_retries,
                status,
                detail,
            )
            if attempt < settings.max_retries - 1 and settings.retry_delay > 0:
                time.sleep(settings.retry_delay)
        else:
            return SendResult(
                ok=False,
                status_code=None,
                error="retries exhausted",
                attempts=attempts,
                chunks_sent=sent,
            )
    logger.info("Telegram message delivered (%s chunk(s))", sent)
    return SendResult(ok=True, status_code=200, attempts=attempts, chunks_sent=sent)
