"""Net-trade chart must ignore annuities/bonds mis-tagged with equity tickers."""
from __future__ import annotations

import pandas as pd

from src.api._home_analytics import aggregate_net_trade_amount, tickers_available


def _row(
    *,
    ticker: str,
    asset_name_raw: str,
    asset_type: str,
    transaction_type: str,
    amount_low: float,
    amount_high: float,
    transaction_date: str = "2025-12-29",
) -> dict:
    return {
        "ticker": ticker,
        "asset_name_raw": asset_name_raw,
        "asset_type": asset_type,
        "transaction_type": transaction_type,
        "amount_low": amount_low,
        "amount_high": amount_high,
        "transaction_date": pd.Timestamp(transaction_date),
    }


def test_aggregate_net_trade_excludes_annuity_masquerading_as_equity_ticker():
    frame = pd.DataFrame(
        [
            _row(
                ticker="PRU",
                asset_name_raw=(
                    "Prudential RILA - 10% Buffer 6-year Alliance Bernstein "
                    "500 Plus Index with participation rate [VA]"
                ),
                asset_type="annuity",
                transaction_type="P",
                amount_low=5_000_001,
                amount_high=25_000_000,
            ),
            _row(
                ticker="AAPL",
                asset_name_raw="Apple Inc. - Common Stock (AAPL) [ST]",
                asset_type="equity",
                transaction_type="P",
                amount_low=15_001,
                amount_high=50_000,
            ),
        ]
    )

    agg = aggregate_net_trade_amount(frame, top_n=20)
    assert agg is not None
    tickers = set(agg["ticker"].astype(str))
    assert "PRU" not in tickers
    assert "AAPL" in tickers


def test_aggregate_net_trade_excludes_bond_asset_type():
    frame = pd.DataFrame(
        [
            _row(
                ticker="PRU",
                asset_name_raw="Prudential Finl Inc Medium Term",
                asset_type="bond",
                transaction_type="P",
                amount_low=15_001,
                amount_high=15_001,
            ),
            _row(
                ticker="MSFT",
                asset_name_raw="Microsoft Corporation - Common Stock (MSFT) [ST]",
                asset_type="equity",
                transaction_type="P",
                amount_low=1_001,
                amount_high=15_000,
            ),
        ]
    )

    agg = aggregate_net_trade_amount(frame, top_n=20)
    assert agg is not None
    tickers = set(agg["ticker"].astype(str))
    assert "PRU" not in tickers
    assert "MSFT" in tickers


def test_aggregate_net_trade_keeps_real_equity():
    frame = pd.DataFrame(
        [
            _row(
                ticker="NVDA",
                asset_name_raw="NVIDIA Corporation - Common Stock (NVDA) [ST]",
                asset_type="equity",
                transaction_type="P",
                amount_low=50_001,
                amount_high=100_000,
            ),
            _row(
                ticker="NVDA",
                asset_name_raw="NVIDIA Corporation - Common Stock (NVDA) [ST]",
                asset_type="equity",
                transaction_type="S",
                amount_low=1_001,
                amount_high=15_000,
            ),
        ]
    )

    agg = aggregate_net_trade_amount(frame, top_n=20)
    assert agg is not None
    assert list(agg["ticker"]) == ["NVDA"]
    assert float(agg.iloc[0]["net_amount"]) > 0


def test_tickers_available_excludes_annuity_ticker():
    frame = pd.DataFrame(
        [
            _row(
                ticker="PRU",
                asset_name_raw="Prudential RILA - 10% Buffer [VA]",
                asset_type="annuity",
                transaction_type="P",
                amount_low=5_000_001,
                amount_high=25_000_000,
            ),
            _row(
                ticker="AAPL",
                asset_name_raw="Apple Inc. - Common Stock (AAPL) [ST]",
                asset_type="equity",
                transaction_type="P",
                amount_low=15_001,
                amount_high=50_000,
            ),
        ]
    )
    assert tickers_available(frame) == ["AAPL"]
