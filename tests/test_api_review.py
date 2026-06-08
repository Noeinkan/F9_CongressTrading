"""Smoke tests for the Review API route: auth gate + payload shape."""
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


def test_review_requires_auth(client):
    assert client.get("/api/review/summary").status_code == 401


def test_review_summary_shape(client):
    _login(client)
    r = client.get("/api/review/summary")
    assert r.status_code == 200
    data = r.json()

    for key in ("ready", "review_source", "kpis", "rows", "total", "limit", "offset"):
        assert key in data, f"missing {key}"

    kpis = data["kpis"]
    for key in (
        "open_count",
        "total_count",
        "high_confidence_pct",
        "high_confidence_label",
        "by_reason",
        "by_status",
        "by_month",
    ):
        assert key in kpis, f"missing kpis.{key}"

    assert isinstance(data["rows"], list)
    assert isinstance(kpis["by_reason"], list)
    assert isinstance(kpis["by_status"], list)
    assert isinstance(kpis["by_month"], list)


def test_review_pagination_limit(client):
    _login(client)
    r = client.get("/api/review/summary?limit=2&offset=0")
    assert r.status_code == 200
    data = r.json()
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert len(data["rows"]) <= 2


def test_review_pagination_offset_past_end(client):
    _login(client)
    total = client.get("/api/review/summary").json()["total"]
    r = client.get(f"/api/review/summary?limit=10&offset={total + 100}")
    assert r.status_code == 200
    assert r.json()["rows"] == []


def test_review_limit_validation(client):
    _login(client)
    assert client.get("/api/review/summary?limit=1001").status_code == 422
