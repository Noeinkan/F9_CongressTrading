"""Unit tests for ticker cumulative exposure floor/ceiling bands."""
from __future__ import annotations

import pandas as pd

from src.api._format import format_cumulative_range_label
from src.api._tickers_analytics import ticker_cumulative_exposure_payload


def _trade(
    *,
    member: str,
    transaction_date: str,
    transaction_type: str,
    amount_low: float,
    amount_high: float,
    filing_date: str | None = None,
    ticker: str = "AAPL",
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "member": member,
        "transaction_date": transaction_date,
        "filing_date": filing_date or transaction_date,
        "transaction_type": transaction_type,
        "amount_low": amount_low,
        "amount_high": amount_high,
        "amount_range_raw": f"${amount_low:,.0f} – ${amount_high:,.0f}",
    }


def test_format_cumulative_range_label_collapsed():
    assert format_cumulative_range_label(8000, 8000, 8000) == "$8.0K net"


def test_format_cumulative_range_label_with_band():
    label = format_cumulative_range_label(8000, 1000, 15000)
    assert label.startswith("~")
    assert "range" in label
    assert "$1.0K" in label
    assert "$15.0K" in label


def test_ticker_cumulative_exposure_payload_buy_then_sell_band():
    frame = pd.DataFrame(
        [
            _trade(
                member="Alice",
                transaction_date="2024-01-10",
                transaction_type="P",
                amount_low=1_000,
                amount_high=15_000,
            ),
            _trade(
                member="Alice",
                transaction_date="2024-02-10",
                transaction_type="S",
                amount_low=1_000,
                amount_high=15_000,
            ),
        ]
    )
    payload = ticker_cumulative_exposure_payload(frame, "AAPL")
    assert payload["ticker"] == "AAPL"
    assert payload["members"] == ["Alice"]
    assert len(payload["rows"]) == 2

    first, second = payload["rows"]
    # Buy $1k–$15k: floor +1k, median +8k, ceiling +15k
    assert first["cumulative_low"] == 1_000.0
    assert first["cumulative_net"] == 8_000.0
    assert first["cumulative_high"] == 15_000.0
    assert "range" in str(first["cumulative_label"])

    # After matching sell: median nets to 0; band spans -14k … +14k
    assert second["cumulative_net"] == 0.0
    assert second["cumulative_low"] == 1_000.0 - 15_000.0
    assert second["cumulative_high"] == 15_000.0 - 1_000.0
    assert second["cumulative_low"] < second["cumulative_net"] < second["cumulative_high"]


def test_ticker_cumulative_exposure_payload_sell_floor_more_negative():
    frame = pd.DataFrame(
        [
            _trade(
                member="Bob",
                transaction_date="2024-03-01",
                transaction_type="S",
                amount_low=15_001,
                amount_high=50_000,
            )
        ]
    )
    payload = ticker_cumulative_exposure_payload(frame, "AAPL")
    row = payload["rows"][0]
    assert row["cumulative_low"] == -50_000.0
    assert row["cumulative_high"] == -15_001.0
    assert row["cumulative_low"] < row["cumulative_high"]
    assert row["cumulative_net"] < 0
