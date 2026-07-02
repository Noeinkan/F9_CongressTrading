"""Tests for admin refresh-data background ingest job."""
from __future__ import annotations

import os
import threading
import time

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.jobs import CancelledError, JobManager, run_ingest_all


# --- shared fakes ---------------------------------------------------------

def _patch_house_senate(monkeypatch, calls: list[str]) -> None:
    """Patch the original three pipeline entrypoints to record call order."""

    def fake_download(years, *, overwrite=False, extract=True, force_extract=False):
        calls.append(f"download:{years}:{overwrite}:{force_extract}")
        return years

    def fake_house() -> None:
        calls.append("house")

    def fake_senate() -> None:
        calls.append("senate")

    monkeypatch.setattr("src.download_house_fd.download_house_fd_bulk", fake_download)
    monkeypatch.setattr("src.ingest_house.ingest_house", fake_house)
    monkeypatch.setattr("src.ingest_senate.ingest_senate", fake_senate)


def _patch_oge(monkeypatch, calls: list[str], *, download_returns: tuple[int, int] = (0, 0)) -> None:
    """Patch the two OGE entrypoints to record call order."""

    def fake_oge_download(*, filer_name=None, dest_dir=None, min_interval_seconds=None, overwrite=False):
        calls.append(f"oge_download:overwrite={overwrite}")
        return download_returns

    def fake_oge_ingest(filer_name=None):
        calls.append("oge_ingest")

    monkeypatch.setattr("src.download_oge.download_oge_filings", fake_oge_download)
    monkeypatch.setattr("src.ingest_oge.ingest_oge", fake_oge_ingest)


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
    _patch_house_senate(monkeypatch, calls)
    _patch_oge(monkeypatch, calls)

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
    # default behaviour: overwrite=False, force_extract=False
    assert ":False:False" in calls[0]
    # OGE is part of the default pipeline now and runs after senate.
    assert any(c.startswith("oge_download") for c in calls)
    assert "oge_ingest" in calls
    # OGE download should default to overwrite=False (don't re-hammer the registry).
    assert "oge_download:overwrite=False" in calls
    # The full order is: download -> house -> senate -> oge_download -> oge_ingest.
    assert calls.index("senate") < calls.index("oge_download:overwrite=False") < calls.index("oge_ingest")
    # OGE summary recorded on the job state.
    assert final["result"]["oge_download"]["downloaded"] == 0
    assert final["result"]["oge_download"]["already_present"] == 0
    assert "registered" in final["result"]["oge_download"]["registry"]


