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

    def fake_download(
        years,
        *,
        overwrite=False,
        extract=True,
        force_extract=False,
        force_years=None,
        cancel_event=None,
        progress_hook=None,
    ):
        fy = sorted(force_years or [])
        calls.append(f"download:{years}:{overwrite}:{force_extract}:{fy}")
        if progress_hook is not None:
            progress_hook("Downloading House FD metadata", 0, len(years), unit="years")
            for i, _year in enumerate(years):
                progress_hook(f"House FD {_year}", i + 1, len(years), unit="years")
        return years

    def fake_house(cancel_event=None, progress_hook=None) -> None:
        calls.append("house")
        if progress_hook is not None:
            progress_hook("Parsing House PTR PDFs", 3, 10, unit="PDFs")

    def fake_senate(cancel_event=None, progress_hook=None) -> None:
        calls.append("senate")
        if progress_hook is not None:
            progress_hook("Parsing Senate PTR PDFs", 1, 2, unit="PDFs")

    monkeypatch.setattr("src.download_house_fd.download_house_fd_bulk", fake_download)
    monkeypatch.setattr("src.ingest_house.ingest_house", fake_house)
    monkeypatch.setattr("src.ingest_senate.ingest_senate", fake_senate)


def _patch_oge(monkeypatch, calls: list[str], *, download_returns: tuple[int, int] = (0, 0)) -> None:
    """Patch the two OGE entrypoints to record call order."""

    def fake_oge_download(
        *,
        filer_name=None,
        dest_dir=None,
        min_interval_seconds=None,
        overwrite=False,
        progress_hook=None,
    ):
        calls.append(f"oge_download:overwrite={overwrite}")
        if progress_hook is not None:
            progress_hook("Downloading OGE filings", 1, 1, unit="filings")
        return download_returns

    def fake_oge_ingest(filer_name=None, cancel_event=None, progress_hook=None, force_reparse=False):
        calls.append(f"oge_ingest:force_reparse={force_reparse}")
        if progress_hook is not None:
            progress_hook("Parsing OGE PDFs", 1, 1, unit="PDFs")

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
    # default behaviour: overwrite=False, force_extract=False; current year is
    # force-refreshed via force_years so new PTR filings are discovered.
    assert ":False:False:" in calls[0]
    assert final["result"]["force_years"]  # at least the current calendar year
    from datetime import datetime

    assert datetime.now().year in final["result"]["force_years"]
    # OGE is part of the default pipeline now and runs after senate.
    assert any(c.startswith("oge_download") for c in calls)
    assert "oge_ingest:force_reparse=False" in calls
    # The full order is: download -> house -> senate -> oge_download -> oge_ingest.
    assert calls.index("senate") < calls.index("oge_download:overwrite=False") < calls.index(
        "oge_ingest:force_reparse=False"
    )
    # OGE summary recorded on the job state.
    assert final["result"]["oge_download"]["downloaded"] == 0
    assert final["result"]["oge_download"]["already_present"] == 0
    assert "registered" in final["result"]["oge_download"]["registry"]


def test_refresh_default_skips_force_reparse(monkeypatch):
    """The admin refresh button must default to force_reparse=False so that
    a normal Refresh only touches new/changed PDFs (the (path, sha256)
    dedup in ingested_files skips everything else). Setting force_reparse
    re-processes every PDF; that's an explicit, opt-in choice."""
    # Ensure no leftover env var from a previous test in the same process.
    monkeypatch.delenv("HOUSE_INGEST_FORCE_REPARSE_PDFS", raising=False)
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
    assert final["result"]["force_reparse"] is False
    assert os.environ.get("HOUSE_INGEST_FORCE_REPARSE_PDFS") != "1"


