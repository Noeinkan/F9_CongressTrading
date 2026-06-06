"""Tests for src.dashboard_shared.filters — verifies the period-filter logic
narrows data correctly. The dashboard sidebar was removed; global filtering is
driven by the top-bar period slicer only."""
from __future__ import annotations

import pandas as pd


# ---------------------------------------------------------------------------
# Sample data shared across tests
# ---------------------------------------------------------------------------
def _sample_transactions() -> pd.DataFrame:
    rows = [
        {
            "member": "Alice Smith",
            "chamber": "House",
            "party": "D",
            "state": "CA",
            "ticker": "AAPL",
            "transaction_type": "P",
            "transaction_date": pd.Timestamp("2024-06-01"),
            "filing_date": pd.Timestamp("2024-06-15"),
            "asset_type": "Stock",
            "asset_name_raw": "Apple Inc",
            "asset_name_normalized": "Apple Inc",
            "issuer_name": "Apple",
            "amount_low": 10_000,
            "amount_high": 20_000,
            "amount_range_raw": "10k-20k",
            "confidence_score": 0.95,
            "review_status": "resolved",
        },
        {
            "member": "Bob Jones",
            "chamber": "Senate",
            "party": "R",
            "state": "TX",
            "ticker": "MSFT",
            "transaction_type": "S",
            "transaction_date": pd.Timestamp("2024-07-10"),
            "filing_date": pd.Timestamp("2024-07-20"),
            "asset_type": "Stock",
            "asset_name_raw": "Microsoft Corp",
            "asset_name_normalized": "Microsoft Corp",
            "issuer_name": "Microsoft",
            "amount_low": 30_000,
            "amount_high": 70_000,
            "amount_range_raw": "30k-70k",
            "confidence_score": 0.40,
            "review_status": "needs_review",
        },
        {
            "member": "Alice Smith",
            "chamber": "House",
            "party": "D",
            "state": "CA",
            "ticker": "",
            "transaction_type": "P",
            "transaction_date": pd.Timestamp("2024-08-01"),
            "filing_date": pd.Timestamp("2024-08-10"),
            "asset_type": "Other",
            "asset_name_raw": "Private Fund X",
            "asset_name_normalized": "Private Fund X",
            "issuer_name": "",
            "amount_low": 1_000,
            "amount_high": 9_000,
            "amount_range_raw": "1k-9k",
            "confidence_score": 0.20,
            "review_status": "needs_review",
        },
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Period slicer — the only global filter on the dashboard
# ---------------------------------------------------------------------------

class TestPeriodFilter:
    def test_all_years_and_quarters_returns_full_dataset(self):
        data = _sample_transactions()
        from src.dashboard_shared.filters import _apply_period_filter, _available_years

        years = _available_years(data)
        result = _apply_period_filter(
            data,
            selected_years=years,
            selected_quarters=[1, 2, 3, 4],
            all_years=years,
        )
        assert len(result) == len(data)

    def test_single_quarter_narrows_rows(self):
        data = _sample_transactions()
        from src.dashboard_shared.filters import _apply_period_filter, _available_years

        years = _available_years(data)
        result = _apply_period_filter(
            data,
            selected_years=years,
            selected_quarters=[2],
            all_years=years,
        )
        assert len(result) == 1
        assert result.iloc[0]["member"] == "Alice Smith"

    def test_single_year_narrows_rows(self):
        data = _sample_transactions()
        from src.dashboard_shared.filters import _apply_period_filter

        result = _apply_period_filter(
            data,
            selected_years=[2024],
            selected_quarters=[1, 2, 3, 4],
            all_years=[2024],
        )
        assert len(result) == len(data)

    def test_empty_year_selection_returns_no_rows(self):
        data = _sample_transactions()
        from src.dashboard_shared.filters import _apply_period_filter, _available_years

        years = _available_years(data)
        result = _apply_period_filter(
            data,
            selected_years=[],
            selected_quarters=[1, 2, 3, 4],
            all_years=years,
        )
        assert result.empty

    def test_year_range_selection_inclusive_and_order_independent(self):
        from src.dashboard_shared.filters import _year_range_selection

        years = [2019, 2020, 2021, 2022, 2024]
        assert _year_range_selection(years, 2022, 2020) == [2020, 2021, 2022]
        assert _year_range_selection(years, 2024, 2024) == [2024]
        assert _year_range_selection(years, 2018, 2025) == years
