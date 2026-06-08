"""Members route: leaderboard + per-member drill-downs.

Reproduces the analytics surface of ``src/dashboard_pages/members.py`` as
plain JSON. The pure pandas helpers live in :mod:`src.api._patterns_analytics`
(shared with the patterns router — the members page consumes the same
``member_ticker_breakdown`` / ``member_committee_relevant_transactions`` /
``member_leaderboard`` functions). This router is a thin shell that calls them
and serializes the result.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from .._constants import COMMITTEE_SECTOR_MAP
from .._format import (
    add_disclosed_range_column,
    format_disclosed_range,
    sum_amount_high,
    sum_amount_low,
)
from .._patterns_analytics import (
    committee_relevant_trades,
    load_committee_assignments_live,
    member_activity_timeline,
    member_committee_relevant_transactions,
    member_leaderboard,
    member_ticker_breakdown,
    score_committee_relevance,
)
from .._sparklines import monthly_series
from ..query import Slice, get_slice
from ..security import require_auth
from ..serialize import iso_date, records

router = APIRouter(prefix="/api/members", tags=["members"])


_LEADERBOARD_COLUMNS = [
    "member",
    "trades",
    "tickers",
    "amount_low",
    "amount_high",
    "chamber",
    "party",
    "state",
]


_PROFILE_DRILL_COLUMNS = [
    "ticker",
    "buy",
    "sell",
    "call",
    "put",
    "exchange",
    "trades",
    "amount_low_sum",
    "amount_high_sum",
    "disclosed_range",
    "first_trade",
    "last_trade",
]


_COMMITTEE_DRILL_COLUMNS = [
    "ticker",
    "sector",
    "matching_committees",
    "transaction_type_label",
    "transaction_date",
    "amount_range_raw",
]


def _leaderboard(filtered: pd.DataFrame) -> list[dict[str, Any]]:
    if filtered.empty:
        return []
    board = member_leaderboard(filtered)
    if board.empty:
        return []
    return records(
        board,
        _LEADERBOARD_COLUMNS,
    )


def _per_member_kpis(filtered: pd.DataFrame, member: str) -> dict[str, Any]:
    profile = filtered.loc[filtered["member"].astype(str) == member]
    if profile.empty:
        return {
            "member": member,
            "trades": 0,
            "tickers": 0,
            "amount_low_total": 0.0,
            "amount_high_total": 0.0,
            "disclosed_range": "—",
            "chamber": "",
            "party": "",
            "state": "",
            "sparklines": {
                "transactions": [],
                "tickers": [],
                "disclosed_amount_high": [],
            },
        }
    amount_low_total = sum_amount_low(profile)
    amount_high_total = sum_amount_high(profile)
    chamber = str(profile["chamber"].iloc[0]) if "chamber" in profile.columns else ""
    party_raw = profile["party"].iloc[0] if "party" in profile.columns else ""
    state = str(profile["state"].iloc[0]) if "state" in profile.columns else ""
    # Reuse the same party normalizer the leaderboard uses, so the two are consistent.
    from .._patterns_analytics import normalize_party

    return {
        "member": member,
        "trades": int(len(profile)),
        "tickers": int(
            profile.loc[profile["ticker"].astype(str).str.strip() != "", "ticker"].nunique()
        ),
        "amount_low_total": float(amount_low_total),
        "amount_high_total": float(amount_high_total),
        "disclosed_range": format_disclosed_range(amount_low_total, amount_high_total),
        "chamber": chamber,
        "party": normalize_party(party_raw),
        "state": state,
        "sparklines": {
            "transactions": monthly_series(profile, "transactions") or [],
            "tickers": monthly_series(profile, "tickers") or [],
            "disclosed_amount_high": monthly_series(profile, "disclosed_amount_high") or [],
        },
    }


def _validate_member(filtered: pd.DataFrame, member: str) -> None:
    """Reject unknown members with 404, mirroring the leaderboard-only contract."""
    options = filtered["member"].astype(str).unique().tolist() if not filtered.empty else []
    if member not in options:
        raise HTTPException(status_code=404, detail=f"Unknown member: {member}")


@router.get("/summary")
def members_summary(
    s: Slice = Depends(get_slice),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """Leaderboard + KPI sparklines for the active period slice."""
    return {
        "ready": s.ready,
        "transaction_source": s.transaction_source,
        "leaderboard": _leaderboard(s.filtered),
        "kpi_sparklines": {
            "members": monthly_series(s.filtered, "members") or [],
            "tickers": monthly_series(s.filtered, "tickers") or [],
            "transactions": monthly_series(s.filtered, "transactions") or [],
        },
    }


@router.get("/{member}/tickers")
def member_tickers(
    member: str,
    s: Slice = Depends(get_slice),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """Per-ticker buy/sell/call/put counts for one member in the active slice."""
    if not s.ready:
        return {"member": member, "kpis": {}, "rows": []}
    _validate_member(s.filtered, member)
    breakdown = member_ticker_breakdown(s.filtered, member)
    if breakdown.empty:
        return {
            "member": member,
            "kpis": _per_member_kpis(s.filtered, member),
            "rows": [],
        }
    rows = add_disclosed_range_column(
        breakdown, low_col="amount_low_sum", high_col="amount_high_sum"
    )
    return {
        "member": member,
        "kpis": _per_member_kpis(s.filtered, member),
        "rows": records(
            rows,
            _PROFILE_DRILL_COLUMNS,
            date_columns=("first_trade", "last_trade"),
        ),
    }


@router.get("/{member}/committee_relevant")
def member_committee_relevant(
    member: str,
    s: Slice = Depends(get_slice),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """Committee-overlap drill-down for one member (mirrors
    ``/api/patterns/committee_relevant`` but pre-filtered to a single member)."""
    assignments = load_committee_assignments_live()
    if not assignments:
        return {
            "member": member,
            "assignments_loaded": False,
            "rows": [],
        }
    if not s.ready:
        return {"member": member, "assignments_loaded": True, "rows": []}
    _validate_member(s.filtered, member)
    relevant = member_committee_relevant_transactions(
        s.filtered, member, assignments, COMMITTEE_SECTOR_MAP
    )
    # If the per-member helper came back empty (no committee matches), still
    # report that assignments were loaded so the frontend can render a useful
    # empty state.
    if relevant.empty:
        return {"member": member, "assignments_loaded": True, "rows": []}
    return {
        "member": member,
        "assignments_loaded": True,
        "rows": records(
            relevant,
            _COMMITTEE_DRILL_COLUMNS,
            date_columns=("transaction_date",),
        ),
    }


_ACTIVITY_TIMELINE_COLUMNS = [
    "ticker",
    "transaction_date",
    "transaction_type",
    "transaction_type_label",
    "amount_range_raw",
    "issuer_name",
]


@router.get("/{member}/activity_timeline")
def member_activity_timeline_route(
    member: str,
    s: Slice = Depends(get_slice),
    top_n: int = Query(25, ge=1, le=100, description="Max tickers on the timeline y-axis."),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """Activity-over-time scatter rows for one member (y = ticker)."""
    if not s.ready:
        return {
            "member": member,
            "truncated": False,
            "truncate_note": "",
            "tickers": [],
            "rows": [],
        }
    _validate_member(s.filtered, member)
    payload = member_activity_timeline(s.filtered, member, top_n=top_n)
    return {
        "member": payload["member"],
        "truncated": payload["truncated"],
        "truncate_note": payload["truncate_note"],
        "tickers": payload["tickers"],
        "rows": records(
            pd.DataFrame(payload["rows"]) if payload["rows"] else pd.DataFrame(),
            _ACTIVITY_TIMELINE_COLUMNS,
            date_columns=("transaction_date",),
        )
        if payload["rows"]
        else [],
    }
