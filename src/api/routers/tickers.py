"""Tickers route: paginated leaderboard + per-ticker profile.

Reproduces the analytics surface of ``src.dashboard_pages/tickers.py`` as
plain JSON. The pure pandas helpers live in :mod:`src.api._tickers_analytics`
(Streamlit-free copies of the pieces in ``dashboard_shared.analytics`` plus
the per-ticker profile that the page built inline). This router is a thin
shell that calls them and serializes the result.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from .._format import (
    add_disclosed_range_column,
    format_disclosed_range,
    sum_amount_high,
    sum_amount_low,
)
from .._tickers_analytics import (
    load_issuer_info_live,
    polygon_price_overlay,
    ticker_cumulative_exposure_payload,
    ticker_leaderboard,
    ticker_member_timeline_payload,
    ticker_profile,
)
from ..query import Slice, get_slice
from ..security import require_auth
from ..serialize import iso_date, records

router = APIRouter(prefix="/api/tickers", tags=["tickers"])


_LEADERBOARD_COLUMNS = [
    "ticker",
    "issuer_name",
    "sector",
    "trades",
    "members",
    "buy",
    "sell",
    "call",
    "put",
    "exchange",
    "amount_low",
    "amount_high",
    "disclosed_range",
    "first_trade",
    "last_trade",
]


_PROFILE_MEMBER_COLUMNS = [
    "member",
    "chamber",
    "party",
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


_PROFILE_TX_COLUMNS = [
    "member",
    "chamber",
    "party",
    "ticker",
    "transaction_type_label",
    "transaction_type",
    "transaction_date",
    "filing_date",
    "amount_low",
    "amount_high",
    "amount_range_raw",
    "issuer_name",
    "asset_name_raw",
    "disclosure_url",
]


SORTABLE_COLUMNS: frozenset[str] = frozenset(
    {
        "ticker",
        "issuer_name",
        "sector",
        "trades",
        "members",
        "buy",
        "sell",
        "call",
        "put",
        "exchange",
        "amount_low",
        "amount_high",
        "first_trade",
        "last_trade",
    }
)


def _disclosed_range_row(low: float, high: float) -> str:
    return format_disclosed_range(low, high)


@router.get("")
def tickers_list(
    s: Slice = Depends(get_slice),
    sort: str = Query("trades", description="Column to sort by."),
    order: str = Query("desc", description="asc or desc."),
    search: str | None = Query(
        None, description="Case-insensitive substring across ticker / issuer_name."
    ),
    page: int = Query(1, ge=1, description="1-based page number."),
    page_size: int = Query(50, ge=1, le=200, description="Rows per page (max 200)."),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """Paginated ticker leaderboard for the current period slice.

    Mirrors the Streamlit ticker dropdown on the page — gives the React
    shell the list of available symbols + a snapshot of activity per
    symbol, so the user can pick one and then drill in.
    """
    if sort not in SORTABLE_COLUMNS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsortable column '{sort}'. Allowed: {sorted(SORTABLE_COLUMNS)}",
        )
    if order not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="order must be 'asc' or 'desc'.")

    if not s.ready:
        return {
            "ready": False,
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
            "sort": {"column": sort, "order": order},
            "search": search or "",
            "rows": [],
            "source": s.transaction_source,
        }

    board = ticker_leaderboard(s.filtered)
    if board.empty:
        return {
            "ready": True,
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
            "sort": {"column": sort, "order": order},
            "search": search or "",
            "rows": [],
            "source": s.transaction_source,
        }

    if search:
        needle = search.strip().lower()
        if needle:
            mask = (
                board["ticker"].astype(str).str.lower().str.contains(needle, regex=False, na=False)
                | board["issuer_name"].astype(str).str.lower().str.contains(needle, regex=False, na=False)
            )
            board = board.loc[mask].reset_index(drop=True)

    # Stable secondary sort by ticker asc to keep ties deterministic.
    ascending = order == "asc"
    sort_cols = [sort, "ticker"] if sort != "ticker" else ["ticker"]
    sort_asc = [ascending, True] if sort != "ticker" else [True]
    board = board.sort_values(sort_cols, ascending=sort_asc, kind="stable")

    total = int(len(board))
    start = (page - 1) * page_size
    page_slice = board.iloc[start : start + page_size].copy()
    page_slice = add_disclosed_range_column(
        page_slice, low_col="amount_low", high_col="amount_high"
    )

    rows = records(
        page_slice,
        _LEADERBOARD_COLUMNS,
        date_columns=("first_trade", "last_trade"),
    )
    total_pages = (total + page_size - 1) // page_size if total else 0
    return {
        "ready": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "sort": {"column": sort, "order": order},
        "search": search or "",
        "rows": rows,
        "source": s.transaction_source,
    }


@router.get("/{ticker}")
def ticker_detail(
    ticker: str,
    s: Slice = Depends(get_slice),
    tx_limit: int = Query(200, ge=1, le=1000, description="Cap on transactions returned."),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """Per-ticker profile: company header, KPIs, member breakdown, trade history.

    The ticker path is normalized to upper case. When the active slice has
    no trades for the symbol we still return a 200 with empty arrays + the
    issuer info (when available) so the React shell can render a useful
    empty state, the same way the Streamlit page does for an unknown
    symbol.
    """
    t = str(ticker).strip().upper()
    if not t:
        raise HTTPException(status_code=422, detail="ticker is required.")

    issuer_info = load_issuer_info_live(t)
    profile = ticker_profile(s.filtered, t)
    kpis = profile["kpis"]
    # Recompute disclosed range from numeric totals so the JSON consumers
    # never need to call format helpers themselves.
    disclosed_range = format_disclosed_range(
        float(kpis.get("amount_low_total") or 0.0),
        float(kpis.get("amount_high_total") or 0.0),
    )

    if not s.ready:
        return {
            "ready": False,
            "ticker": t,
            "issuer": issuer_info,
            "kpis": kpis,
            "disclosed_range": disclosed_range,
            "members": [],
            "transactions": [],
            "source": s.transaction_source,
        }

    members_df: pd.DataFrame = profile["members"]
    if isinstance(members_df, list):
        members_df = pd.DataFrame(columns=_PROFILE_MEMBER_COLUMNS)
    if not members_df.empty:
        members_rows = records(
            members_df,
            _PROFILE_MEMBER_COLUMNS,
            date_columns=("first_trade", "last_trade"),
        )
    else:
        members_rows = []

    tx_df: pd.DataFrame = profile["transactions"]
    if isinstance(tx_df, list):
        tx_df = pd.DataFrame(columns=_PROFILE_TX_COLUMNS)
    tx_total = int(len(tx_df))
    if not tx_df.empty and tx_limit < tx_total:
        tx_df = tx_df.head(tx_limit)
    tx_rows = records(
        tx_df,
        _PROFILE_TX_COLUMNS,
        date_columns=("transaction_date", "filing_date"),
    )

    return {
        "ready": profile["ready"],
        "ticker": t,
        "issuer": issuer_info,
        "kpis": {
            **kpis,
            "disclosed_range": disclosed_range,
            "amount_low_total": float(kpis.get("amount_low_total") or 0.0),
            "amount_high_total": float(kpis.get("amount_high_total") or 0.0),
        },
        "disclosed_range": disclosed_range,
        "members": members_rows,
        "transactions": tx_rows,
        "transactions_total": tx_total,
        "transactions_limit": tx_limit,
        "source": s.transaction_source,
    }


@router.get("/{ticker}/price_overlay")
def ticker_price_overlay(
    ticker: str,
    s: Slice = Depends(get_slice),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """Polygon-cache close series + trade markers for one ticker.

    Lighter endpoint that the React page can lazy-load after the profile
    is on screen, so the cache miss (or empty cache) for one symbol
    doesn't block the rest of the page.
    """
    t = str(ticker).strip().upper()
    if not t:
        raise HTTPException(status_code=422, detail="ticker is required.")
    if not s.ready:
        return {"ticker": t, "ready": False, "bars": [], "trades": []}
    return polygon_price_overlay(s.filtered, t)


_TIMELINE_ROW_COLUMNS = [
    "member",
    "transaction_date",
    "transaction_type",
    "transaction_type_label",
    "amount_range_raw",
    "issuer_name",
    "chamber",
]

_CUMULATIVE_ROW_COLUMNS = [
    "member",
    "transaction_date",
    "cumulative_net",
    "cumulative_label",
    "txn_type_label",
    "amount_range_raw",
]


@router.get("/{ticker}/member_timeline")
def ticker_member_timeline(
    ticker: str,
    s: Slice = Depends(get_slice),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """Member scatter timeline rows for one ticker (y = member)."""
    t = str(ticker).strip().upper()
    if not t:
        raise HTTPException(status_code=422, detail="ticker is required.")
    if not s.ready:
        return {"ticker": t, "members": [], "rows": []}
    payload = ticker_member_timeline_payload(s.filtered, t)
    rows_df = pd.DataFrame(payload["rows"]) if payload["rows"] else pd.DataFrame()
    return {
        "ticker": payload["ticker"],
        "members": payload["members"],
        "rows": records(rows_df, _TIMELINE_ROW_COLUMNS, date_columns=("transaction_date",))
        if not rows_df.empty
        else [],
    }


@router.get("/{ticker}/cumulative_exposure")
def ticker_cumulative_exposure(
    ticker: str,
    s: Slice = Depends(get_slice),
    top_n: int = Query(16, ge=1, le=32, description="Max members in the facet chart."),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """Per-member cumulative net exposure rows for one ticker."""
    t = str(ticker).strip().upper()
    if not t:
        raise HTTPException(status_code=422, detail="ticker is required.")
    if not s.ready:
        return {"ticker": t, "members": [], "truncated": False, "rows": []}
    payload = ticker_cumulative_exposure_payload(s.filtered, t, top_n=top_n)
    rows_df = pd.DataFrame(payload["rows"]) if payload["rows"] else pd.DataFrame()
    return {
        "ticker": payload["ticker"],
        "members": payload["members"],
        "truncated": payload["truncated"],
        "rows": records(rows_df, _CUMULATIVE_ROW_COLUMNS, date_columns=("transaction_date",))
        if not rows_df.empty
        else [],
    }
