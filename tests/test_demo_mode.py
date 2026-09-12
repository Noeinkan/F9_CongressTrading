"""Demo mode: the kill switch, the read-only guard and the one-click sign-in.

Two properties the public demo rests on, proved here rather than assumed:
a deployment with ``DEMO_MODE`` unset cannot mint a demo session at all, and a
deployment with it on cannot be written to.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# Every mutating API route. The guard is a middleware precisely so this list
# does not have to be maintained in the app — but it does have to be exercised.
WRITE_ROUTES = [
    ("/api/review/items/1/resolve", {"ticker": "AAPL", "apply_to_asset": False}),
    ("/api/review/items/1/accept", {"apply_to_asset": False}),
    ("/api/review/items/1/dismiss", None),
    ("/api/admin/refresh-data", {"restart": True}),
    ("/api/admin/refresh-data/cancel", None),
]


@pytest.fixture
def demo_env(monkeypatch):
    """A deployment configured the way the public demo is."""
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_USERNAME", "demo")
    monkeypatch.setenv("DEMO_PASSWORD", "demo")
    monkeypatch.setenv("DEMO_SNAPSHOT_DATE", "2026-09-12")
    monkeypatch.setenv("APP_USERNAME", "demo")
    monkeypatch.setenv("APP_PASSWORD", "demo")
    monkeypatch.setenv("APP_SESSION_SECRET", "test-secret")


@pytest.fixture
def live_env(monkeypatch):
    """A normal deployment: the demo is off, as it is by default."""
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setenv("APP_USERNAME", "analyst")
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    monkeypatch.setenv("APP_SESSION_SECRET", "test-secret")


def _client() -> TestClient:
    from src.api.app import create_app

    return TestClient(create_app())


# --------------------------------------------------------------------------
# Kill switch
# --------------------------------------------------------------------------


def test_status_reports_disabled_by_default(live_env):
    """Safe to call on a production deployment; it admits to nothing."""
    response = _client().get("/api/demo/status")
    assert response.status_code == 200
    assert response.json() == {"enabled": False}


def test_session_cannot_be_minted_with_the_switch_off(live_env):
    """The security boundary: no demo session exists where the demo does not."""
    response = _client().post("/api/demo/session")
    assert response.status_code == 404


@pytest.mark.parametrize("value", ["0", "false", "no", "off", ""])
def test_falsey_values_all_keep_the_demo_off(live_env, monkeypatch, value):
    monkeypatch.setenv("DEMO_MODE", value)
    client = _client()
    assert client.get("/api/demo/status").json() == {"enabled": False}
    assert client.post("/api/demo/session").status_code == 404


def test_switch_off_leaves_writes_to_the_normal_auth_gate(live_env):
    """Off-demo, a write is refused for lack of a session — never as a demo 403."""
    client = _client()
    for path, body in WRITE_ROUTES:
        response = client.post(path, json=body) if body else client.post(path)
        assert response.status_code == 401, path
        assert "demo" not in response.json()


# --------------------------------------------------------------------------
# The demo itself
# --------------------------------------------------------------------------


def test_status_carries_the_snapshot_date_and_the_hidden_routes(demo_env):
    body = _client().get("/api/demo/status").json()
    assert body["enabled"] is True
    assert body["readOnly"] is True
    assert body["snapshotDate"] == "2026-09-12"
    assert body["snapshotLabel"] == "Snapshot: 12 September 2026"
    assert "/executive" in body["hiddenRoutes"]
    assert body["notice"]


def test_one_click_sign_in_yields_a_working_session(demo_env):
    client = _client()
    assert client.get("/api/session").json()["authenticated"] is False

    minted = client.post("/api/demo/session")
    assert minted.status_code == 200
    assert minted.json()["user"] == "demo"
    assert minted.json()["demo"] is True

    session = client.get("/api/session").json()
    assert session["authenticated"] is True
    assert session["user"] == "demo"


def test_the_published_credentials_still_work_at_the_normal_gate(demo_env):
    """A visitor who types demo/demo on the login form gets in the ordinary way."""
    client = _client()
    response = client.post("/api/login", json={"username": "demo", "password": "demo"})
    assert response.status_code == 200
    assert client.get("/api/session").json()["authenticated"] is True


@pytest.mark.parametrize("path,body", WRITE_ROUTES)
def test_every_write_is_refused_in_demo_mode(demo_env, path, body):
    client = _client()
    client.post("/api/demo/session")

    response = client.post(path, json=body) if body else client.post(path)
    assert response.status_code == 403, path
    payload = response.json()
    assert payload["readOnly"] is True
    assert payload["demo"] is True
    # A friendly wall, not a raw 4xx: it says what is off and why.
    assert "read-only public demo" in payload["detail"]


def test_reads_are_untouched_by_the_guard(demo_env):
    """The demo is read-only, not crippled — GETs go through as normal."""
    client = _client()
    client.post("/api/demo/session")
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/demo/status").status_code == 200


def test_signing_out_is_still_allowed(demo_env):
    """Logout is a write, and blocking it would trap the visitor in the demo."""
    client = _client()
    client.post("/api/demo/session")
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/session").json()["authenticated"] is False


def test_the_guard_does_not_touch_non_api_paths(demo_env):
    """Only /api/* is guarded; the static frontend is served by nginx anyway."""
    response = _client().post("/not-the-api")
    assert response.status_code == 404
