"""Tests for admin refresh-data background ingest job."""
from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.jobs import CancelledError, JobManager, run_ingest_all


@pytest.fixture
def auth_env(monkeypatch):
    monkeypatch.setenv("APP_USERNAME", "analyst")
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    monkeypatch.setenv("APP_SESSION_SECRET", "test-secret")


@pytest.fixture
def client(auth_env):
    return TestClient(create_app())


def _login(client: TestClient) -> None:
    r = client.post("/api/login", json={"username": "analyst", "password": "secret123"})
    assert r.status_code == 200


def test_job_manager_runs_ingest_all_to_success(monkeypatch):
    calls: list[str] = []

    def fake_download(years, *, overwrite=False, extract=True):
        calls.append(f"download:{years}")
        return years

    def fake_house() -> None:
        calls.append("house")

    def fake_senate() -> None:
        calls.append("senate")

    monkeypatch.setattr("src.download_house_fd.download_house_fd_bulk", fake_download)
    monkeypatch.setattr("src.ingest_house.ingest_house", fake_house)
    monkeypatch.setattr("src.ingest_senate.ingest_senate", fake_senate)

    manager = JobManager()
    snapshot = manager.start_or_restart()
    assert snapshot["status"] == "running"

    deadline = time.time() + 10
    while time.time() < deadline:
        snap = manager.get_state()
        if snap["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.05)

    final = manager.get_state()
    assert final["status"] == "succeeded"
    assert final["progress"] == 100
    assert final["result"]["scope"] == "ingest-all"
    assert "download_years" in final["result"]
    assert calls[0].startswith("download:")
    assert calls[-2:] == ["house", "senate"]


def test_job_manager_cancel_between_steps(monkeypatch):
    entered_house = threading.Event()
    release_house = threading.Event()

    def slow_house() -> None:
        entered_house.set()
        assert release_house.wait(timeout=5)

    def fake_senate() -> None:
        pytest.fail("senate should not run after cancel")

    monkeypatch.setattr("src.download_house_fd.download_house_fd_bulk", lambda *a, **k: [])
    monkeypatch.setattr("src.ingest_house.ingest_house", slow_house)
    monkeypatch.setattr("src.ingest_senate.ingest_senate", fake_senate)

    manager = JobManager()
    manager.start_or_restart()
    assert entered_house.wait(timeout=5)
    manager.cancel()
    release_house.set()

    deadline = time.time() + 10
    while time.time() < deadline:
        snap = manager.get_state()
        if snap["status"] == "cancelled":
            break
        time.sleep(0.05)

    assert manager.get_state()["status"] == "cancelled"


def test_run_ingest_all_raises_on_cancel_before_house(monkeypatch):
    cancel = threading.Event()
    cancel.set()
    state = __import__("src.api.jobs", fromlist=["JobState"]).JobState()

    monkeypatch.setattr("src.download_house_fd.download_house_fd_bulk", lambda *a, **k: [])
    monkeypatch.setattr("src.ingest_house.ingest_house", lambda: pytest.fail("house"))
    monkeypatch.setattr("src.ingest_senate.ingest_senate", lambda: pytest.fail("senate"))

    with pytest.raises(CancelledError):
        run_ingest_all(state, cancel)


def test_refresh_status_requires_auth(client):
    assert client.get("/api/admin/refresh-data/status").status_code == 401
    assert client.post("/api/admin/refresh-data", json={"restart": True}).status_code == 401
    assert client.post("/api/admin/refresh-data/cancel").status_code == 401


def test_refresh_start_and_status(client, monkeypatch):
    def noop() -> None:
        pass

    monkeypatch.setattr("src.download_house_fd.download_house_fd_bulk", lambda *a, **k: [])
    monkeypatch.setattr("src.ingest_house.ingest_house", noop)
    monkeypatch.setattr("src.ingest_senate.ingest_senate", noop)

    _login(client)

    start = client.post("/api/admin/refresh-data", json={"restart": True})
    assert start.status_code == 200
    data = start.json()
    assert data["status"] in {"running", "succeeded"}
    for key in ("started_at", "finished_at", "current_step", "progress", "log_tail", "result"):
        assert key in data

    status = client.get("/api/admin/refresh-data/status")
    assert status.status_code == 200
    assert status.json()["status"] in {"running", "succeeded", "failed", "cancelled"}


def test_refresh_restart_while_running(client, monkeypatch):
    started = threading.Event()
    gate = threading.Event()

    def slow_house() -> None:
        started.set()
        assert gate.wait(timeout=5)

    monkeypatch.setattr("src.download_house_fd.download_house_fd_bulk", lambda *a, **k: [])
    monkeypatch.setattr("src.ingest_house.ingest_house", slow_house)
    monkeypatch.setattr("src.ingest_senate.ingest_senate", lambda: None)

    _login(client)

    first = client.post("/api/admin/refresh-data", json={"restart": True})
    assert first.status_code == 200
    assert started.wait(timeout=5)

    second = client.post("/api/admin/refresh-data", json={"restart": True})
    assert second.status_code == 200
    assert second.json()["status"] == "running"

    gate.set()

    deadline = time.time() + 15
    while time.time() < deadline:
        snap = client.get("/api/admin/refresh-data/status").json()
        if snap["status"] == "succeeded":
            break
        time.sleep(0.05)
    assert client.get("/api/admin/refresh-data/status").json()["status"] == "succeeded"


def test_refresh_cancel_endpoint(client, monkeypatch):
    started = threading.Event()
    gate = threading.Event()

    def slow_house() -> None:
        started.set()
        assert gate.wait(timeout=5)

    monkeypatch.setattr("src.download_house_fd.download_house_fd_bulk", lambda *a, **k: [])
    monkeypatch.setattr("src.ingest_house.ingest_house", slow_house)
    monkeypatch.setattr("src.ingest_senate.ingest_senate", lambda: None)

    _login(client)
    client.post("/api/admin/refresh-data", json={"restart": True})
    assert started.wait(timeout=5)

    cancel = client.post("/api/admin/refresh-data/cancel")
    assert cancel.status_code == 200
    gate.set()

    deadline = time.time() + 10
    while time.time() < deadline:
        if client.get("/api/admin/refresh-data/status").json()["status"] == "cancelled":
            break
        time.sleep(0.05)
    assert client.get("/api/admin/refresh-data/status").json()["status"] == "cancelled"
