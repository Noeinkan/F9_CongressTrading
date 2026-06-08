"""Patterns route: committee relevance, coordinated trades, call/put,
volume anomalies, and bipartisan activity.

Reproduces the analytics surface of ``src/dashboard_pages/patterns.py`` as
plain JSON. The pure pandas helpers live in :mod:`src.api._patterns_analytics`
(Streamlit-free copies of ``dashboard_shared.analytics``); this router is a
thin shell that calls them and serializes the result.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, Query

from .._constants import COMMITTEE_SECTOR_MAP
from .._patterns_analytics import (
    bipartisan_tickers,
    call_put_monthly,
    committee_relevance_coverage,
    committee_relevant_trades,
    coordinated_pattern_transactions,
    detect_coordinated_trades,
    load_committee_assignments_live,
    score_committee_relevance,
    summarize_committee_relevance,
    volume_anomalies,
)
from ..query import Slice, get_slice
from ..security import require_auth
from ..serialize import iso_date, records

router = APIRouter(prefix="/api/patterns", tags=["patterns"])


_COMMITTEE_DRILL_COLUMNS = [
    "ticker",
    "sector",
    "matching_committees",
    "transaction_type_label",
    "transaction_date",
    "amount_range_raw",
]


def _committee_relevance(
    filtered: pd.DataFrame,
    assignments: dict[str, list[str]],
) -> dict[str, Any]:
    if not assignments:
        return {
            "summary": [],
            "members_with_overlap": [],
            "coverage": {
                "member_coverage_pct": 0.0,
                "sector_coverage_pct": 0.0,
                "members_mapped": 0,
            },
        }
    coverage = committee_relevance_coverage(filtered, assignments)
    scored = score_committee_relevance(filtered, assignments, COMMITTEE_SECTOR_MAP)
    if scored.empty:
        return {"summary": [], "members_with_overlap": [], "coverage": coverage}
    summary = summarize_committee_relevance(scored)
    relevant = committee_relevant_trades(scored)
    members_with_overlap = (
        sorted(relevant["member"].astype(str).unique().tolist()) if not relevant.empty else []
    )
    return {
        "summary": records(
            summary,
            [
                "member",
                "chamber",
                "party",
                "total_trades",
                "relevant_trades",
                "relevance_pct",
                "top_committee",
                "top_sector",
            ],
        ),
        "members_with_overlap": members_with_overlap,
        "coverage": coverage,
    }


def _coordinated(
    filtered: pd.DataFrame,
    *,
    window_days: int,
    min_members: int,
    limit: int,
) -> list[dict[str, Any]]:
    if filtered.empty:
        return []
    out = detect_coordinated_trades(
        filtered, window_days=window_days, min_members=min_members
    )
    if out.empty:
        return []
    out = out.head(limit)
    return records(
        out,
        ["ticker", "pattern", "members", "member_names", "trades", "date_from", "date_to"],
        date_columns=("date_from", "date_to"),
    )


def _call_put(filtered: pd.DataFrame) -> dict[str, Any]:
    cp = call_put_monthly(filtered)
    if cp.empty:
        return {"monthly": [], "ratio": []}
    monthly = records(cp, ["month", "option_side", "transactions"], date_columns=("month",))
    pivot = (
        cp.pivot(index="month", columns="option_side", values="transactions")
        .fillna(0)
        .reset_index()
    )
    ratio_records: list[dict[str, Any]] = []
    if "Call" in pivot.columns and "Put" in pivot.columns:
        for _, row in pivot.iterrows():
            call_n = float(row["Call"])
            put_n = float(row["Put"])
            ratio = (call_n / put_n) if put_n > 0 else float(call_n)
            ratio_records.append(
                {
                    "month": iso_date(row["month"]),
                    "call": int(call_n),
                    "put": int(put_n),
                    "call_put_ratio": float(ratio),
                }
            )
    return {"monthly": monthly, "ratio": ratio_records}


def _summary(
    s: Slice,
    *,
    window_days: int,
    min_members: int,
    coordinated_limit: int,
) -> dict[str, Any]:
    assignments = load_committee_assignments_live()
    committee = _committee_relevance(s.filtered, assignments)
    return {
        "ready": s.ready,
        "window_days": window_days,
        "min_members": min_members,
        "coordinated_limit": coordinated_limit,
        "committee": committee,
        "coordinated": _coordinated(
            s.filtered,
            window_days=window_days,
            min_members=min_members,
            limit=coordinated_limit,
        ),
        "call_put": _call_put(s.filtered),
        "volume_anomalies": records(
            volume_anomalies(s.filtered, recent_days=window_days),
            ["ticker", "recent_disclosures", "recent_per_month", "prior_per_month", "spike_ratio"],
        ),
        "bipartisan": records(
            bipartisan_tickers(s.filtered, window_days=window_days),
            [
                "ticker",
                "members",
                "democrat_trades",
                "republican_trades",
                "member_names",
                "date_from",
                "date_to",
            ],
            date_columns=("date_from", "date_to"),
        ),
    }


@router.get("/summary")
def patterns_summary(
    s: Slice = Depends(get_slice),
    window_days: int = Query(90, ge=30, le=365),
    min_members: int = Query(2, ge=2, le=8),
    coordinated_limit: int = Query(50, ge=1, le=500),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """All data needed to render the Patterns page for the current period slice."""
    if not s.ready:
        return {
            "ready": False,
            "window_days": window_days,
            "min_members": min_members,
            "coordinated_limit": coordinated_limit,
            "committee": _committee_relevance(s.filtered, {}),
            "coordinated": [],
            "call_put": {"monthly": [], "ratio": []},
            "volume_anomalies": [],
            "bipartisan": [],
        }
    return _summary(
        s,
        window_days=window_days,
        min_members=min_members,
        coordinated_limit=coordinated_limit,
    )


@router.get("/committee_relevant")
def committee_relevant(
    member: str = Query(..., min_length=1, description="Member full name."),
    s: Slice = Depends(get_slice),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """Disclosures for one member where their committees overlap the traded sector."""
    assignments = load_committee_assignments_live()
    if not assignments:
        return {"member": member, "assignments_loaded": False, "rows": []}
    scored = score_committee_relevance(s.filtered, assignments, COMMITTEE_SECTOR_MAP)
    relevant = committee_relevant_trades(scored)
    member_rel = relevant.loc[relevant["member"].astype(str) == member] if not relevant.empty else relevant
    return {
        "member": member,
        "assignments_loaded": True,
        "rows": records(
            member_rel,
            _COMMITTEE_DRILL_COLUMNS,
            date_columns=("transaction_date",),
        ),
    }


@router.get("/coordinated_transactions")
def coordinated_transactions(
    ticker: str = Query(..., min_length=1),
    pattern: str = Query(..., min_length=1, description='"Coordinated buy" or "Coordinated sell"'),
    window_days: int = Query(90, ge=30, le=365),
    limit: int = Query(200, ge=1, le=1000),
    s: Slice = Depends(get_slice),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """Return the disclosure rows backing a single coordinated-pattern row."""
    out = coordinated_pattern_transactions(
        s.filtered, ticker=ticker, pattern=pattern, window_days=window_days
    )
    if not out.empty and limit < len(out):
        out = out.head(limit)
    return {
        "ticker": ticker,
        "pattern": pattern,
        "window_days": window_days,
        "limit": limit,
        "rows": records(
            out,
            [
                "member",
                "ticker",
                "transaction_type_label",
                "transaction_date",
                "filing_date",
                "amount_range_raw",
                "chamber",
                "party",
            ],
            date_columns=("transaction_date", "filing_date"),
        ),
    }
