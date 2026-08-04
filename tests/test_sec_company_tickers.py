"""Unit tests for SEC company_tickers local resolver (fixture only, no network)."""

from src.sec_company_tickers import (
    SecTickerMatch,
    build_sec_index_from_payload,
    match_sec_company_ticker,
    reset_sec_company_tickers_cache,
)
from src.utils import normalize_key


def test_build_index_from_payload():
    payload = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
        "2": {"cik_str": 1, "ticker": "", "title": "Bad"},
    }
    index = build_sec_index_from_payload(payload)
    assert index[normalize_key("Apple Inc.")] == "AAPL"
    assert index[normalize_key("MICROSOFT CORP")] == "MSFT"
    assert "" not in index.values() or all(index.values())


def test_exact_and_fuzzy_match_against_fixture_index():
    reset_sec_company_tickers_cache()
    index = build_sec_index_from_payload(
        {
            "0": {"cik_str": 1, "ticker": "JPM", "title": "JPMORGAN CHASE & CO"},
            "1": {"cik_str": 2, "ticker": "LOW", "title": "LOWE'S COMPANIES, INC."},
            "2": {"cik_str": 3, "ticker": "SLB", "title": "Schlumberger Limited"},
        }
    )

    exact = match_sec_company_ticker("JPMORGAN CHASE & CO", index=index)
    assert exact is not None
    assert exact.exact is True
    assert exact.ticker == "JPM"

    fuzzy = match_sec_company_ticker("Lowes Companies Inc", index=index, fuzzy_min_score=85)
    assert fuzzy is not None
    assert fuzzy.ticker == "LOW"
    assert isinstance(fuzzy, SecTickerMatch)

    miss = match_sec_company_ticker("Totally Fake Private LLC", index=index, fuzzy_min_score=95)
    assert miss is None
