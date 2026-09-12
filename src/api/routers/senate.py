"""Senate page route.

The overview half of the payload is ``/api/home/summary`` computed on the
Senate slice — same KPIs, charts and leaderboards — so the Senate page and the
Home page can never disagree about a figure. The Senate-specific half (filing
timeliness, the filings list, coverage) comes from
:mod:`src.api._senate_analytics`.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from fastapi import APIRouter, Depends

from .. import repository
from .._senate_analytics import (
    filing_list,
    filing_timeliness,
    senate_coverage,
    senate_rows,
)
from ..query import Slice, get_slice
from ..security import require_auth
from .home import home_summary

router = APIRouter(prefix="/api/senate", tags=["senate"])


@router.get("/summary")
def senate_summary(
    s: Slice = Depends(get_slice),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """Everything the Senate page renders, for the active period slice."""
    senate = senate_rows(s.filtered)
    scoped = replace(
        s,
        filtered=senate,
        review=repository.filter_review_to_slice(s.review, senate),
    )
    # All-time count, so the page can tell "nothing ingested yet" apart from
    # "nothing in the selected period".
    all_time = senate_rows(s.transactions) if s.ready else senate
    return {
        **home_summary(scoped, _user),
        "senate_rows_all_time": int(len(all_time)),
        "coverage": senate_coverage(senate),
        "timeliness": filing_timeliness(senate),
        "filings": filing_list(senate),
    }
