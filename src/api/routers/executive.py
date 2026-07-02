"""Executive (OGE 278-T / 278e) routes for the dashboard.

Thin router that:
* serves filer/filing summaries (``/api/executive/filers``, ``/api/executive/filings``)
* reuses :func:`src.api.repository._prepare_transactions` (filtered to
  ``chamber == "Executive"``) for the periodic-transactions list
* exposes the new ``executive_holdings`` table for annual-report rows
* delegates analytics to :mod:`src.api._executive_analytics`
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, Query

from .. import _executive_analytics
from .._constants import TRANSACTION_COLUMNS
from ..repository import (
    _prepare_transactions,
    available_years,
    filter_by_lookback,
    load_transactions,
)
from ..security import require_auth
from ..serialize import records

router = APIRouter(prefix="/api/executive", tags=["executive"])


_HOLDINGS_QUERY = """
SELECT
    eh.id AS id,
    eh.filing_id AS filing_id,
    eh.asset_name AS asset_name,
    eh.value_range AS value_range,
    eh.owner_type AS owner_type,
    eh.asset_type AS asset_type,
    eh.source_page AS source_page,
    eh.source_row AS source_row,
    eh.parse_warning AS parse_warning,
    eh.created_at AS created_at,
    f.filing_type AS filing_type,
    f.filing_date AS filing_date,
    f.doc_id AS doc_id,
    f.source_url AS source_url,
    f.raw_document_path AS raw_document_path,
    m.full_name AS filer_name,
    m.id AS member_id
FROM executive_holdings eh
JOIN filings f ON f.id = eh.filing_id
JOIN members m ON m.id = f.member_id
ORDER BY f.filing_date DESC, eh.id ASC
"""


_FILINGS_QUERY = """
SELECT
    f.id AS filing_id,
    m.full_name AS filer_name,
    m.id AS member_id,
    f.filing_type AS filing_type,
    f.filing_date AS filing_date,
    f.doc_id AS doc_id,
    f.source_url AS source_url,
    f.raw_document_path AS raw_document_path,
    COALESCE(t.cnt, 0) AS transaction_count
FROM filings f
JOIN members m ON m.id = f.member_id
LEFT JOIN (
    SELECT filing_id, COUNT(*) AS cnt
    FROM transactions
    GROUP BY filing_id
) t ON t.filing_id = f.id
WHERE f.chamber = 'Executive'
ORDER BY f.filing_date DESC, f.id ASC
"""


_FILERS_QUERY = """
SELECT
    m.id AS member_id,
    m.full_name AS filer_name,
    MAX(f.filing_date) AS latest_filing_date,
    COUNT(DISTINCT f.id) AS filing_count,
    COALESCE(SUM(t.cnt), 0) AS transaction_count
