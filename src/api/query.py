"""Shared request-parsing helpers reused by every page route.

Parses the period filter (``lookback`` years + ``quarters``) that the Streamlit
sidebar applied globally, loads the dataset, and returns the filtered slice plus
the review queue restricted to that slice.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from fastapi import Depends, Query

from . import repository


@dataclass(frozen=True)
class PeriodParams:
    lookback: int | None
    quarters: list[int] | None


def period_params(
    lookback: int | None = Query(
        None,
        ge=0,
        description="Lookback window in years (0 or omit for all time).",
    ),
    quarters: str | None = Query(
        None,
        description="Comma-separated quarters to include, e.g. '1,2'. Omit for all quarters.",
    ),
) -> PeriodParams:
    parsed: list[int] | None = None
    if quarters:
        parsed = [int(x) for x in quarters.split(",") if x.strip().isdigit() and 1 <= int(x) <= 4]
        parsed = parsed or None
    # Frontend sends lookback=0 for "All time"; treat 0 like omit (None).
    normalized_lookback = None if lookback in (None, 0) else lookback
    return PeriodParams(lookback=normalized_lookback, quarters=parsed)


@dataclass
class Slice:
    transactions: pd.DataFrame  # full (unfiltered) dataset
    filtered: pd.DataFrame  # period-filtered transactions
    review: pd.DataFrame  # review queue restricted to the filtered slice
    transaction_source: str
    review_source: str
    ready: bool
    lookback: int | None = None  # period filter as requested by the client
    quarters: list[int] | None = None


def get_slice(period: PeriodParams = Depends(period_params)) -> Slice:
    """Load the dataset and apply the period filter (the per-request entrypoint)."""
    ctx = repository.load_dataset()
    transactions: pd.DataFrame = ctx["transactions"]  # type: ignore[assignment]
    review: pd.DataFrame = ctx["review"]  # type: ignore[assignment]
    filtered = repository.filter_by_lookback(
        transactions, lookback=period.lookback, quarters=period.quarters
    )
    review_slice = repository.filter_review_to_slice(review, filtered)
    return Slice(
        transactions=transactions,
        filtered=filtered,
        review=review_slice,
        transaction_source=str(ctx["transaction_source"]),
        review_source=str(ctx["review_source"]),
        ready=bool(ctx["ready"]),
        lookback=period.lookback,
        quarters=list(period.quarters) if period.quarters else None,
    )