def test_refresh_default_enables_force_reparse(monkeypatch):
    """The admin refresh button must default to force_reparse=True so that
    every PDF on disk is re-parsed; otherwise the (path, sha256) dedup in
    ingested_files silently masks every previously-ingested PTR."""
    calls: list[str] = []
    _patch_house_senate(monkeypatch, calls)
    _patch_oge(monkeypatch, calls)

    manager = JobManager()
    manager.start_or_restart()

    deadline = time.time() + 10
    while time.time() < deadline:
        if manager.get_state()["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.05)

    final = manager.get_state()
    assert final["status"] == "succeeded"
    assert final["result"]["force_reparse"] is True
    assert os.environ.get("HOUSE_INGEST_FORCE_REPARSE_PDFS") == "1"


def test_job_manager_propagates_overwrite_true(monkeypatch):
    calls: list[str] = []
    _patch_house_senate(monkeypatch, calls)
    _patch_oge(monkeypatch, calls)

    manager = JobManager()
    manager.start_or_restart(overwrite=True)

    deadline = time.time() + 10
    while time.time() < deadline:
        snap = manager.get_state()
        if snap["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.05)

    assert manager.get_state()["status"] == "succeeded"
    # Fake format: "download:{years}:{overwrite}:{force_extract}" so
    # overwrite=True, force_extract=False ends as "]:True:False".
    assert calls and calls[0].endswith(":True:False")
    assert "oge_download:overwrite=False" in calls


def test_job_manager_propagates_force_extract_and_skip_senate(monkeypatch):
    calls: list[str] = []
    _patch_house_senate(monkeypatch, calls)
    _patch_oge(monkeypatch, calls)

    manager = JobManager()
    manager.start_or_restart(force_extract=True, skip_senate=True)

    deadline = time.time() + 10
    while time.time() < deadline:
        snap = manager.get_state()
        if snap["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.05)

    final = manager.get_state()
    assert final["status"] == "succeeded"
    # Fake format ends with the two booleans: "]:{overwrite}:{force_extract}".
    assert calls[0].endswith(":False:True")
    assert "house" in calls
    # skip_senate short-circuits the pipeline — OGE must not run.
    assert "oge_download" not in calls
    assert "oge_ingest" not in calls
    assert final["result"]["scope"] == "ingest-house-only"
    assert final["result"]["skip_senate"] is True
    assert final["result"]["force_extract"] is True


def test_job_manager_skip_oge_runs_senate_only(monkeypatch):
    """skip_oge=True must keep senate but skip the OGE download + ingest."""
    calls: list[str] = []
    _patch_house_senate(monkeypatch, calls)
    _patch_oge(monkeypatch, calls)

    manager = JobManager()
    manager.start_or_restart(skip_oge=True)

    deadline = time.time() + 10
    while time.time() < deadline:
        snap = manager.get_state()
        if snap["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.05)

    final = manager.get_state()
    assert final["status"] == "succeeded"
    assert "senate" in calls
    assert "oge_download" not in calls
    assert "oge_ingest" not in calls
    assert final["result"]["scope"] == "ingest-all-no-oge"
    assert final["result"]["oge_skipped"] is True


def test_job_manager_oge_progress_reaches_100(monkeypatch):
    """After a successful OGE run, progress must be 100% and the final
    step must be 'done' — i.e. the OGE block does not leave the job stuck
    at 90%."""
    calls: list[str] = []
    _patch_house_senate(monkeypatch, calls)
    _patch_oge(monkeypatch, calls, download_returns=(3, 5))

    manager = JobManager()
    manager.start_or_restart()

    deadline = time.time() + 10
    while time.time() < deadline:
        snap = manager.get_state()
        if snap["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.05)

    final = manager.get_state()
    assert final["status"] == "succeeded"
    assert final["progress"] == 100
    assert final["current_step"] == "done"
    assert final["result"]["oge_download"]["downloaded"] == 3
    assert final["result"]["oge_download"]["already_present"] == 5


def test_job_manager_oge_download_error_does_not_fail_job(monkeypatch):
    """A 404 from the OGE registry (or any download error) must be logged
    and surfaced on the result, but must not flip the whole refresh to
    'failed' — the OGE ingest still gets a chance to process whatever is
    already on disk."""
    calls: list[str] = []
    _patch_house_senate(monkeypatch, calls)

    def exploding_oge_download(*, filer_name=None, dest_dir=None, min_interval_seconds=None, overwrite=False):
        raise RuntimeError("OGE doc_id XYZ returned 404")

    def fake_oge_ingest(filer_name=None):
        calls.append("oge_ingest")

    monkeypatch.setattr("src.download_oge.download_oge_filings", exploding_oge_download)
    monkeypatch.setattr("src.ingest_oge.ingest_oge", fake_oge_ingest)

    manager = JobManager()
    manager.start_or_restart()

    deadline = time.time() + 10
    while time.time() < deadline:
        snap = manager.get_state()
        if snap["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.05)

    final = manager.get_state()
    assert final["status"] == "succeeded"
    assert "oge_ingest" in calls
    assert "404" in final["result"]["oge_download"].get("error", "")


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
    assert client.post("/api/admin/refresh-data", json={"restart": True, "overwrite": True}).status_code == 401
    assert client.post("/api/admin/refresh-data", json={"restart": True, "force_extract": True}).status_code == 401
    assert client.post("/api/admin/refresh-data", json={"restart": True, "skip_senate": True}).status_code == 401
    assert client.post("/api/admin/refresh-data", json={"restart": True, "skip_oge": True}).status_code == 401
    assert client.post("/api/admin/refresh-data/cancel").status_code == 401


def test_refresh_start_and_status(client, monkeypatch):
    calls: list[str] = []
    _patch_house_senate(monkeypatch, calls)
    _patch_oge(monkeypatch, calls)

    _login(client)

    start = client.post("/api/admin/refresh-data", json={"restart": True})
    assert start.status_code == 200
    data = start.json()
    assert data["status"] in {"running", "succeeded"}
    for key in ("started_at", "finished_at", "current_step", "progress", "log_tail", "log_lines", "result"):
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
    monkeypatch.setattr("src.download_oge.download_oge_filings", lambda *a, **k: (0, 0))
    monkeypatch.setattr("src.ingest_oge.ingest_oge", lambda: None)

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
    monkeypatch.setattr("src.download_oge.download_oge_filings", lambda *a, **k: (0, 0))
    monkeypatch.setattr("src.ingest_oge.ingest_oge", lambda: None)

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
