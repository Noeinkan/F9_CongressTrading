"""Unit tests for Yahoo bar fetch (no network)."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

from src.polygon_prices import fetch_yahoo_daily_bars


def test_fetch_yahoo_daily_bars_parses_close_column():
    idx = pd.to_datetime(["2025-01-02", "2025-01-03"])
    hist = pd.DataFrame({"Close": [100.0, 101.5]}, index=idx)
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = hist

    with patch("yfinance.Ticker", return_value=mock_ticker):
        bars = fetch_yahoo_daily_bars("AAPL", date(2025, 1, 1), date(2025, 1, 10))

    assert len(bars) == 2
    assert bars[0] == (date(2025, 1, 2), 100.0)
    assert bars[1] == (date(2025, 1, 3), 101.5)
    mock_ticker.history.assert_called_once()
