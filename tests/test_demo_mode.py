"""Demo mode: the kill switch, the tiers and the read-only guard.

Properties the public demo rests on, proved here rather than assumed: a
deployment with ``DEMO_MODE`` unset has no demo routes at all; on the demo,
locked features are refused by the server, removed features do not exist, and
nothing can be written. The email gate itself is ``test_demo_access.py``.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

# Every mutating API route that exists on the demo, and how it is refused there.
WRITE_ROUTES = [
    ("/api/review/items/1/resolve", {"ticker": "AAPL", "apply_to_asset": False}, "DEMO_LOCKED"),
    ("/api/review/items/1/accept", {"apply_to_asset": False}, "DEMO_LOCKED"),
    ("/api/review/items/1/dismiss", None, "DEMO_LOCKED"),
    ("/api/admin/refresh-data", {"restart": True}, "DEMO_READ_ONLY"),
    ("/api/admin/refresh-data/cancel", None, "DEMO_READ_ONLY"),
]


@pytest.fixture
def demo_env(monkeypatch, tmp_path):
    """A deployment configured the way the public demo is."""
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_SNAPSHOT_DATE", "2026-09-12")
    monkeypatch.setenv("DEMO_MAIL_BACKEND", "console")
    monkeypatch.setenv("DEMO_ACCESS_DB", str(tmp_path / "access.sqlite3"))
    monkeypatch.delenv("DEMO_ACCESS_GATE", raising=False)
    monkeypatch.delenv("DEMO_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("DEMO_NOTIFY_EMAIL", raising=False)
    # The demo sets no password: the email gate is the door.
    monkeypatch.delenv("APP_USERNAME", raising=False)
    monkeypatch.delenv("APP_PASSWORD", raising=False)
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


def _sign_in(client: TestClient, address: str = "visitor@example.com") -> None:
    assert client.post("/api/demo/access/request", json={"email": address}).status_code == 200
    text = client.app.state.demo_access.mailer.outbox[-1].text
    code = "".join(re.search(r"code is (\d{3}) (\d{3})", text).groups())
    assert client.post("/api/demo/access/code", json={"email": address, "code": code}).status_code == 200


# --------------------------------------------------------------------------
# Kill switch
# --------------------------------------------------------------------------


def test_status_reports_disabled_by_default(live_env):
    """Safe to call on a production deployment; it admits to nothing."""
    response = _client().get("/api/demo/status")
    assert response.status_code == 200
    assert response.json() == {"enabled": False}


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/demo/access/request"),
        ("post", "/api/demo/access/code"),
        ("get", "/api/demo/access/link?t=x"),
        ("post", "/api/demo/access/signout"),
        ("post", "/api/demo/session"),
        ("get", "/admin"),
    ],
)
def test_no_demo_route_exists_with_the_switch_off(live_env, method, path):
    """The security boundary: no demo sign-in exists where the demo does not."""
    response = getattr(_client(), method)(path)
    assert response.status_code == 404, path


@pytest.mark.parametrize("value", ["0", "false", "no", "off", ""])
def test_falsey_values_all_keep_the_demo_off(live_env, monkeypatch, value):
    monkeypatch.setenv("DEMO_MODE", value)
    client = _client()
    assert client.get("/api/demo/status").json() == {"enabled": False}
    assert client.post("/api/demo/access/request", json={"email": "a@example.com"}).status_code == 404


def test_switch_off_leaves_writes_to_the_normal_auth_gate(live_env):
    """Off-demo, a write is refused for lack of a session — never as a demo refusal."""
    client = _client()
    for path, body, _ in WRITE_ROUTES:
        response = client.post(path, json=body) if body else client.post(path)
        assert response.status_code == 401, path
        assert "code" not in response.json()


def test_locked_features_are_untouched_outside_the_demo(live_env):
    client = _client()
    assert client.post("/api/login", json={"username": "analyst", "password": "secret123"}).status_code == 200
    response = client.get("/api/raw/export.csv")
    assert response.status_code != 403
    assert "DEMO_LOCKED" not in response.text


def test_admin_routes_exist_outside_the_demo(live_env):
    """Removed from the demo process only: the live tracker keeps its refresh controls."""
    assert _client().get("/api/admin/refresh-data/status").status_code == 401


# --------------------------------------------------------------------------
# The demo itself
# --------------------------------------------------------------------------


def test_status_carries_the_snapshot_the_tiers_and_the_session(demo_env):
    body = _client().get("/api/demo/status").json()
    assert body["enabled"] is True
    assert body["readOnly"] is True
    assert body["snapshotDate"] == "2026-09-12"
    assert body["snapshotLabel"] == "Snapshot: 12 September 2026"
    assert "/executive" in body["hiddenRoutes"]
    assert body["notice"]
    assert body["session"] == {"minutes": 45}
    assert body["contactEmail"] == "support@noeinsolutions.com"
    assert {f["feature"] for f in body["locked"]} == {"csv_export", "review_actions"}
    assert all(f["label"] and f["message"] for f in body["locked"])
    assert body["access"]["gate"] is True
    assert body["access"]["status"] == "signed_out"
    assert [p["title"] for p in body["access"]["privacy"]] == ["What is stored.", "Why.", "For how long."]


def test_the_one_click_door_is_gone(demo_env):
    client = _client()
    assert client.post("/api/demo/session").status_code == 401
    _sign_in(client)
    assert client.post("/api/demo/session").status_code != 200


def test_the_old_published_credentials_open_nothing(demo_env):
    client = _client()
    response = client.post("/api/login", json={"username": "demo", "password": "demo"})
    assert response.status_code == 401
    assert response.json()["code"] == "DEMO_SIGNED_OUT"


@pytest.mark.parametrize("path,body,code", WRITE_ROUTES)
def test_every_write_is_refused_in_demo_mode(demo_env, path, body, code):
    client = _client()
    _sign_in(client)

    response = client.post(path, json=body) if body else client.post(path)
    assert response.status_code == 403, path
    payload = response.json()
    assert payload["code"] == code
    # A friendly wall, not a raw 4xx: it says what is off and why.
    assert payload["detail"]


@pytest.mark.parametrize("path", ["/api/home/net_trade.csv", "/api/raw/export.csv"])
def test_csv_downloads_are_locked_and_recorded(demo_env, path):
    client = _client()
    _sign_in(client)
    response = client.get(path)
    assert response.status_code == 403
    assert response.json()["code"] == "DEMO_LOCKED"
    assert response.json()["feature"] == "csv_export"
    events = client.app.state.demo_access.store.recent_events()
    assert any(e["kind"] == "locked" and e["detail"] == "csv_export" for e in events)


def test_admin_routes_are_removed_from_the_demo_process(demo_env):
    client = _client()
    _sign_in(client)
    assert client.get("/api/admin/refresh-data/status").status_code == 404
    assert client.get("/api/admin/deploy/status").status_code == 404


def test_reads_are_untouched_by_the_guard(demo_env):
    """The demo is read-only, not crippled — GETs go through as normal."""
    client = _client()
    _sign_in(client)
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/demo/status").status_code == 200
    session = client.get("/api/session").json()
    assert session["authenticated"] is True
    assert session["user"] == "visitor@example.com"


def test_signing_out_is_still_allowed(demo_env):
    """Sign-out is a write, and blocking it would trap the visitor in the demo."""
    client = _client()
    _sign_in(client)
    assert client.post("/api/demo/access/signout").status_code == 200
    assert client.get("/api/session").status_code == 401


def test_the_guard_does_not_touch_non_api_paths(demo_env, monkeypatch):
    """Only /api/* is read-only; the static frontend is served by nginx anyway."""
    monkeypatch.setenv("DEMO_ACCESS_GATE", "0")
    response = _client().post("/not-the-api")
    assert response.status_code == 404


def test_gate_off_is_an_open_demo_with_the_tiers_still_enforced(demo_env, monkeypatch):
    """DEMO_ACCESS_GATE=0 is for local runs: no sign-in, but locks and read-only still hold."""
    monkeypatch.setenv("DEMO_ACCESS_GATE", "0")
    client = _client()
    assert client.get("/api/demo/status").json()["access"] == {"gate": False}
    assert client.get("/api/session").json()["authenticated"] is True
    assert client.get("/api/raw/export.csv").json()["code"] == "DEMO_LOCKED"
    assert client.post("/api/review/items/1/dismiss").json()["code"] == "DEMO_LOCKED"
    assert client.post("/api/demo/access/request", json={"email": "a@example.com"}).status_code == 404
