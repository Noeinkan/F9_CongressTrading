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
2. ``large_trade`` — the disclosed *floor* clears the large-trade threshold.
   Using the floor keeps it conservative: Congress discloses ranges, and a
   "$50,001 - $100,000" bucket is at least $50k.
3. ``cluster`` — several members trading the same ticker inside one window.
   Delegated to the dashboard's own ``detect_coordinated_trades`` so an alert
   and the Patterns page can never disagree.
4. ``late_filing`` — filed past the STOCK Act's 45-day deadline. A compliance
   signal rather than a trading one, so it is reported regardless of size but
   capped hard when a batch of them lands at once.

Everything else — a member's first position in a name, the sector, the option
side — rides along as a tag on one of the above rather than firing on its own.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable

import pandas as pd

from ..api._format import format_disclosed_range
from ..api._patterns_analytics import (
    add_trade_categories,
    detect_coordinated_trades,
    normalize_party,
)

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

_CHAMBER_PREFIX = {"house": "Rep.", "senate": "Sen."}

# House filings store the name with an "Hon." title already attached, which
# would otherwise render as "Rep. Hon. Tim Moore".
_LEADING_TITLE = re.compile(r"^(?:Hon|Honorable|Rep|Sen)\.?\s+", re.IGNORECASE)


@dataclass(frozen=True)
class Event:
    kind: str
    title: str
    lines: tuple[str, ...] = ()
    url: str = ""
    dedupe_key: str = ""
    # Ranking within a kind; larger sorts first (dollars, or member count).
    sort_value: float = 0.0


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


def member_label(row: pd.Series) -> str:
    """``Rep. Nancy Pelosi (D-CA)`` — chamber, party and state in one token."""
    name = _LEADING_TITLE.sub("", _text(row.get("member"))) or "Unknown member"
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
    """Ticker when resolved, else the issuer or the raw asset name."""
    ticker = _text(row.get("ticker")).upper()
    if ticker:
        return ticker
    issuer = _text(row.get("issuer_name"))
    if issuer:
        return issuer
    raw = _text(row.get("asset_name_normalized")) or _text(row.get("asset_name_raw"))
    return raw[:60] or "unknown asset"


def _action_label(row: pd.Series) -> str:
    label = _text(row.get("transaction_type_label"))
    if label and label.lower() != "unknown":
        return label
    if bool(row.get("is_buy")):
        return "Buy"
    if bool(row.get("is_sell")):
        return "Sell"
    return _text(row.get("transaction_type")) or "Trade"


def _filing_delay_days(row: pd.Series) -> float | None:
    filed = row.get("filing_date")
    traded = row.get("transaction_date")
    if filed is None or traded is None or pd.isna(filed) or pd.isna(traded):
        return None
    try:
        return float((pd.Timestamp(filed) - pd.Timestamp(traded)).days)
    except (ValueError, TypeError):
        return None


def _detail_line(row: pd.Series, *, tags: Iterable[str] = ()) -> str:
    parts = [
        format_disclosed_range(row.get("amount_low"), row.get("amount_high")),
        f"traded {_date_text(row.get('transaction_date'))}",
        f"filed {_date_text(row.get('filing_date'))}",
    ]
    # "Unknown" is a real stored value, not a blank — printing it adds a word
    # and no information.
    sector = _text(row.get("sector"))
    if sector and sector.lower() not in {"unknown", "n/a", "none"}:
        parts.append(sector)
    parts.extend(t for t in tags if t)
    return " · ".join(p for p in parts if p and p != "—")


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


def detect_option_trades(
    frame: pd.DataFrame,
    *,
    min_amount: float,
    tagger: Callable[[pd.Series], list[str]] | None = None,
) -> tuple[list[Event], set]:
    """Options trades at or above ``min_amount``. Returns (events, row index)."""
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
        side = _text(row.get("option_side"))
        tags = list(tagger(row)) if tagger else []
        events.append(
            Event(
                kind=KIND_OPTION,
                title=f"{_action_label(row)} {side.lower()} · {asset_label(row)} — {member_label(row)}",
                lines=(_detail_line(row, tags=tags),),
                url=_text(row.get("disclosure_url")),
                dedupe_key=_row_dedupe_key(row),
                sort_value=floor,
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
) -> tuple[list[Event], set]:
    """Trades whose disclosed floor clears ``min_amount``."""
    if frame is None or frame.empty:
        return [], set()
    skip = skip or set()
    events: list[Event] = []
    claimed: set = set()
    for idx, row in frame.iterrows():
        if idx in skip:
            continue
        floor = _amount_floor(row)
        if floor < min_amount:
            continue
        tags = list(tagger(row)) if tagger else []
        events.append(
            Event(
                kind=KIND_LARGE,
                title=f"{_action_label(row)} · {asset_label(row)} — {member_label(row)}",
                lines=(_detail_line(row, tags=tags),),
                url=_text(row.get("disclosure_url")),
                dedupe_key=_row_dedupe_key(row),
                sort_value=floor,
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
        delay = _filing_delay_days(row)
        if delay is None or delay <= min_days:
            continue
        events.append(
            Event(
                kind=KIND_LATE,
                title=f"{int(delay)} days late · {asset_label(row)} — {member_label(row)}",
                lines=(_detail_line(row),),
                url=_text(row.get("disclosure_url")),
                dedupe_key=_row_dedupe_key(row),
                sort_value=float(delay),
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
        key = f"cluster:{ticker}:{row.get('pattern')}"
        if is_new is not None and not is_new(key, members):
            continue
        names = str(row.get("member_names") or "")
        events.append(
            Event(
                kind=KIND_CLUSTER,
                title=f"{row.get('pattern')} · {ticker} — {members} members",
                lines=(
                    f"{int(row.get('trades') or 0)} trades between "
                    f"{_date_text(row.get('date_from'))} and {_date_text(row.get('date_to'))}",
                    names,
                ),
                dedupe_key=key,
                sort_value=float(members),
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

    def _tags_for(row: pd.Series) -> list[str]:
        # Lateness rides along as a tag on the trade that is already being
        # reported, so a big trade filed late is one message, not two — and the
        # late-filing detector below is left to catch only the small tail.
        tags = list(tagger(row)) if tagger else []
        delay = _filing_delay_days(row)
        if delay is not None and delay > late_filing_days:
            tags.append(f"filed {int(delay)}d late")
        return tags

    if not prepared.empty:
        option_events, option_rows = detect_option_trades(
            prepared, min_amount=option_trade_usd, tagger=_tags_for
        )
        events.extend(option_events)
        claimed |= option_rows

        large_events, large_rows = detect_large_trades(
            prepared, min_amount=large_trade_usd, skip=claimed, tagger=_tags_for
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
