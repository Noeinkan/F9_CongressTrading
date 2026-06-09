"""Smoke tests for the FastAPI layer: auth gate + Home payload shape.

These run against whatever dataset is present (SQLite/CSV/empty); they assert on
structure, not specific counts, so they are stable across data refreshes.
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


def test_health_reports_auth_required(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["auth_required"] is True
    assert "polygon_cache_rows" in data
    assert isinstance(data["polygon_cache_rows"], int)


def test_home_requires_auth(client):
    assert client.get("/api/home/summary").status_code == 401


def test_bad_login_rejected(client):
    r = client.post("/api/login", json={"username": "analyst", "password": "nope"})
    assert r.status_code == 401


def test_login_then_home_summary_shape(client):
    assert client.post(
        "/api/login", json={"username": "analyst", "password": "secret123"}
    ).status_code == 200

    r = client.get("/api/home/summary")
    assert r.status_code == 200
    data = r.json()

    # Top-level contract every Home render relies on.
    for key in (
        "ready",
        "hero",
        "kpis",
        "latest_transactions",
        "breakdown",
        "monthly_activity",
        "top_members",
        "top_tickers",
        "members_leaderboard",
        "net_trade_amounts",
        "tickers_available",
    ):
        assert key in data, f"missing {key}"

    # Leaderboard rows mirror /api/members/summary so the two endpoints
    # stay consistent. Optional keys (disclosed_range) are accepted too.
    assert isinstance(data["members_leaderboard"], list)
    if data["members_leaderboard"]:
        row = data["members_leaderboard"][0]
        for key in ("member", "trades", "tickers", "chamber", "party", "state"):
            assert key in row, f"missing leaderboard row key: {key}"

    hero = data["hero"]
    for key in ("transaction_source", "total_transactions", "disclosed_range"):
        assert key in hero

    if data["ready"]:
        keys = {k["key"] for k in data["kpis"]}
        assert keys == {"transactions", "members", "tickers", "open_reviews", "disclosed_range"}
        assert isinstance(data["breakdown"]["by_chamber"], list)


def test_logout_clears_session(client):
    client.post("/api/login", json={"username": "analyst", "password": "secret123"})
    assert client.get("/api/me").status_code == 200
    client.post("/api/logout")
    assert client.get("/api/me").status_code == 401


def test_session_probe_does_not_401(client):
    r = client.get("/api/session")
    assert r.status_code == 200
    assert r.json()["authenticated"] is False


def test_home_net_trade_csv_requires_auth(client):
    assert client.get("/api/home/net_trade.csv").status_code == 401


def test_home_net_trade_csv_returns_csv(client):
    client.post("/api/login", json={"username": "analyst", "password": "secret123"})
    r = client.get("/api/home/net_trade.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert "ticker" in r.text.splitlines()[0]


def test_home_ticker_drilldown_requires_auth(client):
    assert client.get("/api/home/ticker_drilldown?ticker=MSFT").status_code == 401


def test_home_ticker_drilldown_shape(client):
    client.post("/api/login", json={"username": "analyst", "password": "secret123"})
    r = client.get("/api/home/ticker_drilldown?ticker=MSFT")
    assert r.status_code == 200
    data = r.json()
    for key in ("ready", "ticker", "ticker_timeline", "ticker_3d", "ticker_cumulative"):
        assert key in data, f"missing {key}"
    assert data["ticker"] == "MSFT"
    assert isinstance(data["ticker_timeline"], list)
    assert isinstance(data["ticker_3d"], list)
    assert isinstance(data["ticker_cumulative"], list)


def test_home_net_trade_amounts_row_shape(client):
    client.post("/api/login", json={"username": "analyst", "password": "secret123"})
    r = client.get("/api/home/summary")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data["net_trade_amounts"], list)
    assert isinstance(data["tickers_available"], list)
    if data["net_trade_amounts"]:
        row = data["net_trade_amounts"][0]
        for key in ("ticker", "direction", "net_amount", "trades"):
            assert key in row, f"missing net_trade row key: {key}"


def test_home_members_leaderboard_row_shape(client):
    client.post("/api/login", json={"username": "analyst", "password": "secret123"})
    r = client.get("/api/home/summary")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data["members_leaderboard"], list)
    if data["members_leaderboard"]:
        row = data["members_leaderboard"][0]
        for key in ("member", "trades", "tickers", "chamber", "party", "state"):
            assert key in row, f"missing leaderboard row key: {key}"


def test_home_latest_transactions_row_shape(client):
    client.post("/api/login", json={"username": "analyst", "password": "secret123"})
    r = client.get("/api/home/summary")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data["latest_transactions"], list)
    if data["latest_transactions"]:
        row = data["latest_transactions"][0]
        for key in ("member", "ticker", "transaction_type_label", "amount_range_raw"):
            assert key in row, f"missing latest_transactions row key: {key}"
        # issuer_name is the company label rendered next to the ticker; it
        # may be an empty string when unresolved, but the key must exist.
        assert "issuer_name" in row, "missing issuer_name in latest_transactions row"