FROM members m
LEFT JOIN filings f ON f.member_id = m.id AND f.chamber = 'Executive'
LEFT JOIN (
    SELECT filing_id, COUNT(*) AS cnt
    FROM transactions
    GROUP BY filing_id
) t ON t.filing_id = f.id
WHERE m.chamber = 'Executive'
GROUP BY m.id, m.full_name
ORDER BY latest_filing_date DESC, m.full_name ASC
"""


def _executive_transactions_frame() -> tuple[pd.DataFrame, str]:
    """Load the full transactions frame and restrict it to Executive rows.

    Reuses the same in-process cache the rest of the API uses so repeated
    requests don't re-read SQLite.
    """
    frame, source = load_transactions()
    if frame.empty:
        return frame, source
    if "chamber" not in frame.columns:
        return frame.iloc[0:0].copy(), source
    mask = frame["chamber"].astype(str).str.strip().str.casefold() == "executive"
    return frame.loc[mask].copy(), source


def _apply_executive_filters(
    frame: pd.DataFrame,
    *,
    lookback: int | None,
    quarters: list[int] | None,
    transaction_type: str | None,
    owner_type: str | None,
    filing_doc_id: str | None,
) -> pd.DataFrame:
    """Apply the Executive-page filters to a transactions frame."""
    work = frame
    if work.empty:
        return work
    if filing_doc_id:
        target = filing_doc_id.strip()
        if target and "doc_id" in work.columns:
            work = work.loc[work["doc_id"].astype(str) == target]
    work = filter_by_lookback(work, lookback=lookback, quarters=quarters)
    if transaction_type:
        target = transaction_type.strip().casefold()
        work = work.loc[work["transaction_type"].astype(str).str.casefold() == target]
    if owner_type:
        target = owner_type.strip().casefold()
        work = work.loc[work["owner_type"].astype(str).str.casefold() == target]
    return work


@router.get("/filers")
def executive_filers(_user: str = Depends(require_auth)) -> dict[str, Any]:
    """Per-filer summary cards for the Executive page."""
    from ...db import get_connection, init_db

    conn = get_connection()
    try:
        init_db(conn)
        rows = conn.execute(_FILERS_QUERY).fetchall()
    finally:
        conn.close()

    filers = [
        {
            "filer_name": str(r["filer_name"]),
            "latest_filing_date": r["latest_filing_date"],
            "filing_count": int(r["filing_count"] or 0),
            "transaction_count": int(r["transaction_count"] or 0),
        }
        for r in rows
    ]
    return {"ready": bool(filers), "filers": filers}


@router.get("/filings")
def executive_filings(_user: str = Depends(require_auth)) -> dict[str, Any]:
    """List every OGE filing known to the database (278-T and 278e)."""
    from ...db import get_connection, init_db

    conn = get_connection()
    try:
        init_db(conn)
        rows = conn.execute(_FILINGS_QUERY).fetchall()
    finally:
        conn.close()

    filings = [
        {
            "filing_id": int(r["filing_id"]),
            "filer_name": str(r["filer_name"]),
            "filing_type": str(r["filing_type"]),
            "filing_date": r["filing_date"],
            "doc_id": str(r["doc_id"] or ""),
            "source_url": str(r["source_url"] or ""),
            "raw_document_path": str(r["raw_document_path"] or ""),
            "transaction_count": int(r["transaction_count"] or 0),
        }
        for r in rows
    ]
    return {"ready": bool(filings), "filings": filings}


@router.get("/transactions")
def executive_transactions(
    lookback: int | None = Query(
        None,
        ge=0,
        description="Lookback window in years (0/None = all time).",
    ),
    quarters: str | None = Query(
        None,
        description="Comma-separated quarters (1-4). Omit for all quarters.",
    ),
    transaction_type: str | None = Query(
        None,
        description="Filter by raw transaction_type (e.g. 'P', 'P (Buy)', 'S').",
    ),
    owner_type: str | None = Query(
        None,
        description="Filter by owner_type (filer/spouse/dependent).",
    ),
    filing_doc_id: str | None = Query(
        None,
        description="Restrict to a single filing by its doc_id (matches filings.doc_id).",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """Periodic-transactions list (278-T rows) for the Executive page.

    Reuses ``_prepare_transactions`` so columns stay aligned with the rest
    of the dashboard; pagination is server-side.
    """
    frame, source = _executive_transactions_frame()
    years_all = available_years(frame)
    parsed_quarters: list[int] | None = None
    if quarters:
        parsed_quarters = [int(x) for x in quarters.split(",") if x.strip().isdigit() and 1 <= int(x) <= 4]
        parsed_quarters = parsed_quarters or None
    normalized_lookback = None if lookback in (None, 0) else lookback

    filtered = _apply_executive_filters(
        frame,
        lookback=normalized_lookback,
        quarters=parsed_quarters,
        transaction_type=transaction_type,
        owner_type=owner_type,
        filing_doc_id=filing_doc_id,
    )

    if filtered.empty:
        return {
            "ready": False,
            "transaction_source": source,
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
            "rows": [],
            "summary": _executive_analytics.compute_executive_summary(filtered),
            "monthly_timeline": [],
            "by_owner_type": {},
        }

    # Make sure every TRANSACTION_COLUMNS exists (in case the Executive slice
    # was empty before the cache was populated).
    for column in TRANSACTION_COLUMNS:
        if column not in filtered.columns:
            filtered[column] = pd.NA
    prepared = _prepare_transactions(filtered)

    sorted_frame = prepared.sort_values(
        ["transaction_date", "filing_date"],
        ascending=[False, False],
        kind="stable",
        na_position="last",
    )
    total = int(len(sorted_frame))
    total_pages = (total + page_size - 1) // page_size if total else 0
    start = (page - 1) * page_size
    page_slice = sorted_frame.iloc[start : start + page_size]

    return {
        "ready": True,
        "transaction_source": source,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "rows": records(
            page_slice,
            TRANSACTION_COLUMNS + ["transaction_type_label", "disclosure_url"],
            date_columns=("transaction_date", "filing_date"),
        ),
        "summary": _executive_analytics.compute_executive_summary(prepared),
        "monthly_timeline": _executive_analytics.compute_monthly_timeline(prepared),
        "by_owner_type": _executive_analytics.compute_by_owner_type(prepared),
        "years_available": years_all,
    }


@router.get("/holdings")
def executive_holdings(
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """Annual-report (278e) holdings rows joined to their filings.

    Returns all rows in ``executive_holdings`` joined with the latest
    filings metadata — the frontend renders the most recent 278e per filer
    by default.
    """
    from ...db import get_connection, init_db

    conn = get_connection()
    try:
        init_db(conn)
        rows = conn.execute(_HOLDINGS_QUERY).fetchall()
    finally:
        conn.close()

    holdings = [
        {
            "id": int(r["id"]),
            "filing_id": int(r["filing_id"]),
            "filer_name": str(r["filer_name"]),
            "filing_type": str(r["filing_type"]),
            "filing_date": r["filing_date"],
            "doc_id": str(r["doc_id"] or ""),
            "source_url": str(r["source_url"] or ""),
            "raw_document_path": str(r["raw_document_path"] or ""),
            "asset_name": str(r["asset_name"] or ""),
            "value_range": str(r["value_range"] or ""),
            "owner_type": str(r["owner_type"] or ""),
            "asset_type": str(r["asset_type"] or ""),
            "source_page": int(r["source_page"]) if r["source_page"] is not None else None,
            "parse_warning": str(r["parse_warning"] or ""),
        }
        for r in rows
    ]
    return {"ready": bool(holdings), "holdings": holdings}