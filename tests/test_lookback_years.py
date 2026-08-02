"""Lookback year selection — keep lagged transaction dates visible."""
from __future__ import annotations

from datetime import date as real_date

from src.api.repository import lookback_years


def test_lookback_one_year_includes_current_calendar_year():
    years = [2024, 2025, 2026]
    current = real_date.today().year
    assert lookback_years(years, 1) == [y for y in years if y >= current]


def test_lookback_falls_back_when_window_is_ahead_of_data(monkeypatch):
    """Only 2025 dates exist; in 2026 lookback=1 must not return []."""

    class _FixedDate:
        @staticmethod
        def today():
            return real_date(2026, 8, 2)

    monkeypatch.setattr("src.api.repository.date", _FixedDate)
    assert lookback_years([2025], 1) == [2025]
    assert lookback_years([2024, 2025], 1) == [2025]
    # lookback=2 in 2026 → cutoff 2025, so only 2025 from this set
    assert lookback_years([2024, 2025], 2) == [2025]
    assert lookback_years([2023, 2024], 2) == [2023, 2024]


def test_lookback_none_returns_all():
    assert lookback_years([2023, 2025], None) == [2023, 2025]
