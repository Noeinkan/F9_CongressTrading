from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No live Polygon/OpenFIGI during tests; quieter progress bars."""
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    monkeypatch.delenv("OPENFIGI_API_KEY", raising=False)
    monkeypatch.setenv("CONGRESS_SKIP_POLYGON_TICKER_DETAILS", "1")
    monkeypatch.setenv("TQDM_DISABLE", "1")
    monkeypatch.delenv("CONGRESS_RE_RESOLVE_TICKERS_BULK", raising=False)
    monkeypatch.delenv("CONGRESS_DISABLE_RE_RESOLVE_OPENFIGI_BATCH", raising=False)
