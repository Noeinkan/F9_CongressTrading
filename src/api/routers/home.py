"""Home page route: KPIs, sparklines, latest activity, and overview rollups.

Reproduces the analytics surface of ``src/dashboard_pages/home.py`` and
``dashboard_shared.session.render_slice_hero_and_kpis`` as plain JSON. Charts
are returned as raw aggregates; the frontend renders them.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends

from .._sparklines import build_slice_kpi_sparklines, month_over_month_delta
from .._format import (
    format_currency_full,
    format_disclosed_range,
    format_percent,
    sum_amount_high,
    sum_amount_low,
)
from ..query import Slice, get_slice
from ..security import require_auth
from ..serialize import iso_date, records

router = APIRouter(prefix="/api/home", tags=["home"])

_LATEST_COLUMNS = [
    "member",
    "chamber",
    "party",
    "ticker",
    "transaction_type_label",
    "transaction_date",
    "amount_range_raw",
    "filing_date",
    "disclosure_url",
]


def _hero(s: Slice) -> dict[str, Any]:
    filtered = s.filtered
    total_transactions = int(len(filtered))
    total_members = int(filtered["member"].nunique()) if total_transactions else 0
    tracked_tickers = (
        int(filtered.loc[filtered["ticker"] != "", "ticker"].nunique()) if total_transactions else 0
    )
    open_reviews = int((s.review["status"] == "open").sum()) if not s.review.empty else 0
    amount_low_total = sum_amount_low(filtered)
    amount_high_total = sum_amount_high(filtered)
    avg_confidence = float(filtered["confidence_score"].mean()) if total_transactions else 0.0
    active_chambers = (
        ", ".join(sorted(filtered["chamber"].dropna().astype(str).unique()))
        if total_transactions
        else ""
    )
    coverage_min = filtered["transaction_date"].min() if total_transactions else None
    coverage_max = filtered["transaction_date"].max() if total_transactions else None
    latest_filing = filtered["filing_date"].max() if total_transactions else None
    return {
        "transaction_source": s.transaction_source,
        "review_source": s.review_source,
        "total_transactions": total_transactions,
        "total_members": total_members,
        "tracked_tickers": tracked_tickers,
        "open_reviews": open_reviews,
        "avg_confidence": avg_confidence,
        "avg_confidence_label": format_percent(avg_confidence),
        "active_chambers": active_chambers,
        "amount_low_total": amount_low_total,
        "amount_high_total": amount_high_total,
        "disclosed_range": format_disclosed_range(amount_low_total, amount_high_total),
        "coverage_from": iso_date(coverage_min),
        "coverage_to": iso_date(coverage_max),
        "latest_filing": iso_date(latest_filing),
    }


def _kpis(s: Slice, hero: dict[str, Any]) -> list[dict[str, Any]]:
    spark = build_slice_kpi_sparklines(s.filtered, s.review)
    return [
        {
            "key": "transactions",
            "label": "Transactions",
            "value": hero["total_transactions"],
            "detail": "Rows in the active filter slice",
            "sparkline": spark.get("transactions") or [],
            "delta": month_over_month_delta(spark.get("transactions") or []),
        },
        {
            "key": "members",
            "label": "Members",
            "value": hero["total_members"],
            "detail": "Distinct filers in the slice",
            "sparkline": spark.get("members") or [],
            "delta": month_over_month_delta(spark.get("members") or []),
        },
        {
            "key": "tickers",
            "label": "Tickers",
            "value": hero["tracked_tickers"],
            "detail": "Resolved symbols in the slice",
            "sparkline": spark.get("tickers") or [],
            "delta": month_over_month_delta(spark.get("tickers") or []),
        },
        {
            "key": "open_reviews",
            "label": "Open reviews",
            "value": hero["open_reviews"],
            "detail": "Queue items still needing validation",
            "sparkline": spark.get("open_reviews") or [],
            "delta": month_over_month_delta(spark.get("open_reviews") or []),
        },
        {
            "key": "disclosed_range",
            "label": "Disclosed range",
            "value": hero["disclosed_range"],
            "detail": (
                f"{format_currency_full(hero['amount_low_total'])} low · "
                f"{format_currency_full(hero['amount_high_total'])} high · "
                f"{hero['avg_confidence_label']} avg confidence"
            ),
            "sparkline": spark.get("disclosed_amount_high") or [],
            "delta": month_over_month_delta(
                spark.get("disclosed_amount_high") or [], percent=True
            ),
        },
    ]


def _breakdown(filtered: pd.DataFrame) -> dict[str, Any]:
    if filtered.empty:
        return {"by_chamber": [], "by_type": []}
    by_chamber = (
        filtered.groupby("chamber", as_index=False)
        .size()
        .rename(columns={"size": "transactions"})
        .sort_values("transactions", ascending=False)
    )
    by_type = (
        filtered.groupby("transaction_type_label", as_index=False)
        .size()
        .rename(columns={"size": "transactions"})
        .sort_values("transactions", ascending=False)
    )
    return {
        "by_chamber": records(by_chamber, ["chamber", "transactions"]),
        "by_type": records(by_type, ["transaction_type_label", "transactions"]),
    }


def _monthly_activity(filtered: pd.DataFrame) -> list[dict[str, Any]]:
    if filtered.empty:
        return []
    monthly = (
        filtered.dropna(subset=["month"])
        .groupby("month", as_index=False)
        .agg(
            transactions=("member", "size"),
            amount_low=("amount_low", "sum"),
            amount_high=("amount_high", "sum"),
        )
        .sort_values("month")
    )
    return records(monthly, ["month", "transactions", "amount_low", "amount_high"], date_columns=("month",))


def _top(filtered: pd.DataFrame, key: str) -> list[dict[str, Any]]:
    if filtered.empty:
        return []
    frame = filtered
    if key == "ticker":
        frame = filtered.loc[filtered["ticker"] != ""]
    if frame.empty:
        return []
    agg = (
        frame.groupby(key, as_index=False)
        .agg(
            transactions=(key, "size"),
            amount_low=("amount_low", "sum"),
            amount_high=("amount_high", "sum"),
        )
        .sort_values(["transactions", "amount_high"], ascending=[False, False])
        .head(10)
    )
    agg["disclosed_range"] = [
        format_disclosed_range(lo, hi)
        for lo, hi in zip(agg["amount_low"], agg["amount_high"], strict=True)
    ]
    return records(agg, [key, "transactions", "amount_low", "amount_high", "disclosed_range"])


@router.get("/summary")
def home_summary(
    s: Slice = Depends(get_slice),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
    """All data needed to render the Home page for the current period slice."""
    if not s.ready:
        return {
            "ready": False,
            "hero": _hero(s),
            "kpis": [],
            "latest_transactions": [],
            "breakdown": {"by_chamber": [], "by_type": []},
            "monthly_activity": [],
            "top_members": [],
            "top_tickers": [],
        }

    hero = _hero(s)
    latest = s.filtered.head(30)
    return {
        "ready": True,
        "hero": hero,
        "kpis": _kpis(s, hero),
        "latest_transactions": records(
            latest, _LATEST_COLUMNS, date_columns=("transaction_date", "filing_date")
        ),
        "breakdown": _breakdown(s.filtered),
        "monthly_activity": _monthly_activity(s.filtered),
        "top_members": _top(s.filtered, "member"),
        "top_tickers": _top(s.filtered, "ticker"),
    }
