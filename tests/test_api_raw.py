"""Smoke + contract tests for the /api/raw route (transactions + CSV export).

Like test_api_home, these run against whatever dataset is present and assert on
structure/relationships, not specific counts, so they stay stable across data
refreshes.
"""
from __future__ import annotations

from math import ceil

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


def _login(client):
    assert client.post(
        "/api/login", json={"username": "analyst", "password": "secret123"}
    ).status_code == 200


def test_raw_requires_auth(client):
    assert client.get("/api/raw/transactions").status_code == 401


def test_raw_default_shape(client):
    _login(client)
    r = client.get("/api/raw/transactions")
    assert r.status_code == 200
    data = r.json()
    for key in ("ready", "total", "page", "page_size", "total_pages", "sort", "rows", "columns", "source"):
        assert key in data, f"missing {key}"
    assert data["sort"] == {"column": "transaction_date", "order": "desc"}
    assert isinstance(data["columns"], list) and data["columns"]
    # Column meta describes the table to the frontend.
    meta = data["columns"][0]
    assert {"key", "label", "type", "sortable"} <= set(meta)


def test_raw_pagination_math(client):
    _login(client)
    r = client.get("/api/raw/transactions?page_size=10")
    data = r.json()
    assert len(data["rows"]) <= 10
    if data["ready"]:
        assert data["total_pages"] == ceil(data["total"] / 10)
        if data["total"] > 10:
            page2 = client.get("/api/raw/transactions?page_size=10&page=2").json()
            assert page2["rows"] != data["rows"]


def test_raw_sort_amount_asc(client):
    _login(client)
    data = client.get("/api/raw/transactions?sort=amount_high&order=asc&page_size=200").json()
    if data["ready"]:
        vals = [row["amount_high"] for row in data["rows"] if row.get("amount_high") is not None]
        assert vals == sorted(vals)


def test_raw_ticker_filter_shrinks_total(client):
    _login(client)
    base = client.get("/api/raw/transactions?page_size=1").json()
    if not base["ready"] or base["total"] == 0:
        return
    # Find a known ticker from the data.
    rows = client.get("/api/raw/transactions?page_size=200").json()["rows"]
    tickers = [r["ticker"] for r in rows if r.get("ticker")]
    if not tickers:
        return
    known = tickers[0]
    filtered = client.get(f"/api/raw/transactions?ticker={known}").json()
    assert filtered["total"] <= base["total"]
    assert filtered["total"] >= 1


def test_raw_date_bounds(client):
    _login(client)
    data = client.get(
        "/api/raw/transactions?date_from=2024-01-01&date_to=2024-12-31&page_size=200"
    ).json()
    if data["ready"]:
        for row in data["rows"]:
            td = row.get("transaction_date")
            if td is not None:
                assert "2024-01-01" <= td <= "2024-12-31"


def test_raw_validation_errors(client):
    _login(client)
    assert client.get("/api/raw/transactions?sort=bogus").status_code == 422
    assert client.get("/api/raw/transactions?order=sideways").status_code == 422
    assert client.get("/api/raw/transactions?page_size=999").status_code == 422
    assert client.get("/api/raw/transactions?page=0").status_code == 422


def test_raw_csv_export(client):
    _login(client)
    r = client.get("/api/raw/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert "congress_transactions_filtered.csv" in r.headers["content-disposition"]

    body = r.text
    lines = body.splitlines()
    assert lines, "CSV should at least have a header row"
    header = lines[0]
    assert "member" in header and "chamber" in header

    # Data-row count equals the unpaginated total for the same (empty) filters.
    total = client.get("/api/raw/transactions?page_size=1").json()["total"]
    data_rows = len(lines) - 1
    assert data_rows == total
