from __future__ import annotations

import pandas as pd

from src.dashboard_shared.kpi_sparklines import (
    build_slice_kpi_sparklines,
    month_over_month_delta,
    monthly_series,
)


def _sample() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "member": ["A", "A", "B"],
            "ticker": ["X", "Y", "X"],
            "transaction_date": pd.to_datetime(
                ["2024-01-15", "2024-02-10", "2024-02-20"]
            ),
            "amount_high": [10_000.0, 20_000.0, 5_000.0],
            "month": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-02-01"]),
        }
    )


def test_monthly_series_transactions():
    vals = monthly_series(_sample(), "transactions")
    assert len(vals) >= 2
    assert vals[-1] == 2.0


def test_build_slice_kpi_sparklines_keys():
    spark = build_slice_kpi_sparklines(_sample())
    assert set(spark.keys()) == {
        "transactions",
        "members",
        "tickers",
        "open_reviews",
        "disclosed_amount_high",
    }


def test_month_over_month_delta():
    assert month_over_month_delta([1.0, 4.0]) == "+3 vs prior month"
    assert month_over_month_delta([10.0, 15.0], percent=True) == "+50% vs prior month"
