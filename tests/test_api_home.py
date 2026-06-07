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
    monkeypatch.setenv("DASHBOARD_USERNAME", "analyst")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret123")
    monkeypatch.setenv("DASHBOARD_SESSION_SECRET", "test-secret")


@pytest.fixture
def client(auth_env):
    return TestClient(create_app())


def test_health_reports_auth_required(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "auth_required": True}


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
    ):
        assert key in data, f"missing {key}"

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
