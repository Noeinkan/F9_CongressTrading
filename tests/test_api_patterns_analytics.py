"""Unit tests for the streamlit-free pattern analytics helpers in src.api."""
from __future__ import annotations

import pandas as pd

from src.api._constants import COMMITTEE_SECTOR_MAP
from src.api._patterns_analytics import (
    add_trade_categories,
    bipartisan_tickers,
    call_put_monthly,
    classify_option_side,
    committee_relevant_trades,
    committee_relevance_coverage,
    coordinated_pattern_transactions,
    detect_coordinated_trades,
    member_ticker_breakdown,
    score_committee_relevance,
    summarize_committee_relevance,
    ticker_member_breakdown,
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


def test_add_trade_categories():
    frame = add_trade_categories(_sample_frame())
    assert "is_buy" in frame.columns
    assert "is_sell" in frame.columns
    assert "option_side" in frame.columns
    assert "party_label" in frame.columns
    assert frame.loc[frame["ticker"] == "AAPL", "is_buy"].all()
    assert (frame.loc[frame["ticker"] == "MSFT", "option_side"] == "Call").all()
    assert frame["party_label"].isin(["Democrat", "Republican"]).all()


def test_classify_option_side():
    row = pd.Series(
        {
            "asset_type": "Stock Option",
            "asset_name_raw": "NVDA Put",
            "asset_name_normalized": "",
            "issuer_name": "",
        }
    )
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


def test_ticker_member_breakdown():
    frame = _sample_frame()
    out = ticker_member_breakdown(frame, "AAPL")
    assert len(out) == 2
    assert set(out["member"]) == {"Alice", "Bob"}


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


def test_score_committee_relevance_overlap():
    frame = pd.DataFrame(
        [
            {
                "member": "Alice",
                "chamber": "House",
                "party": "D",
                "ticker": "LMT",
                "sector": "Industrials",
                "industry": "Aerospace",
                "transaction_type": "P",
                "transaction_type_label": "Buy",
                "transaction_date": pd.Timestamp("2024-06-01"),
                "amount_range_raw": "15k-50k",
                "issuer_name": "Lockheed",
                "asset_name_raw": "Lockheed Martin",
            },
            {
                "member": "Alice",
                "chamber": "House",
                "party": "D",
                "ticker": "XYZ",
                "sector": "Real Estate",
                "industry": "REIT",
                "transaction_type": "P",
                "transaction_type_label": "Buy",
                "transaction_date": pd.Timestamp("2024-07-01"),
                "amount_range_raw": "1k-15k",
                "issuer_name": "Example REIT",
                "asset_name_raw": "Example REIT",
            },
        ]
    )
    assignments = {"alice": ["Armed Services", "Agriculture"]}
    scored = score_committee_relevance(frame, assignments, COMMITTEE_SECTOR_MAP)
    assert len(scored) == 2
    relevant = committee_relevant_trades(scored)
    assert len(relevant) == 1
    assert relevant.iloc[0]["ticker"] == "LMT"
    assert "Armed Services" in relevant.iloc[0]["matching_committees"]

    summary = summarize_committee_relevance(scored)
    row = summary.loc[summary["member"] == "Alice"].iloc[0]
    assert int(row["relevant_trades"]) == 1
    assert row["relevance_pct"] == 50.0

    cov = committee_relevance_coverage(frame, assignments)
    assert cov["members_mapped"] == 1
    assert cov["sector_coverage_pct"] == 100.0
