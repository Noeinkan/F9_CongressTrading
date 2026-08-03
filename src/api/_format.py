"""Currency and percentage formatting helpers for API responses."""
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


_RANGE_EPS = 0.5


def _as_float(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_cumulative_net_label(value: object) -> str:
    """Running net total for cumulative exposure charts ($0 net, -$4.2K net)."""
    v = _as_float(value)
    if v is None:
        return "— net"
    if abs(v) < _RANGE_EPS:
        return "$0 net"
    compact = format_currency_compact(v)
    if compact == "—":
        return "$0 net"
    return f"{compact} net"


def format_cumulative_range_label(median: object, low: object, high: object) -> str:
    """End-of-line label that surfaces midpoint uncertainty.

    Collapsed range → same as :func:`format_cumulative_net_label`.
    Wide range → ``~$95.0K (range $1.0K – $15.0K)``.
    """
    med_v = _as_float(median)
    lo_v = _as_float(low)
    hi_v = _as_float(high)
    if med_v is None:
        return "— net"
    if lo_v is None or hi_v is None or abs(hi_v - lo_v) < _RANGE_EPS:
        return format_cumulative_net_label(med_v)

    med_s = format_currency_compact(med_v)
    if med_s == "—" or abs(med_v) < _RANGE_EPS:
        med_s = "$0"
    lo_s = format_currency_compact(lo_v)
    hi_s = format_currency_compact(hi_v)
    if lo_s == "—":
        lo_s = "$0"
    if hi_s == "—":
        hi_s = "$0"
    return f"~{med_s} (range {lo_s} – {hi_s})"


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
    """Attach a formatted ``disclosed_range`` string column. Pure port of the
    helper in ``dashboard_shared.formatting`` (Streamlit column configs not
    included — that lives in the dashboard, not here)."""
    out = frame.copy()
    low = pd.to_numeric(out.get(low_col), errors="coerce")
    high = pd.to_numeric(out.get(high_col), errors="coerce")
    out["disclosed_range"] = [
        format_disclosed_range(l, h) for l, h in zip(low, high, strict=True)
    ]
    return out
