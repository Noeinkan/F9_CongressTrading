"""Smoke tests for the Patterns API route: auth gate + payload shape.

Mirrors the review suite: auth required, contract keys, param validation,
empty-database / no-data edge cases. Counts are not asserted (the dataset
under test is whatever is on disk).
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


def test_patterns_summary_requires_auth(client):
    assert client.get("/api/patterns/summary").status_code == 401


def test_patterns_summary_shape(client):
    _login(client)
    r = client.get("/api/patterns/summary")
    assert r.status_code == 200
    data = r.json()

    for key in (
        "ready",
        "window_days",
        "min_members",
        "coordinated_limit",
        "committee",
        "coordinated",
        "call_put",
        "volume_anomalies",
        "bipartisan",
    ):
        assert key in data, f"missing {key}"

    committee = data["committee"]
    for key in ("summary", "members_with_overlap", "coverage"):
        assert key in committee, f"missing committee.{key}"
    for key in ("member_coverage_pct", "sector_coverage_pct", "members_mapped"):
        assert key in committee["coverage"], f"missing committee.coverage.{key}"

    call_put = data["call_put"]
    for key in ("monthly", "ratio"):
        assert key in call_put

    assert isinstance(data["coordinated"], list)
    assert isinstance(data["volume_anomalies"], list)
    assert isinstance(data["bipartisan"], list)
    assert isinstance(call_put["monthly"], list)
    assert isinstance(call_put["ratio"], list)


def test_patterns_summary_respects_window(client):
    _login(client)
    r = client.get("/api/patterns/summary?window_days=30&min_members=3")
    assert r.status_code == 200
    data = r.json()
    assert data["window_days"] == 30
    assert data["min_members"] == 3


def test_patterns_summary_param_validation(client):
    _login(client)
    # window_days out of range
    assert client.get("/api/patterns/summary?window_days=10").status_code == 422
    # min_members below floor
    assert client.get("/api/patterns/summary?min_members=1").status_code == 422
    # coordinated_limit above ceiling
    assert client.get("/api/patterns/summary?coordinated_limit=10000").status_code == 422


def test_committee_relevant_requires_member(client):
    _login(client)
    assert client.get("/api/patterns/committee_relevant").status_code == 422


def test_committee_relevant_empty_member(client):
    _login(client)
    r = client.get("/api/patterns/committee_relevant?member=")
    # FastAPI min_length=1 rejects the empty string with 422.
    assert r.status_code == 422


def test_committee_relevant_shape(client):
    _login(client)
    r = client.get("/api/patterns/committee_relevant?member=NoSuchMember")
    assert r.status_code == 200
    data = r.json()
    assert data["member"] == "NoSuchMember"
    assert "assignments_loaded" in data
    assert isinstance(data["rows"], list)


def test_coordinated_transactions_requires_ticker_and_pattern(client):
    _login(client)
    assert client.get("/api/patterns/coordinated_transactions").status_code == 422
    assert (
        client.get("/api/patterns/coordinated_transactions?ticker=AAPL").status_code == 422
    )


def test_coordinated_transactions_shape(client):
    _login(client)
    r = client.get(
        "/api/patterns/coordinated_transactions?ticker=AAPL&pattern=Coordinated+buy&window_days=365"
    )
    assert r.status_code == 200
    data = r.json()
    for key in ("ticker", "pattern", "window_days", "limit", "rows"):
        assert key in data, f"missing {key}"
    assert data["ticker"] == "AAPL"
    assert data["pattern"] == "Coordinated buy"
    assert data["window_days"] == 365
    assert isinstance(data["rows"], list)


def test_coordinated_transactions_param_validation(client):
    _login(client)
    assert (
        client.get(
            "/api/patterns/coordinated_transactions?ticker=AAPL&pattern=Coordinated+buy&limit=10000"
        ).status_code
        == 422
    )
