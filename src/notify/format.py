"""Rendering of events into Telegram HTML.

Telegram's HTML mode accepts a short tag whitelist (``b``, ``i``, ``a``,
``code``, ...) and nothing else, so structure here is carried by line breaks,
bullets and emoji rather than markup. Every piece of database text passes
through :func:`src.notify.telegram.escape` — an asset name containing ``&`` or
``<`` would otherwise make Telegram reject the whole message with a 400.

One message per run, never one per event: that is the difference between a
channel worth reading and a channel that gets muted.
"""
from __future__ import annotations

from html import escape as _html_escape

import pandas as pd

from .events import KIND_CAPS, KIND_LABELS, KIND_ORDER, Event
from .telegram import escape

_KIND_EMOJI: dict[str, str] = {
    "option_trade": "🎯",
    "large_trade": "💵",
    "cluster": "👥",
    "late_filing": "⏰",
}


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    """``3 trades`` / ``1 trade`` — a message read daily should not say "1 trades"."""
    word = singular if abs(count) == 1 else (plural_form or f"{singular}s")
    return f"{count:,} {word}"


def _attr(value: object) -> str:
    return _html_escape(str("" if value is None else value), quote=True)


def _link(url: str, label: str = "disclosure") -> str:
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return ""
    return f'<a href="{_attr(url)}">{escape(label)}</a>'


def _today_label(when: object = None) -> str:
    ts = pd.Timestamp(when) if when is not None else pd.Timestamp.now()
    return ts.strftime("%d %b %Y")


def _render_event(event: Event) -> list[str]:
    out = [f"• <b>{escape(event.title)}</b>"]
    for line in event.lines:
        if line and str(line).strip():
            out.append(f"  {escape(line)}")
    link = _link(event.url)
    if link:
        out.append(f"  {link}")
    return out


def render_event_message(
    events: list[Event],
    *,
    new_row_count: int,
    when: object = None,
    max_events: int = 12,
    flood_threshold: int = 250,
) -> str:
    """One message for a whole run. Empty string when there is nothing to say."""
    if not events:
        return ""

    header = [
        f"🏛 <b>Congress trades — {escape(_today_label(when))}</b>",
        escape(
            f"{plural(new_row_count, 'new disclosure row')} ingested · "
            f"{len(events)} notable"
        ),
    ]
    if new_row_count >= flood_threshold:
        header.append(
            escape(
                "Bulk filing batch — only the most notable are listed; "
                "see the dashboard for the full set."
            )
        )

    body: list[str] = []
    shown = 0
    omitted = 0
    for kind in KIND_ORDER:
        in_kind = sorted(
            (e for e in events if e.kind == kind),
            key=lambda e: e.sort_value,
            reverse=True,
        )
        if not in_kind:
            continue
        cap = min(KIND_CAPS.get(kind, max_events), max(0, max_events - shown))
        visible = in_kind[:cap]
        if not visible:
            omitted += len(in_kind)
            continue
        emoji = _KIND_EMOJI.get(kind, "•")
        body.append("")
        body.append(f"{emoji} <b>{escape(KIND_LABELS.get(kind, kind))}</b>")
        for event in visible:
            body.extend(_render_event(event))
        hidden = len(in_kind) - len(visible)
        if hidden > 0:
            body.append(escape(f"  … and {hidden} more"))
            omitted += hidden
        shown += len(visible)

    if omitted:
        body.append("")
        body.append(escape(f"{plural(omitted, 'further event')} not listed."))

    return "\n".join(header + body)


def render_bootstrap_message(*, high_water: int, total_rows: int) -> str:
    return "\n".join(
        [
            "🏛 <b>Congress trades — alerts armed</b>",
            escape(
                f"Existing history ({total_rows:,} rows) marked as seen at id "
                f"{high_water:,}. From the next ingest onward you will get a "
                "message only when something notable lands."
            ),
        ]
    )


def render_test_message() -> str:
    return "\n".join(
        [
            "🏛 <b>Congress trades — test message</b>",
            escape(
                "Delivery works: bot token and chat id are valid. "
                "This is the only message this command sends."
            ),
        ]
    )


def render_failure_message(detail: str, *, when: object = None) -> str:
    return "\n".join(
        [
            "🚨 <b>Congress trades — nightly job failed</b>",
            escape(_today_label(when)),
            escape(detail.strip() or "No detail captured."),
            escape("Check: journalctl / /var/log/f9-congress-trading/ingest.log"),
        ]
    )
