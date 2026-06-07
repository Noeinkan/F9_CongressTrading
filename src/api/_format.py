"""Pure currency / percentage formatting helpers (no Streamlit).

These are byte-for-byte copies of the pure functions in
``src.dashboard_shared.formatting``. That module cannot be imported here
because it builds ``st.column_config`` objects at import time, which would
pull Streamlit into the API layer. At cutover, the Streamlit column-config
block is deleted and this file becomes the single source.
"""
from __future__ import annotations

import pandas as pd


def format_percent(value: object, *, decimals: int = 0) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        return f"{float(value):.{decimals}%}"
    except (TypeError, ValueError):
        return "—"


def format_currency_full(value: object) -> str:
    """Full-precision dollars ($12,345)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if v == 0:
        return "—"
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.0f}"


def format_currency_compact(value: object) -> str:
    """Abbreviated currency for KPIs and chart labels ($12.5K, -$1.3M)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if v == 0:
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


def format_disclosed_range(low: object, high: object) -> str:
    """Human-readable disclosure bucket, e.g. $1.0K – $15.0K."""
    lo = format_currency_compact(low)
    hi = format_currency_compact(high)
    if lo == "—" and hi == "—":
        return "—"
    if lo == "—":
        return hi
    if hi == "—":
        return lo
    return f"{lo} – {hi}"


def sum_amount_low(frame: pd.DataFrame) -> float:
    return float(pd.to_numeric(frame.get("amount_low"), errors="coerce").sum(skipna=True))


def sum_amount_high(frame: pd.DataFrame) -> float:
    return float(pd.to_numeric(frame.get("amount_high"), errors="coerce").sum(skipna=True))