def test_refresh_force_reparse_true_scopes_and_restores_env(monkeypatch):
    """Opt-in force_reparse=True must set HOUSE_INGEST_FORCE_REPARSE_PDFS=1
    during ingest, then restore the previous env so a later Refresh cannot
    leak into a full re-parse of every PDF on disk."""
    monkeypatch.delenv("HOUSE_INGEST_FORCE_REPARSE_PDFS", raising=False)
    calls: list[str] = []
    seen_during_house: list[str | None] = []

    def fake_download(
        years,
        *,
        overwrite=False,
        extract=True,
        force_extract=False,
        force_years=None,
        cancel_event=None,
        progress_hook=None,
    ):
        calls.append(f"download:{years}:{overwrite}:{force_extract}:{sorted(force_years or [])}")
        return years

    def fake_house(cancel_event=None, progress_hook=None) -> None:
        seen_during_house.append(os.environ.get("HOUSE_INGEST_FORCE_REPARSE_PDFS"))
        calls.append("house")

    def fake_senate(cancel_event=None, progress_hook=None) -> None:
        calls.append("senate")

    monkeypatch.setattr("src.download_house_fd.download_house_fd_bulk", fake_download)
    monkeypatch.setattr("src.ingest_house.ingest_house", fake_house)
    monkeypatch.setattr("src.ingest_senate.ingest_senate", fake_senate)
    _patch_oge(monkeypatch, calls)

    manager = JobManager()
    manager.start_or_restart(force_reparse=True)

    deadline = time.time() + 10
    while time.time() < deadline:
        if manager.get_state()["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.05)

    final = manager.get_state()
    assert final["status"] == "succeeded"
    assert final["result"]["force_reparse"] is True
    assert seen_during_house == ["1"]
    # Env must be restored after the job — no sticky force-reparse.
    assert os.environ.get("HOUSE_INGEST_FORCE_REPARSE_PDFS") != "1"
    assert os.environ.get("OGE_INGEST_FORCE_REPARSE_PDFS") != "1"
    assert "oge_ingest:force_reparse=True" in calls

    # A subsequent default Refresh must not re-enable the env during ingest.
    seen_during_house.clear()
    manager2 = JobManager()
    manager2.start_or_restart()
    deadline = time.time() + 10
    while time.time() < deadline:
        if manager2.get_state()["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.05)
    assert manager2.get_state()["status"] == "succeeded"
    assert seen_during_house == [None]
    assert os.environ.get("HOUSE_INGEST_FORCE_REPARSE_PDFS") != "1"


def test_refresh_forces_current_year_fd_catalog(monkeypatch):
    """Default Refresh must pass force_years containing the current year so
    the Clerk catalog is re-fetched even when overwrite=False."""
    from datetime import datetime

    from src.download_house_fd import house_fd_refresh_force_years

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
    expected = sorted(house_fd_refresh_force_years(datetime.now()))
    assert final["result"]["force_years"] == expected
    assert f":{expected}" in calls[0]


def test_house_fd_refresh_force_years_includes_prior_early_year():
    from datetime import datetime

    from src.download_house_fd import house_fd_refresh_force_years

    assert house_fd_refresh_force_years(datetime(2026, 7, 30)) == {2026}
    assert house_fd_refresh_force_years(datetime(2026, 2, 15)) == {2025, 2026}
    assert house_fd_refresh_force_years(datetime(2026, 1, 5)) == {2025, 2026}


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
    # Fake format: "download:{years}:{overwrite}:{force_extract}:{force_years}"
    # overwrite=True clears force_years (global overwrite covers all years).
    assert calls and ":True:False:[]" in calls[0]
    assert manager.get_state()["result"]["force_years"] == []
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
    # Fake format ends with overwrite:force_extract:force_years.
    assert ":False:True:" in calls[0]
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

    def exploding_oge_download(*, filer_name=None, dest_dir=None, min_interval_seconds=None, overwrite=False, progress_hook=None):
        raise RuntimeError("OGE doc_id XYZ returned 404")

    def fake_oge_ingest(filer_name=None, cancel_event=None, progress_hook=None, force_reparse=False):
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

    def slow_house(cancel_event=None, progress_hook=None) -> None:
        entered_house.set()
        assert release_house.wait(timeout=5)

    def fake_senate(cancel_event=None, progress_hook=None) -> None:
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


def test_progress_emits_sub_counts(monkeypatch):
    """Progress hooks must surface sub_done/sub_total on the job snapshot."""
    calls: list[str] = []
    _patch_house_senate(monkeypatch, calls)
    _patch_oge(monkeypatch, calls)

    manager = JobManager()
    manager.start_or_restart()

    saw_sub_counts = False
    deadline = time.time() + 10
    while time.time() < deadline:
        snap = manager.get_state()
        if snap.get("sub_total", 0) > 0 and snap.get("sub_done", 0) > 0:
            saw_sub_counts = True
        if snap["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.02)

    final = manager.get_state()
    assert final["status"] == "succeeded"
    assert saw_sub_counts, "expected sub_done/sub_total to be populated during the run"
    assert final["phase_total"] == 5
    assert final["sub_unit"] in {"years", "PDFs", "filings", "PTR files", "batches", ""}


def test_eta_is_computed_when_progress_advances(monkeypatch):
    """ETA should be set once enough elapsed time and partial progress exist."""
    from datetime import datetime, timedelta, timezone

    import src.api.jobs as jobs_mod

    fixed_now = datetime(2026, 1, 1, 12, 0, 10, tzinfo=timezone.utc)
    step_started = (fixed_now - timedelta(seconds=5)).isoformat()

    state = jobs_mod.JobState(
        current_step="ingest-house",
        step_started_at=step_started,
        phase_index=1,
        phase_total=5,
    )

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz else fixed_now.replace(tzinfo=None)

    monkeypatch.setattr(jobs_mod, "datetime", _FixedDateTime)

    jobs_mod._emit_progress(
        state,
        phase="ingest-house",
        phase_label="Ingesting House PTRs",
        phase_index=1,
        phase_total=5,
        progress_start=15,
        progress_span=50,
        label="Parsing House PTR PDFs",
        done=5,
        total=10,
        unit="PDFs",
    )

    assert state.sub_done == 5
    assert state.sub_total == 10
    assert state.eta_seconds is not None
    assert state.eta_seconds > 0


def test_refresh_status_requires_auth(client):
    assert client.get("/api/admin/refresh-data/status").status_code == 401
    assert client.post("/api/admin/refresh-data", json={"restart": True}).status_code == 401
    assert client.post("/api/admin/refresh-data", json={"restart": True, "overwrite": True}).status_code == 401
    assert client.post("/api/admin/refresh-data", json={"restart": True, "force_extract": True}).status_code == 401
    assert client.post("/api/admin/refresh-data", json={"restart": True, "skip_senate": True}).status_code == 401
    assert client.post("/api/admin/refresh-data", json={"restart": True, "skip_oge": True}).status_code == 401
    assert client.post("/api/admin/refresh-data/cancel").status_code == 401


# --- /api/admin/deploy -----------------------------------------------------

import subprocess as _subprocess  # noqa: E402  (kept local to test file)


class _FakePopen:
    """Minimal Popen double for tests. Configurable via the factory below."""

    instances: list["_FakePopen"] = []

    def __init__(self, *, returncode: int = 0, lines: list[str] | None = None) -> None:
        self.returncode = returncode
        self._lines = lines or ["hello from deploy.sh\n"]
        self.stdout = iter(self._lines)
        self.terminate_called = False
        self.kill_called = False
        self.wait_called = 0
        self.args: tuple | None = None
        self.cwd: str | None = None
        self.env: dict | None = None
        _FakePopen.instances.append(self)

    def wait(self, timeout=None):  # noqa: ARG002 — Popen signature
        self.wait_called += 1
        return self.returncode

    def terminate(self) -> None:
        self.terminate_called = True

    def kill(self) -> None:
        self.kill_called = True


def _patch_popen(monkeypatch, *, returncode: int = 0, lines: list[str] | None = None) -> list[_FakePopen]:
    """Patch src.api.jobs.subprocess.Popen to return a controllable fake.

    Returns the list of fakes created during the test (so the test can inspect
    what was passed to Popen).
    """
    _FakePopen.instances = []

    def factory(argv, **kwargs):
        fake = _FakePopen(returncode=returncode, lines=lines)
        fake.args = tuple(argv)
        fake.cwd = kwargs.get("cwd")
        fake.env = kwargs.get("env")
        return fake

    monkeypatch.setattr("src.api.jobs.subprocess.Popen", factory)
    return _FakePopen.instances


def test_deploy_endpoints_require_auth(client):
    assert client.get("/api/admin/deploy/status").status_code == 401
    assert client.post("/api/admin/deploy").status_code == 401
    assert client.post("/api/admin/deploy", json={"skip_frontend": True}).status_code == 401
    assert client.post("/api/admin/deploy/cancel").status_code == 401


def test_deploy_start_runs_script_and_reports_success(client, monkeypatch):
    instances = _patch_popen(monkeypatch, returncode=0)
    _login(client)

    r = client.post("/api/admin/deploy")
    assert r.status_code == 200
    snap = r.json()
    assert snap["status"] in {"running", "succeeded"}
    for key in (
        "started_at",
        "finished_at",
        "current_step",
        "progress",
        "phase_label",
        "log_tail",
        "log_lines",
        "result",
    ):
        assert key in snap

    # Wait for completion (the wrapper exits as soon as the fake stdout iter ends).
    deadline = time.time() + 5
    while time.time() < deadline:
        if client.get("/api/admin/deploy/status").json()["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.02)

    final = client.get("/api/admin/deploy/status").json()
    assert final["status"] == "succeeded"
    assert final["progress"] == 100
    assert final["result"]["scope"] == "deploy"
    assert final["result"]["return_code"] == 0
    assert final["result"]["skip_frontend"] is False
    assert final["result"]["skip_restart"] is False

    assert len(instances) == 1
    assert instances[0].args[0] == "bash"
    assert str(instances[0].args[1]).replace("\\", "/").endswith("deploy/deploy.sh")
    assert "SKIP_FRONTEND" not in (instances[0].env or {})
    assert "SKIP_RESTART" not in (instances[0].env or {})


def test_deploy_start_forwards_skip_flags(client, monkeypatch):
    instances = _patch_popen(monkeypatch, returncode=0)
    _login(client)

    r = client.post("/api/admin/deploy", json={"skip_frontend": True, "skip_restart": True})
    assert r.status_code == 200

    deadline = time.time() + 5
    while time.time() < deadline:
        if client.get("/api/admin/deploy/status").json()["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.02)

    assert client.get("/api/admin/deploy/status").json()["status"] == "succeeded"
    assert len(instances) == 1
    assert instances[0].env.get("SKIP_FRONTEND") == "1"
    assert instances[0].env.get("SKIP_RESTART") == "1"


def test_deploy_start_fails_when_script_exits_nonzero(client, monkeypatch):
    _patch_popen(monkeypatch, returncode=2)
    _login(client)

    r = client.post("/api/admin/deploy")
    assert r.status_code == 200

    deadline = time.time() + 5
    while time.time() < deadline:
        if client.get("/api/admin/deploy/status").json()["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.02)

    final = client.get("/api/admin/deploy/status").json()
    assert final["status"] == "failed"
    assert "exited with code 2" in final["result"]["error"]


def test_deploy_cancel_terminates_subprocess(client, monkeypatch):
    """When the client hits /api/admin/deploy/cancel mid-run, the subprocess
    must be terminated and the job must end as 'cancelled' (not 'succeeded').

    The fake Popen below mimics the real-world behaviour the production
    code relies on: terminate() closes the child's stdout, the read loop
    sees EOF, and the wrapper observes cancel_event.is_set() and raises
    CancelledError. This is what makes the test exercise the actual
    cancellation path rather than a busy-wait.
    """
    import src.api.jobs as jobs_mod

    # The fake stdout is a generator that yields N lines then terminates,
    # which is what the wrapper sees after terminate() in real subprocesses
    # (the OS closes the pipe, EOF arrives, the iterator stops).
    class _CancellablePopen:
        def __init__(self, argv, **kwargs):
            self.args = argv
            self.env = kwargs.get("env")
            self.cwd = kwargs.get("cwd")
            self.terminate_called = False
            self.kill_called = False
            self._stop = threading.Event()
            self._yielded = 0

            def _iter():
                while not self._stop.is_set():
                    self._yielded += 1
                    yield f"line {self._yielded}\n"

            self.stdout = _iter()

        def wait(self, timeout=None):  # noqa: ARG002
            return -1 if not self._stop.is_set() else 0

        def terminate(self) -> None:
            self.terminate_called = True
            # Closing the producer side is what makes the wrapper's
            # `for line in proc.stdout:` loop exit.
            self._stop.set()

        def kill(self) -> None:
            self.kill_called = True
            self._stop.set()

    blocker = _CancellablePopen([])
    monkeypatch.setattr(jobs_mod.subprocess, "Popen", lambda argv, **kw: blocker)

    _login(client)
    client.post("/api/admin/deploy")
    # Let the wrapper enter its read loop and pull a line or two.
    time.sleep(0.1)
    cancel = client.post("/api/admin/deploy/cancel")
    assert cancel.status_code == 200

    deadline = time.time() + 5
    while time.time() < deadline:
        if client.get("/api/admin/deploy/status").json()["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.02)

    final = client.get("/api/admin/deploy/status").json()
    assert final["status"] == "cancelled", final
    assert blocker.terminate_called is True


def test_refresh_start_and_status(client, monkeypatch):
    calls: list[str] = []
    _patch_house_senate(monkeypatch, calls)
    _patch_oge(monkeypatch, calls)

    _login(client)

    start = client.post("/api/admin/refresh-data", json={"restart": True})
    assert start.status_code == 200
    data = start.json()
    assert data["status"] in {"running", "succeeded"}
    for key in (
        "started_at",
        "finished_at",
        "current_step",
        "progress",
        "phase_label",
        "phase_index",
        "phase_total",
        "sub_progress",
        "sub_done",
        "sub_total",
        "sub_unit",
        "eta_seconds",
        "step_started_at",
        "log_tail",
        "log_lines",
        "result",
    ):
        assert key in data

    status = client.get("/api/admin/refresh-data/status")
    assert status.status_code == 200
    assert status.json()["status"] in {"running", "succeeded", "failed", "cancelled"}


def test_refresh_restart_while_running(client, monkeypatch):
    started = threading.Event()
    gate = threading.Event()

    def slow_house(cancel_event=None, progress_hook=None) -> None:
        started.set()
        assert gate.wait(timeout=5)

    monkeypatch.setattr("src.download_house_fd.download_house_fd_bulk", lambda *a, **k: [])
    monkeypatch.setattr("src.ingest_house.ingest_house", slow_house)
    monkeypatch.setattr("src.ingest_senate.ingest_senate", lambda cancel_event=None, progress_hook=None: None)
    monkeypatch.setattr("src.download_oge.download_oge_filings", lambda *a, **k: (0, 0))
    monkeypatch.setattr("src.ingest_oge.ingest_oge", lambda cancel_event=None, filer_name=None, progress_hook=None, force_reparse=False: None)

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

    def slow_house(cancel_event=None, progress_hook=None) -> None:
        started.set()
        assert gate.wait(timeout=5)

    monkeypatch.setattr("src.download_house_fd.download_house_fd_bulk", lambda *a, **k: [])
    monkeypatch.setattr("src.ingest_house.ingest_house", slow_house)
    monkeypatch.setattr("src.ingest_senate.ingest_senate", lambda cancel_event=None, progress_hook=None: None)
    monkeypatch.setattr("src.download_oge.download_oge_filings", lambda *a, **k: (0, 0))
    monkeypatch.setattr("src.ingest_oge.ingest_oge", lambda cancel_event=None, filer_name=None, progress_hook=None, force_reparse=False: None)

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


def test_job_manager_cancelled_when_ingest_house_raises_cancelled(monkeypatch):
    """Regression: if ingest_house observes the cancel_event mid-run and raises
    CancelledError, the job status must end as 'cancelled' — not 'succeeded'
    and not 'failed'. This is the dashboard 'Cancel' button bug fix.
    """
    from src.api.jobs import CancelledError

    started = threading.Event()

    def canceling_house(cancel_event=None, progress_hook=None):
        started.set()
        # Mimic the real behavior: house loop notices the cancel signal and
        # raises immediately. Real ingest_house raises CancelledError from
        # _check_cancel between batches.
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError()
        assert cancel_event is not None
        cancel_event.wait(timeout=5)
        raise CancelledError()

    monkeypatch.setattr("src.download_house_fd.download_house_fd_bulk", lambda *a, **k: [])
    monkeypatch.setattr("src.ingest_house.ingest_house", canceling_house)
    monkeypatch.setattr("src.ingest_senate.ingest_senate", lambda *a, **k: pytest.fail("senate"))
    monkeypatch.setattr("src.download_oge.download_oge_filings", lambda *a, **k: (0, 0))
    monkeypatch.setattr("src.ingest_oge.ingest_oge", lambda *a, **k: pytest.fail("oge"))

    manager = JobManager()
    manager.start_or_restart()
    assert started.wait(timeout=5)
    manager.cancel()

    deadline = time.time() + 10
    while time.time() < deadline:
        snap = manager.get_state()
        if snap["status"] in {"cancelled", "failed", "succeeded"}:
            break
        time.sleep(0.05)

    final = manager.get_state()
    assert final["status"] == "cancelled", (
        f"expected cancelled, got {final['status']!r} "
        f"(this is the dashboard Cancel-button bug)"
    )


def test_cancel_event_is_passed_to_ingest_callables(monkeypatch):
    """Regression: cancel_event must be forwarded to the long-running ingest
    callables so their internal _check_cancel() calls can observe it. Without
    this the 'Cancel' button is a no-op for the heavy phases (House FD
    bulk download + re-parse, Senate PDF parsing, OGE PDF parsing).
    """
    captured: dict[str, threading.Event | None] = {}

    def record(name, fn):
        def wrapper(*args, **kwargs):
            cancel = kwargs.get("cancel_event")
            if cancel is None and args:
                cancel = args[0]
            captured[name] = cancel
            return fn(*args, **kwargs)

        return wrapper

    monkeypatch.setattr("src.download_house_fd.download_house_fd_bulk",
                        record("download_house_fd_bulk", lambda *a, **k: []))
    monkeypatch.setattr("src.ingest_house.ingest_house",
                        record("ingest_house", lambda cancel_event=None, progress_hook=None: None))
    monkeypatch.setattr("src.ingest_senate.ingest_senate",
                        record("ingest_senate", lambda cancel_event=None, progress_hook=None: None))
    monkeypatch.setattr("src.download_oge.download_oge_filings",
                        record("download_oge_filings", lambda *a, **k: (0, 0)))
    monkeypatch.setattr("src.ingest_oge.ingest_oge",
                        record("ingest_oge", lambda cancel_event=None, filer_name=None, progress_hook=None, force_reparse=False: None))

    manager = JobManager()
    manager.start_or_restart()

    deadline = time.time() + 10
    while time.time() < deadline:
        if manager.get_state()["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.05)

    # All long-running ingest callables must receive a cancel_event. The OGE
    # downloader (download_oge_filings) is a fast registry fetch with
    # ~few-second latency — not currently plumbed through the cancel signal,
    # by design.
    for name in (
        "download_house_fd_bulk",
        "ingest_house",
        "ingest_senate",
        "ingest_oge",
    ):
        assert name in captured, f"{name} was never called"
        assert captured[name] is not None, (
            f"{name} did not receive a cancel_event — Cancel button will be a no-op"
        )


def test_run_ingest_all_propagates_cancelled_from_ingest(monkeypatch):
    """If a downstream ingest function (e.g. ingest_house) raises CancelledError,
    run_ingest_all must propagate it so the job wrapper records 'cancelled'
    instead of swallowing it as 'succeeded'.
    """
    from src.api.jobs import CancelledError

    state = __import__("src.api.jobs", fromlist=["JobState"]).JobState()
    cancel = threading.Event()
    cancel.set()  # cancel signal is already present

    def fake_house(cancel_event=None, progress_hook=None):
        # Real ingest_house would raise CancelledError before doing any work
        # because _check_cancel fires at the top of the function.
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError()

    monkeypatch.setattr("src.download_house_fd.download_house_fd_bulk", lambda *a, **k: [])
    monkeypatch.setattr("src.ingest_house.ingest_house", fake_house)

    with pytest.raises(CancelledError):
        run_ingest_all(state, cancel)
