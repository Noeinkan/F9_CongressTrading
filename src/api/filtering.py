"""Pure sort/filter/paginate helpers for the Raw transactions table.

Mirrors the shape of :mod:`src.api.query` (a frozen dataclass + a FastAPI
``Query`` dependency) but for the interactive Raw table, whose sort, filter, and
pagination are driven server-side by TanStack Table in the React rewrite. No
Streamlit imports — only pandas + FastAPI (FastAPI is already a dependency of
``query.py`` so this is consistent).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from fastapi import Query
from fastapi.exceptions import HTTPException

# Columns the frontend may sort by. Matches keys present on the prepared frame
# (see repository._prepare_transactions).
SORTABLE_COLUMNS: frozenset[str] = frozenset(
    {
        "member",
        "chamber",
        "party",
        "ticker",
        "transaction_type_label",
        "transaction_date",
        "filing_date",
        "amount_low",
        "amount_high",
        "confidence_score",
    }
)


@dataclass(frozen=True)
class RawParams:
    search: str | None
    member: str | None
    chamber: str | None
    party: str | None
    ticker: str | None
    transaction_type: str | None
    date_from: str | None
    date_to: str | None
    amount_min: float | None
    amount_max: float | None
    sort: str
    order: str
    page: int
    page_size: int


def raw_params(
    search: str | None = Query(None, description="Case-insensitive substring across member/ticker/issuer/asset."),
    member: str | None = Query(None, description="Exact member name."),
    chamber: str | None = Query(None, description="Exact chamber (House/Senate)."),
    party: str | None = Query(None, description="Exact party."),
    ticker: str | None = Query(None, description="Exact ticker (case-insensitive)."),
    transaction_type: str | None = Query(
        None, description="Match against transaction_type code or its display label."
    ),
    date_from: str | None = Query(None, description="Inclusive lower bound on transaction_date (YYYY-MM-DD)."),
    date_to: str | None = Query(None, description="Inclusive upper bound on transaction_date (YYYY-MM-DD)."),
    amount_min: float | None = Query(None, description="Minimum disclosed upper-bound amount (amount_high)."),
    amount_max: float | None = Query(None, description="Maximum disclosed upper-bound amount (amount_high)."),
    sort: str = Query("transaction_date", description="Column to sort by."),
    order: str = Query("desc", description="Sort direction: asc or desc."),
    page: int = Query(1, ge=1, description="1-based page number."),
    page_size: int = Query(50, ge=1, le=200, description="Rows per page (max 200)."),
) -> RawParams:
    if sort not in SORTABLE_COLUMNS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsortable column '{sort}'. Allowed: {sorted(SORTABLE_COLUMNS)}",
        )
    if order not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="order must be 'asc' or 'desc'.")
    return RawParams(
        search=search,
        member=member,
        chamber=chamber,
        party=party,
        ticker=ticker,
        transaction_type=transaction_type,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )


def apply_filters(frame: pd.DataFrame, p: RawParams) -> pd.DataFrame:
    """Return rows of ``frame`` matching every set filter in ``p``."""
    if frame.empty:
        return frame

    mask = pd.Series(True, index=frame.index)

    if p.search:
        needle = p.search.strip().lower()
        if needle:
            search_cols = ["member", "ticker", "issuer_name", "asset_name_normalized"]
            sub = pd.Series(False, index=frame.index)
            for col in search_cols:
                if col in frame.columns:
                    sub |= frame[col].fillna("").astype(str).str.lower().str.contains(needle, regex=False)
            mask &= sub

    if p.member and "member" in frame.columns:
        mask &= frame["member"].astype(str) == p.member
    if p.chamber and "chamber" in frame.columns:
        mask &= frame["chamber"].astype(str) == p.chamber
    if p.party and "party" in frame.columns:
        mask &= frame["party"].astype(str) == p.party
    if p.ticker and "ticker" in frame.columns:
        # ticker is upper-cased in _prepare_transactions; match the same way.
        mask &= frame["ticker"].astype(str) == p.ticker.strip().upper()
    if p.transaction_type:
        tt = p.transaction_type.strip()
        sub = pd.Series(False, index=frame.index)
        if "transaction_type" in frame.columns:
            sub |= frame["transaction_type"].astype(str) == tt
        if "transaction_type_label" in frame.columns:
            sub |= frame["transaction_type_label"].astype(str) == tt
        mask &= sub

    if (p.date_from or p.date_to) and "transaction_date" in frame.columns:
        tx = pd.to_datetime(frame["transaction_date"], errors="coerce")
        if p.date_from:
            lo = pd.to_datetime(p.date_from, errors="coerce")
            mask &= tx.notna() & (tx >= lo)
        if p.date_to:
            hi = pd.to_datetime(p.date_to, errors="coerce")
            mask &= tx.notna() & (tx <= hi)

    # amount_min/amount_max are applied to amount_high (the disclosed upper bound).
    if (p.amount_min is not None or p.amount_max is not None) and "amount_high" in frame.columns:
        amt = pd.to_numeric(frame["amount_high"], errors="coerce")
        if p.amount_min is not None:
            mask &= amt.notna() & (amt >= p.amount_min)
        if p.amount_max is not None:
            mask &= amt.notna() & (amt <= p.amount_max)

    return frame[mask]


def apply_sort(frame: pd.DataFrame, sort: str, order: str) -> pd.DataFrame:
    """Sort by ``sort`` with a stable secondary sort by filing_date desc.

    The secondary sort reproduces the Streamlit Raw default ordering
    (raw_data.py:95 sorts by ``[transaction_date, filing_date]`` descending).
    """
    if frame.empty or sort not in frame.columns:
        return frame
    ascending = order == "asc"
    by = [sort]
    asc = [ascending]
    if sort != "filing_date" and "filing_date" in frame.columns:
        by.append("filing_date")
        asc.append(False)
    return frame.sort_values(by=by, ascending=asc, kind="stable", na_position="last")


def paginate(frame: pd.DataFrame, page: int, page_size: int) -> tuple[pd.DataFrame, int]:
    """Return ``(page_slice, total_before_pagination)``.

    An out-of-range page yields an empty slice but the real total.
    """
    total = int(len(frame))
    start = (page - 1) * page_size
    return frame.iloc[start : start + page_size], total
