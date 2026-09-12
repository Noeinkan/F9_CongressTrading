"""Rendering of events into Telegram HTML.

Telegram's HTML mode accepts a short tag whitelist (``b``, ``i``, ``a``,
``code``, ...) and nothing else, so structure here is carried by line breaks,
bullets and emoji rather than markup. Every piece of database text passes
through :func:`src.notify.telegram.escape` — an asset name containing ``&`` or
``<`` would otherwise make Telegram reject the whole message with a 400.

One message per run, never one per event: that is the difference between a
channel worth reading and a channel that gets muted. Inside it, rows from the
same filing sit under one member heading, and repeats of the same action on the
same asset fold into one line with a total — a form listing six sales of one
stock is one story, not six.
"""
from __future__ import annotations

import pandas as pd

from .events import (
    KIND_CAPS,
    KIND_CLUSTER,
    KIND_LABELS,
    KIND_LATE,
    KIND_ORDER,
    Event,
    display_name,
)
from .links import DashboardLinks, anchor
from .money import disclosed_range
from .telegram import escape

_KIND_EMOJI: dict[str, str] = {
    "option_trade": "🎯",
    "large_trade": "💵",
    "cluster": "👥",
    "late_filing": "⏰",
}
_DIRECTION_EMOJI: dict[str, str] = {"buy": "🟢", "sell": "🔴"}

# Rows shown under one member heading before "… N more on this filing".
_TRADES_PER_FILING = 4
# Member names listed on a cluster before "+N".
_CLUSTER_NAMES = 6


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    """``3 trades`` / ``1 trade`` — a message read daily should not say "1 trades"."""
    word = singular if abs(count) == 1 else (plural_form or f"{singular}s")
    return f"{count:,} {word}"


def _today_label(when: object = None) -> str:
    ts = pd.Timestamp(when) if when is not None else pd.Timestamp.now()
    return ts.strftime("%d %b %Y")


def _joined(parts: list[str]) -> str:
    return " · ".join(p for p in parts if p)


def _span(values: list, fmt) -> str:
    """``a`` or ``a–b`` from the smallest and largest of ``values``."""
    present = [v for v in values if v is not None]
    if not present:
        return ""
    lo, hi = fmt(min(present)), fmt(max(present))
    return lo if lo == hi else f"{lo}–{hi}"


def _date(ts: pd.Timestamp) -> str:
    return ts.strftime("%d %b %Y")


def _folded_amount(rows: list[Event]) -> str:
    """Total of the disclosed buckets; a floor with "+" if any row lacks a ceiling."""
    low = sum(e.low for e in rows)
    if all(e.high > e.low for e in rows):
        return disclosed_range(low, sum(e.high for e in rows))
    return disclosed_range(low, None)


def _trade_line(rows: list[Event], links: DashboardLinks) -> str:
    """One line per action on one asset; repeats on the same filing fold in."""
    first = rows[0]
    emoji = _DIRECTION_EMOJI.get(first.direction, "▫️")
    asset = anchor(links.ticker(first.ticker), first.asset) if first.ticker else escape(first.asset)
    count = f" ×{len(rows)}" if len(rows) > 1 else ""
    amount = first.amount if len(rows) == 1 else _folded_amount(rows)
    traded = _span([e.traded_on for e in rows], _date)
    late = _span([e.late_days for e in rows], str)
    if late:
        late_rows = sum(1 for e in rows if e.late_days is not None)
        share = f"{late_rows} of {len(rows)} " if late_rows < len(rows) else ""
        verb = "" if first.kind == KIND_LATE and not share else "filed "
        late = f"{share}{verb}{late} days late"
    # Keep only details every folded row shares: a tag true of one row is not
    # true of the line.
    details = [d for d in first.details if all(d in e.details for e in rows)]
    parts = [
        f"{emoji} {escape(first.action)} {asset}{count}",
        escape(amount),
        escape(f"traded {traded}") if traded else "",
        *map(escape, details),
        escape(late),
    ]
    return "  " + _joined(parts)


