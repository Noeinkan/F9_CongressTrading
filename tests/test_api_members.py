"""Smoke tests for the Members API route: auth gate + payload shape.

Mirrors the patterns suite: auth required, contract keys, param validation,
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


def test_members_summary_requires_auth(client):
    assert client.get("/api/members/summary").status_code == 401


def test_members_summary_shape(client):
    _login(client)
    r = client.get("/api/members/summary")
    assert r.status_code == 200
    data = r.json()
    for key in ("ready", "transaction_source", "leaderboard", "kpi_sparklines"):
        assert key in data, f"missing {key}"
    assert isinstance(data["leaderboard"], list)
    sparklines = data["kpi_sparklines"]
    for key in ("members", "tickers", "transactions"):
        assert key in sparklines, f"missing kpi_sparklines.{key}"
        assert isinstance(sparklines[key], list)


def test_members_summary_leaderboard_row_shape(client):
    _login(client)
    r = client.get("/api/members/summary")
    assert r.status_code == 200
    data = r.json()
    if not data["leaderboard"]:
        pytest.skip("No data on disk to assert leaderboard row shape.")
    row = data["leaderboard"][0]
    for key in (
        "member",
        "trades",
        "tickers",
        "amount_low",
        "amount_high",
        "chamber",
        "party",
        "state",
    ):
        assert key in row, f"missing leaderboard row key: {key}"


def test_members_tickers_requires_auth(client):
    assert client.get("/api/members/Some%20Member/tickers").status_code == 401


def test_members_tickers_unknown_member_404(client):
    _login(client)
    r = client.get("/api/members/NoSuchMember/tickers")
    # 404 when data is loaded and member is unknown; if the DB is empty the
    # route short-circuits with 200 + empty rows.
    if r.status_code == 200:
        body = r.json()
        assert body["member"] == "NoSuchMember"
        assert body["rows"] == []
        return
    assert r.status_code == 404


def test_members_tickers_shape_for_real_member(client):
    _login(client)
    # Pick the first member from the leaderboard so the test is data-driven.
    summary = client.get("/api/members/summary").json()
    if not summary["leaderboard"]:
        pytest.skip("No data on disk to assert tickers drill-down.")
    member = summary["leaderboard"][0]["member"]
    r = client.get(f"/api/members/{member}/tickers")
    assert r.status_code == 200
    data = r.json()
    assert data["member"] == member
    assert "kpis" in data
    kpis = data["kpis"]
    for key in (
        "member",
        "trades",
        "tickers",
        "amount_low_total",
        "amount_high_total",
        "disclosed_range",
        "chamber",
        "party",
        "state",
        "sparklines",
    ):
        assert key in kpis, f"missing kpis.{key}"
    for key in ("transactions", "tickers", "disclosed_amount_high"):
        assert key in kpis["sparklines"]
    assert isinstance(data["rows"], list)
    if data["rows"]:
        row = data["rows"][0]
        for key in (
            "ticker",
            "issuer_name",
            "transaction_type",
            "transaction_type_label",
            "transaction_date",
            "amount_low",
            "amount_high",
            "amount_range_raw",
            "is_non_equity",
        ):
            assert key in row, f"missing tickers row key: {key}"
        assert isinstance(row["is_non_equity"], bool)


def test_members_committee_relevant_requires_auth(client):
    assert client.get("/api/members/Some%20Member/committee_relevant").status_code == 401


def test_members_committee_relevant_shape(client):
    _login(client)
    r = client.get("/api/members/NoSuchMember/committee_relevant")
    if r.status_code == 200:
        body = r.json()
        assert body["member"] == "NoSuchMember"
        assert "assignments_loaded" in body
        assert isinstance(body["rows"], list)
        return
    assert r.status_code == 404


def test_members_committee_relevant_for_real_member(client):
    _login(client)
    summary = client.get("/api/members/summary").json()
    if not summary["leaderboard"]:
        pytest.skip("No data on disk to assert committee drill-down.")
    member = summary["leaderboard"][0]["member"]
    r = client.get(f"/api/members/{member}/committee_relevant")
    assert r.status_code == 200
    data = r.json()
    assert data["member"] == member
    assert "assignments_loaded" in data
    assert isinstance(data["rows"], list)


def test_members_activity_timeline_requires_auth(client):
    assert client.get("/api/members/Some%20Member/activity_timeline").status_code == 401


def test_members_activity_timeline_shape(client):
    _login(client)
    r = client.get("/api/members/NoSuchMember/activity_timeline")
    if r.status_code == 200:
        body = r.json()
        assert body["member"] == "NoSuchMember"
        for key in ("truncated", "truncate_note", "tickers", "rows"):
            assert key in body
        assert isinstance(body["rows"], list)
        return
    assert r.status_code == 404


def test_members_activity_timeline_for_real_member(client):
    _login(client)
    summary = client.get("/api/members/summary").json()
    if not summary["leaderboard"]:
        pytest.skip("No data on disk to assert activity timeline.")
    member = summary["leaderboard"][0]["member"]
    r = client.get(f"/api/members/{member}/activity_timeline")
    assert r.status_code == 200
    data = r.json()
    assert data["member"] == member
    assert isinstance(data["tickers"], list)
    assert isinstance(data["rows"], list)
    if data["rows"]:
        row = data["rows"][0]
        for key in (
            "ticker",
            "transaction_date",
            "transaction_type",
            "transaction_type_label",
            "amount_range_raw",
        ):
            assert key in row, f"missing activity row key: {key}"
