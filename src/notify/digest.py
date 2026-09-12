"""The weekly roundup.

Event alerts answer "did something notable just happen". The digest answers
the two questions alerts structurally cannot: *what was the shape of the week*
and *is the pipeline still alive*.

That second half matters more than it looks. A tracker that silently stops
ingesting looks exactly like a quiet week — no alerts either way. The digest
carries a staleness line so a dead pipeline is visible within seven days
instead of whenever someone happens to open the dashboard.

Amounts are always shown as the disclosed range (low–high), never a single
number: Congress discloses buckets, and collapsing them to a midpoint invents
precision the filing does not contain.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

import pandas as pd

from ..api._format import sum_amount_high, sum_amount_low
from .events import KIND_LARGE, KIND_LATE, KIND_OPTION, Event, member_label, prepare_frame
from .format import plural
from .links import DashboardLinks, anchor
from .money import compact_usd
from .telegram import escape

_TOP_N = 5


class MemberRow(NamedTuple):
    name: str  # stored name: the dashboard's member key
    trades: int
    low: float
    high: float
    label: str  # "Rep. Jane Doe (D-CA)"


@dataclass(frozen=True)
class DigestStats:
    rows: int = 0
    members: int = 0
    tickers: int = 0
    buys: int = 0
    sells: int = 0
    buy_low: float = 0.0
    buy_high: float = 0.0
    sell_low: float = 0.0
    sell_high: float = 0.0
    top_members: tuple[MemberRow, ...] = ()
    top_tickers: tuple[tuple[str, int, int, float, float], ...] = ()
    option_events: int = 0
    large_events: int = 0
    late_events: int = 0
    total_rows: int = 0
    stale_days: int | None = None
    window_days: int = 7
    notes: tuple[str, ...] = field(default_factory=tuple)


def _group_size(frame: pd.DataFrame, key: str) -> pd.Series:
    return frame.groupby(key, observed=True).size()


def _group_sum(frame: pd.DataFrame, key: str, column: str) -> pd.Series:
    values = pd.to_numeric(frame[column], errors="coerce")
    return values.groupby(frame[key], observed=True).sum(min_count=0)


def _range_text(low: float, high: float) -> str:
    lo, hi = compact_usd(low), compact_usd(high)
    if not lo and not hi:
        return "—"
    if not lo or not hi or lo == hi:
        return lo or hi
    return f"{lo}–{hi}"


def compute_digest_stats(
    frame: pd.DataFrame,
    *,
    events: list[Event] | None = None,
    total_rows: int = 0,
    stale_days: int | None = None,
    window_days: int = 7,
) -> DigestStats:
    """Summarize one week of newly ingested rows. Pure; no I/O."""
    events = events or []
    counts = {
        "option_events": sum(1 for e in events if e.kind == KIND_OPTION),
        "large_events": sum(1 for e in events if e.kind == KIND_LARGE),
        "late_events": sum(1 for e in events if e.kind == KIND_LATE),
    }
    prepared = prepare_frame(frame)
    if prepared.empty:
        return DigestStats(
            total_rows=total_rows,
            stale_days=stale_days,
            window_days=window_days,
            **counts,
        )

    buys = prepared[prepared["is_buy"]]
    sells = prepared[prepared["is_sell"]]

    by_member = (
        pd.DataFrame(
            {
                "trades": _group_size(prepared, "member"),
                "low": _group_sum(prepared, "member", "amount_low"),
                "high": _group_sum(prepared, "member", "amount_high"),
            }
        )
        .sort_values(["low", "trades"], ascending=[False, False])
        .head(_TOP_N)
    )
    labels = {
        str(row["member"]): member_label(row)
        for _, row in prepared.drop_duplicates("member").iterrows()
    }
    top_members = tuple(
        MemberRow(
            name=str(name),
            trades=int(row["trades"]),
            low=float(row["low"]),
            high=float(row["high"]),
            label=labels.get(str(name), str(name)),
        )
        for name, row in by_member.iterrows()
    )

    with_ticker = prepared[prepared["ticker"].astype(str).str.strip() != ""]
    if with_ticker.empty:
        top_tickers: tuple = ()
    else:
        by_ticker = (
            pd.DataFrame(
                {
                    "trades": _group_size(with_ticker, "ticker"),
                    "members": with_ticker.groupby("ticker", observed=True)[
                        "member"
                    ].nunique(),
                    "low": _group_sum(with_ticker, "ticker", "amount_low"),
                    "high": _group_sum(with_ticker, "ticker", "amount_high"),
                }
            )
            .sort_values(["members", "trades", "low"], ascending=[False, False, False])
            .head(_TOP_N)
        )
        top_tickers = tuple(
            (
                str(name),
                int(row["trades"]),
                int(row["members"]),
                float(row["low"]),
                float(row["high"]),
            )
            for name, row in by_ticker.iterrows()
        )

    return DigestStats(
        rows=int(len(prepared)),
        members=int(prepared["member"].nunique()),
        tickers=int(with_ticker["ticker"].nunique()) if not with_ticker.empty else 0,
        buys=int(len(buys)),
        sells=int(len(sells)),
        buy_low=sum_amount_low(buys),
        buy_high=sum_amount_high(buys),
        sell_low=sum_amount_low(sells),
        sell_high=sum_amount_high(sells),
        top_members=top_members,
        top_tickers=top_tickers,
        total_rows=total_rows,
        stale_days=stale_days,
        window_days=window_days,
        **counts,
    )


def render_digest(
    stats: DigestStats,
    *,
    when: object = None,
    stale_threshold_days: int = 10,
    links: DashboardLinks | None = None,
) -> str:
    links = links or DashboardLinks()
    ts = pd.Timestamp(when) if when is not None else pd.Timestamp.now()
    lines = [
        f"📋 <b>Congress trades — week to {escape(ts.strftime('%d %b %Y'))}</b>",
    ]
    if links.home():
        lines.append(anchor(links.home(), "Open the dashboard"))

    if stats.rows == 0:
        lines.append(
            escape(
                f"No new disclosures ingested in the last {stats.window_days} days."
            )
        )
    else:
        lines.append(
            escape(
                f"{plural(stats.rows, 'new row')} · "
                f"{plural(stats.members, 'member')} · "
                f"{plural(stats.tickers, 'ticker')}"
            )
        )
        lines.append("")
        lines.append(
            escape(
                f"Buys: {stats.buys} ({_range_text(stats.buy_low, stats.buy_high)})"
            )
        )
        lines.append(
            escape(
                f"Sells: {stats.sells} ({_range_text(stats.sell_low, stats.sell_high)})"
            )
        )

        if stats.top_members:
            lines.append("")
            lines.append("👤 <b>Most active members</b>")
            for member in stats.top_members:
                name = anchor(links.member(member.name), member.label or member.name)
                lines.append(
                    f"• {name} — "
                    + escape(
                        f"{plural(member.trades, 'trade')}, "
                        f"{_range_text(member.low, member.high)}"
                    )
                )

        if stats.top_tickers:
            lines.append("")
            lines.append("📈 <b>Most traded tickers</b>")
            for ticker, trades, members, low, high in stats.top_tickers:
                lines.append(
                    f"• {anchor(links.ticker(ticker), ticker)} — "
                    + escape(
                        f"{plural(trades, 'trade')} by "
                        f"{plural(members, 'member')}, {_range_text(low, high)}"
                    )
                )

        notable = stats.option_events + stats.large_events + stats.late_events
        if notable:
            lines.append("")
            lines.append("🔔 <b>Alerted this week</b>")
            lines.append(
                escape(
                    f"{stats.large_events} large · {stats.option_events} options · "
                    f"{stats.late_events} filed late"
                )
            )

    lines.append("")
    lines.append("🩺 <b>Pipeline</b>")
    lines.append(escape(f"{stats.total_rows:,} transactions stored in total."))
    if stats.stale_days is None:
        lines.append(escape("No ingest timestamp found — has the pipeline ever run?"))
    elif stats.stale_days >= stale_threshold_days:
        lines.append(
            escape(
                f"⚠️ No new row for {stats.stale_days} days. The nightly ingest may "
                "be failing — check /var/log/f9-congress-trading/ingest.log."
            )
        )
    else:
        lines.append(
            escape(f"Last new row {plural(stats.stale_days, 'day')} ago.")
        )

    for note in stats.notes:
        lines.append(escape(note))
    return "\n".join(lines)
