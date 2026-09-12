"""What counts as worth a message.

This module is the notification *policy*, kept as pure functions over a
prepared transactions frame so every rule is testable without a database or a
network call.

The guiding rule: **silence has to mean something.** A channel that fires on
every disclosure gets muted within a week, and then a genuinely interesting
trade arrives into a muted channel. So only four kinds of row escalate to an
instant message, in descending order of how rarely they occur:

1. ``option_trade`` — a member buying or selling options. Rare, leveraged and
   directional; the strongest single-row signal in the dataset.
2. ``large_trade`` — a listed stock or ETF whose disclosed *floor* clears the
   large-trade threshold. Using the floor keeps it conservative: Congress
   discloses ranges, and a "$100,001 - $250,000" bucket is at least $100k.
   Treasuries, municipal bonds, corporate notes and mutual funds are left out:
   they clear any dollar bar easily and say nothing about a view on a company.
3. ``cluster`` — several members trading the same ticker inside one window.
   Delegated to the dashboard's own ``detect_coordinated_trades`` so an alert
   and the Patterns page can never disagree.
4. ``late_filing`` — filed past the STOCK Act's 45-day deadline. A compliance
   signal rather than a trading one, so it is reported regardless of size but
   capped hard when a batch of them lands at once.

Everything else — a member's first buy of a name, the sector, the lateness of
a trade already being reported — rides along as a tag on one of the above
rather than firing on its own.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable

import pandas as pd

from ..api._patterns_analytics import (
    add_trade_categories,
    detect_coordinated_trades,
    looks_like_debt_security,
    normalize_party,
)
from ..utils import is_non_equity_asset
from .money import disclosed_range

KIND_OPTION = "option_trade"
KIND_LARGE = "large_trade"
KIND_CLUSTER = "cluster"
KIND_LATE = "late_filing"

# Display order and per-kind caps. The caps stop one noisy kind from eating the
# whole message: a filing deadline can land dozens of late disclosures at once.
KIND_ORDER: tuple[str, ...] = (KIND_OPTION, KIND_LARGE, KIND_CLUSTER, KIND_LATE)
KIND_LABELS: dict[str, str] = {
    KIND_OPTION: "Options activity",
    KIND_LARGE: "Large trades",
    KIND_CLUSTER: "Multiple members, same ticker",
    KIND_LATE: "Filed late (STOCK Act)",
}
KIND_CAPS: dict[str, int] = {
    KIND_OPTION: 6,
    KIND_LARGE: 8,
    KIND_CLUSTER: 4,
    KIND_LATE: 3,
}

# Kinds that justify a notification sound. A message carrying only late filings
# is still delivered, silently: worth reading, not worth interrupting for.
URGENT_KINDS: frozenset[str] = frozenset({KIND_OPTION, KIND_LARGE, KIND_CLUSTER})

_CHAMBER_PREFIX = {"house": "Rep.", "senate": "Sen."}

# House filings store the name with an "Hon." title already attached, which
# would otherwise render as "Rep. Hon. Tim Moore".
_LEADING_TITLE = re.compile(r"^(?:Hon|Honorable|Rep|Sen)\.?\s+", re.IGNORECASE)

# Trailing owner/asset codes from the PTR form ("[GS]", "[ST]") — noise in a chat.
_FORM_CODE = re.compile(r"\s*\[[A-Z]{2}\]\s*$")
_ASSET_LABEL_MAX = 48

# Types that are never a stock pick, whatever the dollar amount.
_NON_LISTED_TYPES = frozenset({"bond", "mutual_fund", "annuity"})
# Five-letter symbols ending in X are mutual and money-market funds (VFIAX, SWVXX).
_FUND_TICKER = re.compile(r"^[A-Z]{4}X$")


@dataclass(frozen=True)
class Event:
    kind: str
    # Plain-text summary: logs, tests, and the fallback rendering.
    title: str
    lines: tuple[str, ...] = ()
    url: str = ""
    dedupe_key: str = ""
    # Ranking within a kind; larger sorts first (dollars, days late, members).
    sort_value: float = 0.0
    # Structured parts, so the renderer can link names and tickers and fold
    # several rows from one filing under a single member heading.
    member: str = ""  # stored name: the dashboard's member key
    member_label: str = ""  # "Rep. Jane Doe (D-CA)"
    ticker: str = ""
    action: str = ""  # "Sell (partial)", "Buy call", "Coordinated buy"
    asset: str = ""  # ticker, else a shortened asset name
    amount: str = ""  # "$100K–$250K"
    low: float = 0.0  # disclosed bucket, for totals when rows are folded
    high: float = 0.0
    traded_on: pd.Timestamp | None = None
    late_days: int | None = None  # past the STOCK Act deadline
    details: tuple[str, ...] = ()  # sector, tags
    filed: str = ""
    group_key: str = ""  # member + filing
    direction: str = ""  # "buy" | "sell" | ""
    members: tuple[str, ...] = ()  # clusters: stored names of the members


# --------------------------------------------------------------------------- #
# Row helpers
# --------------------------------------------------------------------------- #
def _text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _amount_floor(row: pd.Series) -> float:
    value = pd.to_numeric(row.get("amount_low"), errors="coerce")
    if pd.isna(value):
        return 0.0
    return float(value)


def _date_text(value: object) -> str:
    if value is None or pd.isna(value):
        return "?"
    try:
        return pd.Timestamp(value).strftime("%d %b %Y")
    except (ValueError, TypeError):
        return "?"


def display_name(name: object) -> str:
    """Stored member name without the "Hon." the House forms prepend."""
    return _LEADING_TITLE.sub("", _text(name))


def member_label(row: pd.Series) -> str:
    """``Rep. Nancy Pelosi (D-CA)`` — chamber, party and state in one token."""
    name = display_name(row.get("member")) or "Unknown member"
    chamber = _text(row.get("chamber")).lower()
    prefix = _CHAMBER_PREFIX.get(chamber, "")
    party = normalize_party(row.get("party"))
    party_initial = party[0] if party and party != "Unknown" else ""
    state = _text(row.get("state"))
    if party_initial and state:
        suffix = f" ({party_initial}-{state})"
    elif party_initial:
        suffix = f" ({party_initial})"
    elif state:
        suffix = f" ({state})"
    else:
        suffix = ""
    return f"{prefix} {name}{suffix}".strip()


def asset_label(row: pd.Series) -> str:
    """Ticker when resolved, else the issuer or a shortened asset name."""
    ticker = _text(row.get("ticker")).upper()
    if ticker:
        return ticker
    name = (
        _text(row.get("issuer_name"))
        or _text(row.get("asset_name_normalized"))
        or _text(row.get("asset_name_raw"))
    )
    name = _FORM_CODE.sub("", name)
    if len(name) > _ASSET_LABEL_MAX:
        name = name[: _ASSET_LABEL_MAX - 1].rstrip() + "…"
    return name or "unknown asset"


def is_listed_security(row: pd.Series) -> bool:
    """A stock or ETF with a resolved ticker — the trades that express a view.

    Debt and fund rows often carry the issuer's equity ticker (a JPMorgan note
    is tagged JPM), so the name is checked as well as the ticker.
    """
    ticker = _text(row.get("ticker")).upper()
    if not ticker or " " in ticker or _FUND_TICKER.match(ticker):
        return False
    if _text(row.get("asset_type")).lower() in _NON_LISTED_TYPES:
        return False
    name = _text(row.get("asset_name_raw"))
    return not (is_non_equity_asset(ticker, name) or looks_like_debt_security(name))


def _action_label(row: pd.Series) -> str:
    label = _text(row.get("transaction_type_label"))
    if label and label.lower() != "unknown":
        return label
    if bool(row.get("is_buy")):
        return "Buy"
    if bool(row.get("is_sell")):
        return "Sell"
    return _text(row.get("transaction_type")) or "Trade"


def _direction(row: pd.Series) -> str:
    if bool(row.get("is_buy")):
        return "buy"
    if bool(row.get("is_sell")):
        return "sell"
    return ""


def _filing_delay_days(row: pd.Series) -> float | None:
    filed = row.get("filing_date")
    traded = row.get("transaction_date")
    if filed is None or traded is None or pd.isna(filed) or pd.isna(traded):
        return None
    try:
        return float((pd.Timestamp(filed) - pd.Timestamp(traded)).days)
    except (ValueError, TypeError):
        return None


def days_past_deadline(row: pd.Series, deadline_days: int) -> int | None:
    """Days beyond the deadline, or None when on time or undatable.

    A trade filed 90 days after it happened is 45 days late, not 90: the
    deadline itself is subtracted.
    """
    delay = _filing_delay_days(row)
    if delay is None or delay <= deadline_days:
        return None
    return int(delay - deadline_days)


def _late_or_none(row: pd.Series, deadline_days: int | None) -> int | None:
    return None if deadline_days is None else days_past_deadline(row, deadline_days)


def _sector(row: pd.Series) -> str:
    # "Unknown" is a real stored value, not a blank — printing it adds a word
    # and no information.
    sector = _text(row.get("sector"))
    return "" if sector.lower() in {"", "unknown", "n/a", "none"} else sector


def _timestamp(value: object) -> pd.Timestamp | None:
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        return None
    return None if pd.isna(ts) else ts


def _row_event(
    row: pd.Series,
    *,
    kind: str,
    action: str,
    sort_value: float,
    title_prefix: str = "",
    tags: Iterable[str] = (),
    late_days: int | None = None,
) -> Event:
    asset = asset_label(row)
    low = pd.to_numeric(row.get("amount_low"), errors="coerce")
    high = pd.to_numeric(row.get("amount_high"), errors="coerce")
    amount = disclosed_range(low, high)
    traded = f"traded {_date_text(row.get('transaction_date'))}"
    filed = _date_text(row.get("filing_date"))
    tags = tuple(t for t in tags if t)
    label = member_label(row)
    head = title_prefix or action
    late = f"filed {late_days} days late" if late_days is not None else ""
    return Event(
        kind=kind,
        title=f"{head} · {asset} — {label}",
        lines=(
            " · ".join(
                p for p in (amount, traded, f"filed {filed}", _sector(row), *tags, late) if p
            ),
        ),
        url=_text(row.get("disclosure_url")),
        dedupe_key=_row_dedupe_key(row),
        sort_value=sort_value,
        member=_text(row.get("member")),
        member_label=label,
        ticker=_text(row.get("ticker")).upper(),
        action=action,
        asset=asset,
        amount=amount,
        low=0.0 if pd.isna(low) else float(low),
        high=0.0 if pd.isna(high) else float(high),
        traded_on=_timestamp(row.get("transaction_date")),
        late_days=late_days,
        details=tuple(p for p in (_sector(row), *tags) if p),
        filed=filed,
        group_key=f"{_text(row.get('member'))}|{_text(row.get('doc_id')) or filed}",
        direction=_direction(row),
    )


def _row_dedupe_key(row: pd.Series) -> str:
    return f"tx:{_text(row.get('source_hash'))}:{_text(row.get('doc_id'))}"


# --------------------------------------------------------------------------- #
# Detectors
# --------------------------------------------------------------------------- #
def prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Add the buy/sell/option categories the detectors rely on."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    return add_trade_categories(frame)


def recent_filings(
    frame: pd.DataFrame, *, max_age_days: int, today: object = None
) -> pd.DataFrame:
    """Rows filed within ``max_age_days`` of ``today``; all rows when 0 or less.

    New to the database is not new to the public. A backfill — the first Senate
    download pulls every PTR since 2023 — lands thousands of rows above the
    high-water mark in one night, and each would otherwise be announced as
    today's news. A row with no parsable filing date is kept: dropping it would
    let a parser bug silence real alerts.
    """
    if frame is None:
        return pd.DataFrame()
    if frame.empty or max_age_days <= 0 or "filing_date" not in frame.columns:
        return frame
    now = pd.Timestamp(today) if today is not None else pd.Timestamp.now()
    if now.tzinfo is not None:
        now = now.tz_localize(None)
    cutoff = now.normalize() - pd.Timedelta(days=int(max_age_days))
    filed = pd.to_datetime(frame["filing_date"], errors="coerce")
    return frame[filed.isna() | (filed >= cutoff)]


def detect_option_trades(
    frame: pd.DataFrame,
    *,
    min_amount: float,
    tagger: Callable[[pd.Series], list[str]] | None = None,
    late_after_days: int | None = None,
) -> tuple[list[Event], set]:
    """Options trades at or above ``min_amount``. Returns (events, row index).

    ``late_after_days`` notes lateness on the trade itself, so a big trade
    filed late is one entry rather than two.
    """
    if frame is None or frame.empty:
        return [], set()
    is_option = frame["option_side"].isin(["Call", "Put", "Option"])
    candidates = frame[is_option]
    events: list[Event] = []
    claimed: set = set()
    for idx, row in candidates.iterrows():
        floor = _amount_floor(row)
        if floor < min_amount:
            continue
        side = _text(row.get("option_side")).lower()
        events.append(
            _row_event(
                row,
                kind=KIND_OPTION,
                action=f"{_action_label(row)} {side}",
                sort_value=floor,
                tags=tagger(row) if tagger else (),
                late_days=_late_or_none(row, late_after_days),
            )
        )
        claimed.add(idx)
    return events, claimed


def detect_large_trades(
    frame: pd.DataFrame,
    *,
    min_amount: float,
    skip: set | None = None,
    tagger: Callable[[pd.Series], list[str]] | None = None,
    late_after_days: int | None = None,
) -> tuple[list[Event], set]:
    """Listed stock/ETF trades whose disclosed floor clears ``min_amount``."""
    if frame is None or frame.empty:
        return [], set()
    skip = skip or set()
    events: list[Event] = []
    claimed: set = set()
    for idx, row in frame.iterrows():
        if idx in skip:
            continue
        floor = _amount_floor(row)
        if floor < min_amount or not is_listed_security(row):
            continue
        events.append(
            _row_event(
                row,
                kind=KIND_LARGE,
                action=_action_label(row),
                sort_value=floor,
                tags=tagger(row) if tagger else (),
                late_days=_late_or_none(row, late_after_days),
            )
        )
        claimed.add(idx)
    return events, claimed


def detect_late_filings(
    frame: pd.DataFrame, *, min_days: int, skip: set | None = None
) -> tuple[list[Event], set]:
    """Disclosures filed more than ``min_days`` after the trade."""
    if frame is None or frame.empty:
        return [], set()
    skip = skip or set()
    events: list[Event] = []
    claimed: set = set()
    for idx, row in frame.iterrows():
        if idx in skip:
            continue
        late = days_past_deadline(row, min_days)
        if late is None:
            continue
        events.append(
            _row_event(
                row,
                kind=KIND_LATE,
                action=_action_label(row),
                sort_value=float(late),
                title_prefix=f"{late} days late",
                late_days=late,
            )
        )
        claimed.add(idx)
    return events, claimed


def detect_clusters(
    context_frame: pd.DataFrame,
    *,
    new_tickers: Iterable[str],
    min_members: int,
    window_days: int,
    is_new: Callable[[str, int], bool] | None = None,
) -> list[Event]:
    """Coordinated buying/selling that involves at least one newly ingested row.

    ``context_frame`` is the whole history (the same frame the dashboard uses),
    because a cluster is only visible against it. Restricting to ``new_tickers``
    is what keeps this from re-announcing the same cluster every night, and
    ``is_new`` lets the caller suppress a cluster whose member count has not
    grown since it was last reported.
    """
    if context_frame is None or context_frame.empty:
        return []
    wanted = {str(t).strip().upper() for t in new_tickers if str(t).strip()}
    if not wanted:
        return []
    clusters = detect_coordinated_trades(
        context_frame, window_days=window_days, min_members=min_members
    )
    if clusters is None or clusters.empty:
        return []

    events: list[Event] = []
    for _, row in clusters.iterrows():
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker not in wanted:
            continue
        members = int(row.get("members") or 0)
        pattern = str(row.get("pattern") or "")
        key = f"cluster:{ticker}:{pattern}"
        if is_new is not None and not is_new(key, members):
            continue
        names = tuple(n.strip() for n in str(row.get("member_names") or "").split(",") if n.strip())
        window = (
            f"{int(row.get('trades') or 0)} trades between "
            f"{_date_text(row.get('date_from'))} and {_date_text(row.get('date_to'))}"
        )
        events.append(
            Event(
                kind=KIND_CLUSTER,
                title=f"{pattern} · {ticker} — {members} members",
                lines=(window, ", ".join(display_name(n) for n in names)),
                dedupe_key=key,
                sort_value=float(members),
                ticker=ticker,
                action=pattern,
                asset=ticker,
                details=(window,),
                direction="sell" if "sell" in pattern.lower() else "buy",
                members=names,
            )
        )
    return events


def collect_events(
    new_rows: pd.DataFrame,
    *,
    context_frame: pd.DataFrame | None,
    large_trade_usd: float,
    option_trade_usd: float,
    late_filing_days: int,
    cluster_min_members: int,
    cluster_window_days: int,
    cluster_is_new: Callable[[str, int], bool] | None = None,
    tagger: Callable[[pd.Series], list[str]] | None = None,
) -> list[Event]:
    """Run every detector over the newly ingested rows.

    A row is claimed by the most specific detector that matches it, so an
    options trade above the large-trade threshold is reported once, as options
    activity, rather than twice.
    """
    prepared = prepare_frame(new_rows)
    events: list[Event] = []
    claimed: set = set()

    # Lateness rides along on a trade that is already being reported, so the
    # late-filing detector below is left to catch only the small tail.
    if not prepared.empty:
        option_events, option_rows = detect_option_trades(
            prepared,
            min_amount=option_trade_usd,
            tagger=tagger,
            late_after_days=late_filing_days,
        )
        events.extend(option_events)
        claimed |= option_rows

        large_events, large_rows = detect_large_trades(
            prepared,
            min_amount=large_trade_usd,
            skip=claimed,
            tagger=tagger,
            late_after_days=late_filing_days,
        )
        events.extend(large_events)
        claimed |= large_rows

        late_events, _ = detect_late_filings(
            prepared, min_days=late_filing_days, skip=claimed
        )
        events.extend(late_events)

    if context_frame is not None and not prepared.empty:
        tickers = prepared["ticker"].dropna().astype(str).unique().tolist()
        events.extend(
            detect_clusters(
                context_frame,
                new_tickers=tickers,
                min_members=cluster_min_members,
                window_days=cluster_window_days,
                is_new=cluster_is_new,
            )
        )
    return events


def is_urgent(events: Iterable[Event]) -> bool:
    """True when the message deserves a notification sound."""
    return any(e.kind in URGENT_KINDS for e in events)
