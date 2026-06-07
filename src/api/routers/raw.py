"""Raw transactions route: server-side sort / filter / paginate + CSV export.

Replaces the interactive Streamlit Raw page
(``src/dashboard_pages/raw_data.py``). The React rewrite drives the table
(TanStack Table) server-side, so this route owns sort/filter/pagination; the
pure logic lives in :mod:`src.api.filtering`. Polygon return-estimate columns
are deferred — this ships the core transaction columns, matching the current
Streamlit CSV export which dumps the plain filtered frame.
"""
from __future__ import annotations

import io
from math import ceil
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from .._constants import TRANSACTION_COLUMNS
from ..filtering import RawParams, SORTABLE_COLUMNS, apply_filters, apply_sort, paginate, raw_params
from ..query import Slice, get_slice
from ..security import require_auth
from ..serialize import records

router = APIRouter(prefix="/api/raw", tags=["raw"])

# Output column order: transaction columns, then the two computed columns the
# table needs (label for display, url for the disclosure link).
_RAW_COLUMNS = TRANSACTION_COLUMNS + ["transaction_type_label", "disclosure_url"]

_DATE_COLUMNS = ("transaction_date", "filing_date")


def _meta(key: str, label: str, type_: str) -> dict[str, Any]:
    return {"key": key, "label": label, "type": type_, "sortable": key in SORTABLE_COLUMNS}


# Static column descriptor so the React table can render headers without
# hardcoding them. ``type`` ∈ text/date/currency/number.
_COLUMN_META: list[dict[str, Any]] = [
    _meta("member", "Member", "text"),
    _meta("chamber", "Chamber", "text"),
    _meta("party", "Party", "text"),
    _meta("state", "State", "text"),
    _meta("ticker", "Ticker", "text"),
    _meta("issuer_name", "Issuer", "text"),
    _meta("asset_name_normalized", "Asset", "text"),
    _meta("transaction_type_label", "Type", "text"),
    _meta("transaction_date", "Transaction date", "date"),
    _meta("filing_date", "Filing date", "date"),
    _meta("amount_low", "Amount low", "currency"),
    _meta("amount_high", "Amount high", "currency"),
    _meta("amount_range_raw", "Disclosed range", "text"),
    _meta("confidence_score", "Confidence", "number"),
    _meta("review_status", "Review status", "text"),
    _meta("disclosure_url", "Disclosure", "text"),
]


def _sort_meta(p: RawParams) -> dict[str, str]:
    return {"column": p.sort, "order": p.order}


@router.get("/transactions")
def raw_transactions(
    s: Slice = Depends(get_slice),
    p: RawParams = Depends(raw_params),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """A sorted/filtered/paginated page of the raw transaction table."""
    if not s.ready:
        return {
            "ready": False,
            "total": 0,
            "page": p.page,
            "page_size": p.page_size,
            "total_pages": 0,
            "sort": _sort_meta(p),
            "rows": [],
            "columns": _COLUMN_META,
            "source": s.transaction_source,
        }

    frame = apply_sort(apply_filters(s.filtered, p), p.sort, p.order)
    page_slice, total = paginate(frame, p.page, p.page_size)
    total_pages = ceil(total / p.page_size) if total else 0
    return {
        "ready": True,
        "total": total,
        "page": p.page,
        "page_size": p.page_size,
        "total_pages": total_pages,
        "sort": _sort_meta(p),
        "rows": records(page_slice, _RAW_COLUMNS, date_columns=_DATE_COLUMNS),
        "columns": _COLUMN_META,
        "source": s.transaction_source,
    }


@router.get("/export.csv")
def raw_export_csv(
    s: Slice = Depends(get_slice),
    p: RawParams = Depends(raw_params),
    _user: str = Depends(require_auth),
) -> StreamingResponse:
    """The full filtered+sorted set as CSV (pagination ignored), matching the
    Streamlit ``_download_bytes(_raw_base)`` export."""
    frame = apply_sort(apply_filters(s.filtered, p), p.sort, p.order)
    present = [c for c in _RAW_COLUMNS if c in frame.columns]
    buffer = io.BytesIO()
    frame[present].to_csv(buffer, index=False)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="congress_transactions_filtered.csv"'
        },
    )
