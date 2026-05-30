from __future__ import annotations

import pandas as pd

from src.dashboard_shared import (
    bipartisan_tickers,
    call_put_monthly,
    classify_option_side,
    coordinated_pattern_transactions,
    detect_coordinated_trades,
    member_ticker_breakdown,
    volume_anomalies,
)


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "member": "Alice",
                "chamber": "House",
                "party": "D",
                "state": "CA",
                "ticker": "AAPL",
                "transaction_type": "P",
                "transaction_date": pd.Timestamp("2024-06-01"),
                "asset_type": "Stock",
                "asset_name_raw": "Apple Inc",
                "asset_name_normalized": "Apple Inc",
                "issuer_name": "Apple",
                "amount_low": 10000,
                "amount_high": 20000,
                "amount_range_raw": "10k-20k",
            },
            {
                "member": "Bob",
                "chamber": "Senate",
                "party": "R",
                "state": "TX",
                "ticker": "AAPL",
                "transaction_type": "P",
                "transaction_date": pd.Timestamp("2024-06-15"),
                "asset_type": "Stock",
                "asset_name_raw": "Apple Inc",
                "asset_name_normalized": "Apple Inc",
                "issuer_name": "Apple",
                "amount_low": 20000,
                "amount_high": 30000,
                "amount_range_raw": "20k-30k",
            },
            {
                "member": "Alice",
                "chamber": "House",
                "party": "D",
                "state": "CA",
                "ticker": "MSFT",
                "transaction_type": "P",
                "transaction_date": pd.Timestamp("2024-07-01"),
                "asset_type": "Stock Option (Call)",
                "asset_name_raw": "Microsoft Call",
                "asset_name_normalized": "Microsoft Call",
                "issuer_name": "Microsoft",
                "amount_low": 1000,
                "amount_high": 9000,
                "amount_range_raw": "1k-9k",
            },
        ]
    )


def test_classify_option_side():
    row = pd.Series({"asset_type": "Stock Option", "asset_name_raw": "NVDA Put", "asset_name_normalized": "", "issuer_name": ""})
    assert classify_option_side(row) == "Put"


def test_detect_coordinated_trades():
    frame = _sample_frame()
    out = detect_coordinated_trades(frame, window_days=365, min_members=2)
    assert not out.empty
    assert (out["ticker"] == "AAPL").any()


def test_coordinated_pattern_transactions():
    frame = _sample_frame()
    tx = coordinated_pattern_transactions(
        frame,
        ticker="AAPL",
        pattern="Coordinated buy",
        window_days=365,
    )
    assert len(tx) == 2
    assert set(tx["member"]) == {"Alice", "Bob"}


def test_member_ticker_breakdown():
    frame = _sample_frame()
    out = member_ticker_breakdown(frame, "Alice")
    assert len(out) == 2
    aapl = out.loc[out["ticker"] == "AAPL"].iloc[0]
    assert int(aapl["buy"]) == 1


def test_call_put_monthly():
    frame = _sample_frame()
    out = call_put_monthly(frame)
    assert not out.empty
    assert set(out["option_side"]) <= {"Call", "Put"}


def test_bipartisan_tickers():
    frame = _sample_frame()
    out = bipartisan_tickers(frame, window_days=365)
    assert not out.empty
    assert (out["ticker"] == "AAPL").any()


def test_volume_anomalies_spike_ratio():
    frame = pd.DataFrame(
        [
            {"ticker": "SPIKE", "transaction_date": pd.Timestamp("2020-01-01")},
            {"ticker": "SPIKE", "transaction_date": pd.Timestamp("2024-06-01")},
            {"ticker": "SPIKE", "transaction_date": pd.Timestamp("2024-06-15")},
            {"ticker": "SPIKE", "transaction_date": pd.Timestamp("2024-07-01")},
        ]
    )
    out = volume_anomalies(frame, recent_days=90)
    row = out.loc[out["ticker"] == "SPIKE"].iloc[0]
    assert int(row["recent_disclosures"]) == 3
    assert row["prior_per_month"] < row["recent_per_month"]
    assert row["spike_ratio"] >= 2.0
