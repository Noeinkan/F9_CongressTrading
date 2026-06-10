"""Smoke test: yfinance is installed and can return AAPL daily bars."""
from __future__ import annotations

import pytest


def test_yfinance_aapl_history_smoke():
    try:
        import yfinance as yf
    except ImportError:
        pytest.skip("yfinance not installed")

    hist = yf.Ticker("AAPL").history(period="5d", auto_adjust=True, actions=False)
    if hist is None or hist.empty:
        pytest.skip("Yahoo returned no data (network or rate limit)")
    assert "Close" in hist.columns
    assert len(hist) >= 1
