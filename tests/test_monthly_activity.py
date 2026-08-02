"""Unit tests for Home / Executive monthly activity rollups."""
from __future__ import annotations

import pandas as pd

from src.api._executive_analytics import compute_monthly_timeline
from src.api._home_analytics import monthly_activity_rows


def _row(
    *,
    transaction_date: str,
    transaction_type: str,
    amount_low: float = 1_000.0,
    amount_high: float = 15_000.0,
) -> dict:
    ts = pd.Timestamp(transaction_date)
    return {
        "month": ts.to_period("M").to_timestamp(),
        "transaction_date": ts,
        "transaction_type": transaction_type,
        "amount_low": amount_low,
        "amount_high": amount_high,
        "member": "Alice",
    }


def test_monthly_activity_splits_buy_sell_other_and_sums_amounts():
    frame = pd.DataFrame(
        [
            _row(transaction_date="2024-01-10", transaction_type="P", amount_low=1_000, amount_high=15_000),
            _row(transaction_date="2024-01-20", transaction_type="S", amount_low=15_001, amount_high=50_000),
            _row(transaction_date="2024-01-25", transaction_type="E", amount_low=1_001, amount_high=15_000),
            _row(transaction_date="2024-02-05", transaction_type="P (Buy)", amount_low=50_001, amount_high=100_000),
        ]
    )
    rows = monthly_activity_rows(frame)
    assert len(rows) == 2

    jan = rows[0]
    assert jan["month"] == "2024-01-01"
    assert jan["transactions"] == 3
    assert jan["buy"] == 1
    assert jan["sell"] == 1
    assert jan["other"] == 1
    assert jan["amount_low"] == 1_000 + 15_001 + 1_001
    assert jan["amount_high"] == 15_000 + 50_000 + 15_000

    feb = rows[1]
    assert feb["month"] == "2024-02-01"
    assert feb["transactions"] == 1
    assert feb["buy"] == 1
    assert feb["sell"] == 0
    assert feb["other"] == 0


def test_monthly_activity_empty_frame():
    assert monthly_activity_rows(pd.DataFrame()) == []


def test_executive_monthly_timeline_includes_count_alias():
    frame = pd.DataFrame(
        [
            _row(transaction_date="2024-07-30", transaction_type="P", amount_low=50_001, amount_high=100_000),
            _row(transaction_date="2024-07-15", transaction_type="S", amount_low=1_001, amount_high=15_000),
        ]
    )
    rows = compute_monthly_timeline(frame)
    assert len(rows) == 1
    row = rows[0]
    assert row["count"] == 2
    assert row["transactions"] == 2
    assert row["buy"] == 1
    assert row["sell"] == 1
    assert row["amount_high"] == 115_000
