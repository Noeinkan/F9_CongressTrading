"""Smoke tests for the Tickers API route: auth gate + payload shape.

Mirrors the patterns / members suites: auth required, contract keys, param
validation, empty-database / no-data edge cases. Counts are not asserted
(the dataset under test is whatever is on disk).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app


@pytest.fixture
def auth_env(monkeypatch):
    monkeypatch.setenv("APP_USERNAME", "analyst")
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    monkeypatch.setenv("APP_SESSION_SECRET", "test-secret")


@pytest.fixture
def client(auth_env):
    return TestClient(create_app())


def _login(client: TestClient) -> None:
    assert client.post(
        "/api/login", json={"username": "analyst", "password": "secret123"}
    ).status_code == 200


def test_tickers_list_requires_auth(client):
    assert client.get("/api/tickers").status_code == 401


def test_tickers_list_shape(client):
    _login(client)
    r = client.get("/api/tickers")
    assert r.status_code == 200
    data = r.json()
    for key in ("ready", "total", "page", "page_size", "total_pages", "sort", "search", "rows", "source"):
        assert key in data, f"missing {key}"
    assert data["page"] == 1
    assert data["page_size"] == 50
    assert isinstance(data["rows"], list)
    assert data["sort"] == {"column": "trades", "order": "desc"}


def test_tickers_list_row_shape(client):
    _login(client)
    r = client.get("/api/tickers?page_size=10")
    assert r.status_code == 200
    data = r.json()
    if not data["rows"]:
        pytest.skip("No data on disk to assert leaderboard row shape.")
    row = data["rows"][0]
    for key in (
        "ticker",
        "issuer_name",
        "sector",
        "trades",
        "members",
        "buy",
        "sell",
        "call",
        "put",
        "exchange",
        "amount_low",
        "amount_high",
        "disclosed_range",
        "first_trade",
        "last_trade",
        "is_non_equity",
    ):
        assert key in row, f"missing leaderboard row key: {key}"
    assert isinstance(row["is_non_equity"], bool)


def test_tickers_list_sort_and_order(client):
    _login(client)
    r = client.get("/api/tickers?sort=ticker&order=asc&page_size=20")
    assert r.status_code == 200
    data = r.json()
    assert data["sort"] == {"column": "ticker", "order": "asc"}
    tickers = [row["ticker"] for row in data["rows"] if row.get("ticker")]
    if len(tickers) >= 2:
        assert tickers == sorted(tickers)


def test_tickers_list_search_shrinks_total(client):
    _login(client)
    base = client.get("/api/tickers?page_size=1").json()
    if not base["ready"] or base["total"] == 0:
        pytest.skip("No data on disk to assert search filter.")
    rows = client.get("/api/tickers?page_size=200").json()["rows"]
    tickers = [r["ticker"] for r in rows if r.get("ticker")]
    if not tickers:
        pytest.skip("No tickers in the slice to filter by.")
    needle = tickers[0][:1].upper()
    filtered = client.get(f"/api/tickers?search={needle}").json()
    assert filtered["total"] <= base["total"]
    # Every returned ticker / issuer should contain the needle (case-insensitive).
    for row in filtered["rows"]:
        haystack = f"{row.get('ticker', '')} {row.get('issuer_name', '')}".lower()
        assert needle.lower() in haystack


def test_tickers_list_param_validation(client):
    _login(client)
    assert client.get("/api/tickers?sort=member").status_code == 422
    assert client.get("/api/tickers?order=sideways").status_code == 422
    assert client.get("/api/tickers?page=0").status_code == 422
    assert client.get("/api/tickers?page_size=0").status_code == 422
    assert client.get("/api/tickers?page_size=999").status_code == 422


def test_ticker_detail_requires_auth(client):
    assert client.get("/api/tickers/AAPL").status_code == 401


def test_ticker_detail_unknown_symbol(client):
    _login(client)
    r = client.get("/api/tickers/ZZZ_NOPE_NOT_REAL")
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == "ZZZ_NOPE_NOT_REAL"
    assert "issuer" in data
    assert "kpis" in data
    assert data["kpis"]["ticker"] == "ZZZ_NOPE_NOT_REAL"
    assert data["kpis"]["trades"] == 0
    assert isinstance(data["members"], list)
    assert isinstance(data["transactions"], list)


def test_ticker_detail_shape_for_real_symbol(client):
    _login(client)
    list_resp = client.get("/api/tickers?page_size=1").json()
    if not list_resp["ready"] or not list_resp["rows"]:
        pytest.skip("No data on disk to assert detail shape.")
    ticker = list_resp["rows"][0]["ticker"]
    r = client.get(f"/api/tickers/{ticker}")
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == ticker
    assert "issuer" in data
    for key in (
        "ticker",
        "trades",
        "members",
        "buy",
        "sell",
        "call",
        "put",
        "exchange",
        "amount_low_total",
        "amount_high_total",
        "disclosed_range",
        "first_trade",
        "last_trade",
    ):
        assert key in data["kpis"], f"missing kpis.{key}"
    assert isinstance(data["members"], list)
    assert isinstance(data["transactions"], list)
    if data["members"]:
        member_row = data["members"][0]
        for key in (
            "member",
            "chamber",
            "party",
            "buy",
            "sell",
            "call",
            "put",
            "exchange",
            "trades",
            "amount_low_sum",
            "amount_high_sum",
            "disclosed_range",
            "first_trade",
            "last_trade",
        ):
            assert key in member_row, f"missing members row key: {key}"
    if data["transactions"]:
        tx_row = data["transactions"][0]
        assert "is_non_equity" in tx_row, "missing transactions.is_non_equity"
        assert isinstance(tx_row["is_non_equity"], bool)


def test_ticker_detail_tx_limit_param(client):
    _login(client)
    list_resp = client.get("/api/tickers?page_size=1").json()
    if not list_resp["ready"] or not list_resp["rows"]:
        pytest.skip("No data on disk to assert tx_limit.")
    ticker = list_resp["rows"][0]["ticker"]
    r = client.get(f"/api/tickers/{ticker}?tx_limit=1")
    assert r.status_code == 200
    data = r.json()
    assert data["transactions_limit"] == 1
    assert len(data["transactions"]) <= 1
    # And the validation guard
    assert client.get(f"/api/tickers/{ticker}?tx_limit=0").status_code == 422
    assert client.get(f"/api/tickers/{ticker}?tx_limit=99999").status_code == 422


def test_ticker_price_overlay_requires_auth(client):
    assert client.get("/api/tickers/AAPL/price_overlay").status_code == 401


def test_ticker_price_overlay_shape(client):
    _login(client)
    r = client.get("/api/tickers/AAPL/price_overlay")
    assert r.status_code == 200
    data = r.json()
    for key in ("ticker", "ready", "bars", "trades"):
        assert key in data, f"missing {key}"
    assert data["ticker"] == "AAPL"
    assert isinstance(data["bars"], list)
    assert isinstance(data["trades"], list)


def test_ticker_member_timeline_requires_auth(client):
    assert client.get("/api/tickers/AAPL/member_timeline").status_code == 401


def test_ticker_member_timeline_shape(client):
    _login(client)
    r = client.get("/api/tickers/ZZZ_NOPE_NOT_REAL/member_timeline")
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == "ZZZ_NOPE_NOT_REAL"
    assert isinstance(data["members"], list)
    assert isinstance(data["rows"], list)
    assert data["rows"] == []


def test_ticker_member_timeline_for_real_symbol(client):
    _login(client)
    list_resp = client.get("/api/tickers?page_size=1").json()
    if not list_resp["ready"] or not list_resp["rows"]:
        pytest.skip("No data on disk to assert member timeline.")
    ticker = list_resp["rows"][0]["ticker"]
    r = client.get(f"/api/tickers/{ticker}/member_timeline")
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == ticker
    assert isinstance(data["members"], list)
    assert isinstance(data["rows"], list)
    if data["rows"]:
        row = data["rows"][0]
        for key in ("member", "transaction_date", "transaction_type_label"):
            assert key in row, f"missing member timeline row key: {key}"


def test_ticker_cumulative_exposure_requires_auth(client):
    assert client.get("/api/tickers/AAPL/cumulative_exposure").status_code == 401


def test_ticker_cumulative_exposure_shape(client):
    _login(client)
    r = client.get("/api/tickers/ZZZ_NOPE_NOT_REAL/cumulative_exposure")
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == "ZZZ_NOPE_NOT_REAL"
    for key in ("members", "truncated", "rows"):
        assert key in data
    assert isinstance(data["rows"], list)


def test_ticker_cumulative_exposure_for_real_symbol(client):
    _login(client)
    list_resp = client.get("/api/tickers?page_size=1").json()
    if not list_resp["ready"] or not list_resp["rows"]:
        pytest.skip("No data on disk to assert cumulative exposure.")
    ticker = list_resp["rows"][0]["ticker"]
    r = client.get(f"/api/tickers/{ticker}/cumulative_exposure")
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == ticker
    assert isinstance(data["members"], list)
    assert isinstance(data["rows"], list)
    if data["rows"]:
        row = data["rows"][0]
        for key in (
            "member",
            "transaction_date",
            "cumulative_net",
            "cumulative_label",
            "txn_type_label",
        ):
            assert key in row, f"missing cumulative row key: {key}"


def test_resolve_session_close_returns_price_first():
    """Regression: ``_resolve_session_close`` must always return ``(price, date)``.

    The leaderboard + member-tickers endpoints 500'd when the trade date
    wasn't an exact match in the Polygon bar cache because the
    ``after``/``before`` branches returned ``(date, price)`` and downstream
    ``price_trade <= 0`` blew up with ``TypeError``.
    """
    from datetime import date

    from src.api._tickers_analytics import _resolve_session_close

    bars = [
        (date(2024, 1, 2), 100.0),
        (date(2024, 1, 3), 101.5),
        (date(2024, 1, 4), 102.0),
    ]

    # Exact match: any date in the bar list.
    exact = _resolve_session_close(bars, date(2024, 1, 3))
    assert exact is not None
    price, session = exact
    assert isinstance(price, float) and isinstance(session, date)
    assert price == 101.5 and session == date(2024, 1, 3)

    # Date before every cached bar — falls back to the first session.
    before = _resolve_session_close(bars, date(2023, 12, 31))
    assert before is not None
    price, session = before
    assert isinstance(price, float) and isinstance(session, date)
    assert price == 100.0 and session == date(2024, 1, 2)

    # Date after every cached bar — falls back to the last session.
    after = _resolve_session_close(bars, date(2024, 1, 10))
    assert after is not None
    price, session = after
    assert isinstance(price, float) and isinstance(session, date)
    assert price == 102.0 and session == date(2024, 1, 4)