def _render_filing(group: list[Event], links: DashboardLinks) -> list[str]:
    """One member heading, then each trade from that filing."""
    first = group[0]
    name = anchor(links.member(first.member), first.member_label)
    # Senate rows carry no URL on purpose: efdsearch opens a filing only after
    # the visitor accepts its terms, so a deep link lands on its home page.
    # The member link above is their way into the detail.
    pdf = anchor(first.url, "PDF") if first.url else ""
    out = [f"• {_joined([f'<b>{name}</b>', escape(f'filed {first.filed}'), pdf])}"]

    lines: dict[tuple[str, str], list[Event]] = {}
    for event in group:
        lines.setdefault((event.action, event.asset), []).append(event)
    out.extend(_trade_line(rows, links) for rows in list(lines.values())[:_TRADES_PER_FILING])
    hidden = len(lines) - _TRADES_PER_FILING
    if hidden > 0:
        out.append(escape(f"  … {plural(hidden, 'more line')} on this filing"))
    return out


def _render_cluster(event: Event, links: DashboardLinks) -> list[str]:
    emoji = _DIRECTION_EMOJI.get(event.direction, "")
    ticker = anchor(links.ticker(event.ticker), event.ticker)
    out = [f"• {emoji} <b>{escape(event.action)} {ticker}</b> — {escape(plural(int(event.sort_value), 'member'))}"]
    out.extend(f"  {escape(d)}" for d in event.details)
    names = [anchor(links.member(n), display_name(n)) for n in event.members[:_CLUSTER_NAMES]]
    extra = len(event.members) - _CLUSTER_NAMES
    if extra > 0:
        names.append(escape(f"+{extra}"))
    if names:
        out.append("  " + ", ".join(names))
    return out


def _render_plain(event: Event) -> list[str]:
    """Events built without structured parts: title, lines, optional link."""
    out = [f"• <b>{escape(event.title)}</b>"]
    out.extend(f"  {escape(line)}" for line in event.lines if line and str(line).strip())
    if event.url:
        out.append(f"  {anchor(event.url, 'disclosure')}")
    return out


def _entries(events: list[Event]) -> list[list[Event]]:
    """Group a kind's events by filing, strongest group first."""
    groups: dict[str, list[Event]] = {}
    for event in events:
        key = event.group_key or f"solo:{id(event)}"
        groups.setdefault(key, []).append(event)
    for group in groups.values():
        group.sort(key=lambda e: e.sort_value, reverse=True)
    return sorted(groups.values(), key=lambda g: g[0].sort_value, reverse=True)


def _render_entry(group: list[Event], links: DashboardLinks) -> list[str]:
    first = group[0]
    if first.kind == KIND_CLUSTER:
        return _render_cluster(first, links)
    if first.member_label:
        return _render_filing(group, links)
    return _render_plain(first)


def render_event_message(
    events: list[Event],
    *,
    new_row_count: int,
    when: object = None,
    max_events: int = 12,
    flood_threshold: int = 250,
    links: DashboardLinks | None = None,
) -> str:
    """One message for a whole run. Empty string when there is nothing to say.

    ``max_events`` caps the headings (filings and clusters), not the rows.
    """
    if not events:
        return ""
    links = links or DashboardLinks()

    summary = escape(
        f"{plural(new_row_count, 'new disclosure row')} · {len(events)} notable"
    )
    header = [
        f"🏛 <b>Congress trades — {escape(_today_label(when))}</b>",
        _joined([summary, anchor(links.home(), "dashboard") if links.home() else ""]),
    ]
    if new_row_count >= flood_threshold:
        header.append(
            escape("Bulk filing batch — only the most notable are listed.")
        )

    body: list[str] = []
    shown = 0
    omitted = 0
    for kind in KIND_ORDER:
        entries = _entries([e for e in events if e.kind == kind])
        if not entries:
            continue
        cap = min(KIND_CAPS.get(kind, max_events), max(0, max_events - shown))
        visible = entries[:cap]
        if not visible:
            omitted += sum(len(g) for g in entries)
            continue
        emoji = _KIND_EMOJI.get(kind, "•")
        body.append("")
        body.append(f"{emoji} <b>{escape(KIND_LABELS.get(kind, kind))}</b>")
        for group in visible:
            body.extend(_render_entry(group, links))
        hidden = sum(len(g) for g in entries[cap:])
        if hidden > 0:
            body.append(escape(f"  … and {hidden} more"))
            omitted += hidden
        shown += len(visible)

    if omitted:
        body.append("")
        more = escape(f"{plural(omitted, 'further event')} not listed.")
        body.append(_joined([more, anchor(links.raw(), "Full list") if links.raw() else ""]))

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
