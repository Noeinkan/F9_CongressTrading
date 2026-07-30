"""Review queue route: KPIs, groupbys, paginated rows, and triage mutations.

Reproduces the analytics surface of ``src/dashboard_pages/review.py`` as plain
JSON. Charts are returned as raw aggregates; the frontend renders them.
Resolve/dismiss endpoints write back to SQLite ``review_queue`` / ``transactions``.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .._constants import REVIEW_COLUMNS
from .._format import format_percent
from ..query import Slice, get_slice
from ..repository import (
    accept_review_transaction,
    dismiss_review_transaction,
    resolve_review_transaction,
)
from ..security import require_auth
from ..serialize import records

router = APIRouter(prefix="/api/review", tags=["review"])

_ROW_COLUMNS = list(REVIEW_COLUMNS)

_DATE_COLUMNS = ("filing_date", "transaction_date")


class ResolveBody(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=16)
    apply_to_asset: bool = False


class AcceptBody(BaseModel):
    apply_to_asset: bool = False


def _count_group(frame: pd.DataFrame, key: str) -> list[dict[str, Any]]:
    if frame.empty or key not in frame.columns:
        return []
    agg = (
        frame.groupby(key, as_index=False)
        .size()
        .rename(columns={"size": "records"})
        .sort_values("records", ascending=False)
    )
    return records(agg, [key, "records"])


def _by_month(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty or "transaction_date" not in frame.columns:
        return []
    dated = frame.dropna(subset=["transaction_date"]).copy()
    if dated.empty:
        return []
    dated["month"] = dated["transaction_date"].dt.to_period("M").dt.to_timestamp()
    agg = (
        dated.groupby("month", as_index=False)
        .size()
        .rename(columns={"size": "records"})
        .sort_values("month")
    )
    return records(agg, ["month", "records"], date_columns=("month",))


def _kpis(review: pd.DataFrame) -> dict[str, Any]:
    total = int(len(review))
    open_count = int((review["status"] == "open").sum()) if total and "status" in review.columns else 0
    high_confidence_pct = 0.0
    if total and "confidence_score" in review.columns:
        scores = pd.to_numeric(review["confidence_score"], errors="coerce")
        high_confidence_pct = float((scores >= 0.7).sum() / total)
    return {
        "open_count": open_count,
        "total_count": total,
        "high_confidence_pct": high_confidence_pct,
        "high_confidence_label": format_percent(high_confidence_pct),
        "by_reason": _count_group(review, "reason"),
        "by_status": _count_group(review, "status"),
        "by_month": _by_month(review),
    }


def _rows(review: pd.DataFrame, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    total = int(len(review))
    if review.empty:
        return [], total
    sorted_frame = review.sort_values(
        ["transaction_date", "filing_date"],
        ascending=[False, False],
        kind="stable",
        na_position="last",
    )
    page = sorted_frame.iloc[offset : offset + limit]
    return records(page, _ROW_COLUMNS, date_columns=_DATE_COLUMNS), total


def _mutation_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.get("/summary")
def review_summary(
    s: Slice = Depends(get_slice),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """KPIs, groupbys, and a paginated slice of review rows for the active period."""
    if not s.ready:
        return {
            "ready": False,
            "review_source": s.review_source,
            "kpis": {
                "open_count": 0,
                "total_count": 0,
                "high_confidence_pct": 0.0,
                "high_confidence_label": format_percent(0.0),
                "by_reason": [],
                "by_status": [],
                "by_month": [],
            },
            "rows": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
        }

    rows, total = _rows(s.review, limit, offset)
    return {
        "ready": True,
        "review_source": s.review_source,
        "kpis": _kpis(s.review),
        "rows": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/items/{transaction_id}/resolve")
def review_resolve(
    transaction_id: int,
    body: ResolveBody,
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """Manually assign a ticker and clear the review-queue row."""
    try:
        return resolve_review_transaction(
            transaction_id,
            ticker=body.ticker,
            apply_to_asset=body.apply_to_asset,
        )
    except (KeyError, ValueError, RuntimeError) as exc:
        raise _mutation_http_error(exc) from exc


@router.post("/items/{transaction_id}/accept")
def review_accept(
    transaction_id: int,
    body: AcceptBody = AcceptBody(),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """Promote the transaction's current ticker to ``exact_match`` and clear the queue row."""
    try:
        return accept_review_transaction(
            transaction_id,
            apply_to_asset=body.apply_to_asset,
        )
    except (KeyError, ValueError, RuntimeError) as exc:
        raise _mutation_http_error(exc) from exc


@router.post("/items/{transaction_id}/dismiss")
def review_dismiss(
    transaction_id: int,
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """Drop the review-queue row without changing the underlying transaction."""
    try:
        return dismiss_review_transaction(transaction_id)
    except (KeyError, ValueError, RuntimeError) as exc:
        raise _mutation_http_error(exc) from exc
