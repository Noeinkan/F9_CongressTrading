"""Analytics helpers for the Executive (OGE 278-T / 278e) dashboard page.

Pure pandas functions that operate on a ``chamber == "Executive"`` frame
loaded via :func:`src.api.repository._prepare_transactions`. Mirrors the
``_home_analytics`` module's style — no HTTP, no Streamlit, no I/O.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def compute_executive_summary(transactions_df: pd.DataFrame) -> dict[str, Any]:
    """Header-card stats for the Executive page.

    Returns a JSON-safe dict with counts and a few KPIs. Safe on empty frames.
    """
    if transactions_df.empty:
        return {
            "ready": False,
            "transaction_count": 0,
            "filer_count": 0,
            "filing_count": 0,
            "asset_count": 0,
            "buy_count": 0,
            "sell_count": 0,
            "exchange_count": 0,
            "amount_high_total": 0.0,
            "amount_high_label": "—",
            "date_min": None,
            "date_max": None,
        }

    filer_count = (
        int(transactions_df["member"].astype(str).nunique())
        if "member" in transactions_df.columns
        else 0
    )
    filing_count = (
        int(transactions_df["filing_type"].astype(str).nunique())
        if "filing_type" in transactions_df.columns
        else 0
    )
    # If we have a filing_id column we prefer counting distinct filings, so
    # multiple transactions on the same filing still count as one filing.
    if "filing_id" in transactions_df.columns:
        distinct_filings = transactions_df["filing_id"].astype("Int64").nunique(dropna=True)
        if distinct_filings and not pd.isna(distinct_filings):
            filing_count = int(distinct_filings)
    asset_count = (
        int(transactions_df["asset_name_raw"].astype(str).nunique())
        if "asset_name_raw" in transactions_df.columns
        else 0
    )

    tx_type = transactions_df.get("transaction_type", pd.Series([], dtype=object)).astype(str).str.upper()
    buy_count = int(((tx_type == "P") | tx_type.str.contains("BUY", na=False)).sum())
    sell_count = int(((tx_type == "S") | tx_type.str.contains("SELL", na=False)).sum())
    exchange_count = int(((tx_type == "E") | tx_type.str.contains("EXCHANGE", na=False)).sum())

    amount_high = pd.to_numeric(transactions_df.get("amount_high", 0), errors="coerce").fillna(0.0)
    amount_high_total = float(amount_high.sum())

    if "transaction_date" in transactions_df.columns:
        dates = pd.to_datetime(transactions_df["transaction_date"], errors="coerce").dropna()
        date_min = dates.min().strftime("%Y-%m-%d") if not dates.empty else None
        date_max = dates.max().strftime("%Y-%m-%d") if not dates.empty else None
    else:
        date_min = None
        date_max = None

    return {
        "ready": True,
        "transaction_count": _safe_int(len(transactions_df)),
        "filer_count": filer_count,
        "filing_count": filing_count,
        "asset_count": asset_count,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "exchange_count": exchange_count,
        "amount_high_total": amount_high_total,
        "amount_high_label": _format_compact(amount_high_total),
        "date_min": date_min,
        "date_max": date_max,
    }


def compute_monthly_timeline(transactions_df: pd.DataFrame) -> list[dict[str, Any]]:
    """Per-month transaction counts for the active Executive slice.

    Returns ``[{month: 'YYYY-MM-DD', count: int, ...}, ...]`` sorted ascending.
    Empty list when there are no dated transactions.
    """
    if transactions_df.empty or "transaction_date" not in transactions_df.columns:
        return []
    work = transactions_df.copy()
    work["transaction_date"] = pd.to_datetime(work["transaction_date"], errors="coerce")
    work = work.dropna(subset=["transaction_date"])
    if work.empty:
        return []
    work["month"] = work["transaction_date"].dt.to_period("M").dt.to_timestamp()
    agg = work.groupby("month").size().reset_index(name="count").sort_values("month")
    return [
        {"month": row["month"].strftime("%Y-%m-%d"), "count": int(row["count"])}
        for _, row in agg.iterrows()
    ]


def compute_by_owner_type(transactions_df: pd.DataFrame) -> dict[str, Any]:
    """Transaction counts (and amount totals) per owner_type for Executive rows.

    Returns ``{owner_type: {count, amount_high_total, amount_high_label}}``.
    Falls back to ``{"filer": ...}`` when the column is missing so callers
    don't have to special-case empty data.
    """
    if transactions_df.empty or "owner_type" not in transactions_df.columns:
        return {}
    work = transactions_df.copy()
    work["owner_type"] = work["owner_type"].fillna("filer").astype(str).str.strip().str.lower()
    work.loc[work["owner_type"] == "", "owner_type"] = "filer"
    amount_high = pd.to_numeric(work.get("amount_high", 0), errors="coerce").fillna(0.0)
    work["_amount_high"] = amount_high
    agg = work.groupby("owner_type", as_index=False).agg(
        count=("owner_type", "size"),
        amount_high_total=("_amount_high", "sum"),
    )
    out: dict[str, Any] = {}
    for _, row in agg.iterrows():
        owner = str(row["owner_type"]) or "filer"
        total = float(row["amount_high_total"])
        out[owner] = {
            "count": int(row["count"]),
            "amount_high_total": total,
            "amount_high_label": _format_compact(total),
        }
    return out


def _format_compact(value: float) -> str:
    """Abbreviated dollar amount for KPI labels (mirrors ``_format.format_currency_compact``)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if abs(v) < 0.5:
        return "—"
    abs_v = abs(v)
    sign = "-" if v < 0 else ""
    if abs_v >= 1_000_000_000:
        return f"{sign}${abs_v / 1_000_000_000:.1f}B"
    if abs_v >= 1_000_000:
        return f"{sign}${abs_v / 1_000_000:.1f}M"
    if abs_v >= 1_000:
        return f"{sign}${abs_v / 1_000:.1f}K"
    return f"{sign}${abs_v:,.0f}"