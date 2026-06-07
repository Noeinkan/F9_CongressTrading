from __future__ import annotations

import pandas as pd

from .components import _copy

_QUARTER_OPTIONS: tuple[int, ...] = (1, 2, 3, 4)


def _available_years(data: pd.DataFrame) -> list[int]:
    if "transaction_date" not in data.columns:
        return []
    dates = pd.to_datetime(data["transaction_date"], errors="coerce").dropna()
    if dates.empty:
        return []
    return sorted(int(y) for y in dates.dt.year.unique())


def _year_range_selection(
    years_available: list[int],
    year_from: int,
    year_to: int,
) -> list[int]:
    """Inclusive calendar-year range over available years (order-independent)."""
    lo, hi = min(year_from, year_to), max(year_from, year_to)
    return [y for y in years_available if lo <= y <= hi]


def _apply_period_filter(
    data: pd.DataFrame,
    *,
    selected_years: list[int] | None,
    selected_quarters: list[int] | None,
    all_years: list[int],
    all_quarters: tuple[int, ...] = _QUARTER_OPTIONS,
) -> pd.DataFrame:
    """Keep rows whose transaction_date falls in selected calendar years and quarters."""
    if data.empty or "transaction_date" not in data.columns:
        return data

    years_sel = list(selected_years or [])
    quarters_sel = list(selected_quarters or [])
    if not years_sel or not quarters_sel:
        return data.iloc[0:0].copy()

    if set(years_sel) >= set(all_years) and set(quarters_sel) >= set(all_quarters):
        return data

    dated = data.dropna(subset=["transaction_date"]).copy()
    if dated.empty:
        return dated

    tx_dates = pd.to_datetime(dated["transaction_date"], errors="coerce")
    mask = tx_dates.dt.year.isin(years_sel) & tx_dates.dt.quarter.isin(quarters_sel)
    return dated.loc[mask].copy()


_LOOKBACK_OPTIONS: list[tuple[str, int | None]] = [
    ("All time", None),
    ("Last 1 year", 1),
    ("Last 2 years", 2),
    ("Last 3 years", 3),
    ("Last 5 years", 5),
    ("Last 10 years", 10),
]


def _lookback_years(data: pd.DataFrame, n_years: int | None, years_available: list[int]) -> list[int]:
    """Return the list of calendar years included for a given lookback window."""
    if n_years is None:
        return years_available
    from datetime import date
    current_year = date.today().year
    cutoff_year = current_year - n_years + 1
    return [y for y in years_available if y >= cutoff_year]


def render_period_slicers_and_filter(data: pd.DataFrame) -> pd.DataFrame:
    """Apply period lookback + quarter filters (sidebar UI)."""
    from .top_bar import render_sidebar_period_slicer

    return render_sidebar_period_slicer(data)

