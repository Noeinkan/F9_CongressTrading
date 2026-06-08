"""KPI sparkline aggregation for API responses."""
from __future__ import annotations

from typing import Literal

import pandas as pd

SparklineMetric = Literal[
    "transactions",
    "members",
    "tickers",
    "open_reviews",
    "disclosed_amount_high",
]


def _ensure_month(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    if "month" not in work.columns:
        work["month"] = (
            pd.to_datetime(work["transaction_date"], errors="coerce").dt.to_period("M").dt.to_timestamp()
        )
    return work.dropna(subset=["month"])


def monthly_series(
    frame: pd.DataFrame,
    metric: SparklineMetric,
    *,
    review: pd.DataFrame | None = None,
    max_months: int = 14,
) -> list[float]:
    """Last N calendar months of values for KPI sparklines (oldest → newest)."""
    if frame.empty and metric != "open_reviews":
        return []
    months = _ensure_month(frame) if not frame.empty else pd.DataFrame()

    if metric == "transactions":
        if months.empty:
            return []
        agg = months.groupby("month").size().reset_index(name="value")
    elif metric == "members":
        if months.empty:
            return []
        agg = months.groupby("month")["member"].nunique().reset_index(name="value")
    elif metric == "tickers":
        if months.empty:
            return []
        tick = months[months["ticker"].astype(str).str.strip() != ""]
        if tick.empty:
            return []
        agg = tick.groupby("month")["ticker"].nunique().reset_index(name="value")
    elif metric == "disclosed_amount_high":
        if months.empty:
            return []
        months = months.copy()
        months["_amount_high"] = pd.to_numeric(months["amount_high"], errors="coerce")
        agg = months.groupby("month")["_amount_high"].sum(min_count=1).reset_index(name="value")
    elif metric == "open_reviews":
        rev = review if review is not None else pd.DataFrame()
        if rev.empty:
            return []
        rev = rev.copy()
        rev["month"] = pd.to_datetime(rev["transaction_date"], errors="coerce").dt.to_period("M").dt.to_timestamp()
        rev = rev.dropna(subset=["month"])
        if rev.empty:
            return []
        open_mask = rev["status"].astype(str).str.strip().str.lower() == "open"
        agg = rev.loc[open_mask].groupby("month").size().reset_index(name="value")
    else:
        return []

    if agg.empty:
        return []

    agg = agg.sort_values("month").tail(max_months)
    vals = [float(v) for v in pd.to_numeric(agg["value"], errors="coerce").fillna(0.0)]
    if len(vals) == 1:
        vals = [vals[0], vals[0]]
    return vals


def build_slice_kpi_sparklines(
    transactions: pd.DataFrame,
    review: pd.DataFrame | None = None,
    *,
    max_months: int = 14,
) -> dict[str, list[float]]:
    metrics: list[SparklineMetric] = [
        "transactions",
        "members",
        "tickers",
        "open_reviews",
        "disclosed_amount_high",
    ]
    return {m: monthly_series(transactions, m, review=review, max_months=max_months) for m in metrics}


def month_over_month_delta(values: list[float], *, percent: bool = False) -> str | None:
    if len(values) < 2:
        return None
    last, prev = float(values[-1]), float(values[-2])
    diff = last - prev
    if diff == 0:
        return "Flat vs prior month"
    if percent and prev != 0:
        pct = 100.0 * diff / abs(prev)
        sign = "+" if pct > 0 else ""
        return f"{sign}{pct:.0f}% vs prior month"
    sign = "+" if diff > 0 else ""
    if abs(diff) >= 1000:
        return f"{sign}{diff:,.0f} vs prior month"
    if float(int(diff)) == diff:
        return f"{sign}{int(diff)} vs prior month"
    return f"{sign}{diff:.1f} vs prior month"
