"""Analytics for the Senate dashboard page.

Pure pandas over the prepared transactions frame (see
:func:`src.api.repository._prepare_transactions`). The overview figures — KPIs,
monthly activity, leaderboards — are the Home page's own, computed on the
Senate slice, so the two pages can never disagree. This module holds only what
is specific to the Senate view: the slice itself, how promptly senators file,
and the list of filings.

Senate filings carry no PDF link: efdsearch.senate.gov opens a report only
after the visitor accepts its terms, so a deep link lands on its home page.
Rows link to the senator's profile instead.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from ._format import format_disclosed_range, format_percent
from ._patterns_analytics import normalize_party
from .serialize import iso_date

# STOCK Act: a periodic transaction report is due 45 days after the trade.
STOCK_ACT_DEADLINE_DAYS = 45


def senate_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Rows filed with the Senate. Empty (same columns) when there are none."""
    if frame is None or frame.empty or "chamber" not in frame.columns:
        return frame.iloc[0:0] if frame is not None else pd.DataFrame()
    mask = frame["chamber"].astype(str).str.strip().str.casefold() == "senate"
    return frame.loc[mask]


def _filing_delay_days(frame: pd.DataFrame) -> pd.Series:
    """Days from trade to filing, for rows with both dates and a non-negative gap."""
    if frame.empty or not {"transaction_date", "filing_date"} <= set(frame.columns):
        return pd.Series(dtype="float64")
    traded = pd.to_datetime(frame["transaction_date"], errors="coerce")
    filed = pd.to_datetime(frame["filing_date"], errors="coerce")
    delay = (filed - traded).dt.days
    return delay[delay.notna() & (delay >= 0)]


def filing_timeliness(
    frame: pd.DataFrame,
    *,
    deadline_days: int = STOCK_ACT_DEADLINE_DAYS,
    top_n: int = 10,
) -> dict[str, Any]:
    """How promptly trades were disclosed, overall and per senator.

    ``late_filers`` ranks senators by trades filed past the deadline; a senator
    with no late trade is left out rather than listed with a zero.
    """
    delay = _filing_delay_days(frame)
    dated = int(len(delay))
    late_mask = delay > deadline_days
    late = int(late_mask.sum())
    share = (late / dated) if dated else 0.0

    late_filers: list[dict[str, Any]] = []
    if late:
        work = frame.loc[delay.index].assign(_delay=delay)
        grouped = work.groupby("member", as_index=False).agg(
            trades=("member", "size"),
            late_trades=("_delay", lambda s: int((s > deadline_days).sum())),
            worst_delay=("_delay", "max"),
        )
        grouped = grouped[grouped["late_trades"] > 0].sort_values(
            ["late_trades", "worst_delay"], ascending=[False, False]
        )
        late_filers = [
            {
                "member": str(r["member"]),
                "trades": int(r["trades"]),
                "late_trades": int(r["late_trades"]),
                "worst_days_late": int(r["worst_delay"]) - deadline_days,
            }
            for _, r in grouped.head(top_n).iterrows()
        ]

    return {
        "deadline_days": deadline_days,
        "dated_trades": dated,
        "late_trades": late,
        "late_share": share,
        "late_share_label": format_percent(share) if dated else "—",
        "median_delay_days": int(delay.median()) if dated else None,
        "late_filers": late_filers,
    }


def filing_list(frame: pd.DataFrame, *, limit: int = 50) -> list[dict[str, Any]]:
    """One row per filing, newest first: who filed, when, and what it held."""
    if frame is None or frame.empty or "member" not in frame.columns:
        return []
    work = frame.copy()
    doc = work["doc_id"].astype(str).str.strip() if "doc_id" in work.columns else ""
    # Rows without a document id fall back to member + filing date as the key.
    work["_filing_key"] = doc
    missing = work["_filing_key"].isin(["", "nan", "None"])
    work.loc[missing, "_filing_key"] = work.loc[missing, "filing_date"].astype(str)
    work["_ticker"] = work["ticker"].astype(str).str.strip().replace("", pd.NA)

    grouped = (
        work.groupby(["member", "_filing_key"], as_index=False, dropna=False)
        .agg(
            filing_date=("filing_date", "max"),
            trades=("member", "size"),
            tickers=("_ticker", "nunique"),
            amount_low=("amount_low", lambda s: float(pd.to_numeric(s, errors="coerce").sum())),
            amount_high=("amount_high", lambda s: float(pd.to_numeric(s, errors="coerce").sum())),
            traded_from=("transaction_date", "min"),
            traded_to=("transaction_date", "max"),
            party=("party", "first"),
            state=("state", "first"),
        )
        .sort_values(["filing_date", "trades"], ascending=[False, False], na_position="last")
        .head(limit)
    )
    return [
        {
            "member": str(r["member"]),
            "party": normalize_party(r["party"]),
            "state": "" if pd.isna(r["state"]) else str(r["state"]),
            "doc_id": str(r["_filing_key"]),
            "filing_date": iso_date(r["filing_date"]),
            "trades": int(r["trades"]),
            "tickers": int(r["tickers"]),
            "amount_low": float(r["amount_low"]),
            "amount_high": float(r["amount_high"]),
            "disclosed_range": format_disclosed_range(r["amount_low"], r["amount_high"]),
            "traded_from": iso_date(r["traded_from"]),
            "traded_to": iso_date(r["traded_to"]),
        }
        for _, r in grouped.iterrows()
    ]


def senate_coverage(frame: pd.DataFrame) -> dict[str, Any]:
    """What the Senate slice spans, for the page header."""
    if frame is None or frame.empty:
        return {"senators": 0, "filings": 0, "first_filing": None, "latest_filing": None}
    doc = frame["doc_id"].astype(str).str.strip() if "doc_id" in frame.columns else pd.Series(dtype=str)
    return {
        "senators": int(frame["member"].nunique()),
        "filings": int(doc[doc != ""].nunique()),
        "first_filing": iso_date(frame["filing_date"].min()),
        "latest_filing": iso_date(frame["filing_date"].max()),
    }
