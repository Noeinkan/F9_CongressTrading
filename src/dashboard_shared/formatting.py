from __future__ import annotations

import pandas as pd
import streamlit as st


def format_count(value: object) -> str:
    """Integer counts with thousands separators (e.g. 12,345)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return "—"


def format_percent(value: object, *, decimals: int = 0) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        return f"{float(value):.{decimals}%}"
    except (TypeError, ValueError):
        return "—"


def format_currency_full(value: object) -> str:
    """Full-precision dollars for tooltips and detail lines ($12,345)."""
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


def format_cumulative_net_label(value: object) -> str:
    """Running net total for cumulative exposure charts ($0 net, -$4.2K net)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "— net"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "— net"
    if abs(v) < 0.5:
        return "$0 net"
    compact = format_currency_compact(v)
    if compact == "—":
        return "$0 net"
    return f"{compact} net"


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


def add_disclosed_range_column(
    frame: pd.DataFrame,
    *,
    low_col: str = "amount_low_sum",
    high_col: str = "amount_high_sum",
) -> pd.DataFrame:
    out = frame.copy()
    low = pd.to_numeric(out.get(low_col), errors="coerce")
    high = pd.to_numeric(out.get(high_col), errors="coerce")
    out["disclosed_range"] = [
        format_disclosed_range(l, h) for l, h in zip(low, high, strict=True)
    ]
    return out


# Shared Streamlit dataframe column configs (consistent labels + formats site-wide).
COL_TRADES = st.column_config.NumberColumn("Trades", format="%d", help="Disclosure rows in the slice")
COL_UNIQUE_TICKERS = st.column_config.NumberColumn(
    "Unique tickers", format="%d", help="Distinct resolved symbols"
)
COL_DISCLOSED_RANGE = st.column_config.TextColumn(
    "Disclosed range",
    help="Sum of amount_low – sum of amount_high for rows in the slice (not exact market value)",
)
COL_DATE = st.column_config.DateColumn("Date", format="YYYY-MM-DD")
COL_FIRST_TRADE = st.column_config.DateColumn("First trade", format="YYYY-MM-DD")
COL_LAST_TRADE = st.column_config.DateColumn("Last trade", format="YYYY-MM-DD")
COL_AMOUNT_LOW = st.column_config.NumberColumn("Amount low", format="$%d")
COL_AMOUNT_HIGH = st.column_config.NumberColumn("Amount high", format="$%d")
COL_RECENT_DISCLOSURES = st.column_config.NumberColumn(
    "Recent disclosures",
    format="%d",
    help="PTR disclosure rows for this ticker in the lookback window",
)
COL_DISCLOSURES_PER_MONTH = st.column_config.NumberColumn(
    "Per month",
    format="%.2f",
    help="Average PTR disclosures per month",
)
COL_SPIKE_RATIO = st.column_config.NumberColumn(
    "Spike ratio",
    format="%.2f",
    help="Recent monthly rate ÷ prior monthly rate (≥2 flags a spike; with no prior history, equals recent count)",
)
