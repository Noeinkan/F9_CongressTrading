"""In-process background job runner for admin ingest tasks."""
from __future__ import annotations

import sys
import threading
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

JobStatus = Literal["idle", "running", "succeeded", "failed", "cancelled"]

_LOG_MAX_LINES = 500
_LOG_TAIL_SIZE = 50


class CancelledError(Exception):
    """Raised when a job observes a cancel signal between coarse steps."""


@dataclass
class JobState:
    status: JobStatus = "idle"
    started_at: str | None = None
    finished_at: str | None = None
    current_step: str = ""
    progress: int = 0
    log_lines: deque[str] = field(default_factory=lambda: deque(maxlen=_LOG_MAX_LINES))
    result: dict[str, Any] = field(default_factory=dict)


class _TeeStdout:
    """Mirror stdout to the original stream and a capped job log buffer."""

    def __init__(self, original: Any, log_lines: deque[str]) -> None:
        self.original = original
        self.log_lines = log_lines
        self._buffer = ""

    def write(self, text: str) -> int:
        self.original.write(text)
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line:
                self.log_lines.append(line)
        return len(text)

    def flush(self) -> None:
        self.original.flush()
        if self._buffer:
            self.log_lines.append(self._buffer)
            self._buffer = ""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_cancel(cancel_event: threading.Event) -> None:
    if cancel_event.is_set():
        raise CancelledError()


def run_ingest_all(state: JobState, cancel_event: threading.Event, *, overwrite: bool = False) -> None:
    """Download House FD metadata, then run House + Senate ingest."""
    original_stdout = sys.stdout
    tee = _TeeStdout(original_stdout, state.log_lines)
    sys.stdout = tee
    try:
        from datetime import datetime

        from ..config import START_YEAR
        from ..download_house_fd import download_house_fd_bulk

        state.current_step = "download-house-fd"
        state.progress = 5
        _check_cancel(cancel_event)

        years = list(range(START_YEAR, datetime.now().year + 1))
        completed_years = download_house_fd_bulk(years, overwrite=overwrite, extract=True)
        state.result = {"download_years": completed_years, "overwrite": overwrite}

        state.progress = 15
        state.current_step = "ingest-house"
        _check_cancel(cancel_event)

        from ..ingest_house import ingest_house

        ingest_house()

        state.progress = 65
        state.current_step = "ingest-senate"
        _check_cancel(cancel_event)

        from ..ingest_senate import ingest_senate

        ingest_senate()

        state.progress = 100
        state.current_step = "done"
        state.result = {"scope": "ingest-all", "download_years": completed_years}
    finally:
        sys.stdout = original_stdout
        tee.flush()


class JobManager:
    """Single-slot job runner with cancel + restart semantics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = JobState()
        self._cancel_event = threading.Event()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingest-job")
        self._future: Future[None] | None = None
        self._run_id = 0

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot()

    def start_or_restart(self, *, overwrite: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._state.status == "running":
                self._cancel_event.set()
            self._cancel_event = threading.Event()
            cancel_event = self._cancel_event
            run_id = self._run_id + 1
            self._run_id = run_id
            new_state = JobState(
                status="running",
                started_at=_utc_now_iso(),
                current_step="starting",
                progress=0,
            )
            self._state = new_state
            self._future = self._executor.submit(
                self._run_wrapper,
                run_id,
                new_state,
                cancel_event,
                overwrite,
            )
            return self._snapshot()

    def cancel(self) -> dict[str, Any]:
        with self._lock:
            if self._state.status != "running":
                return self._snapshot()
            self._cancel_event.set()
            return self._snapshot()

    def _snapshot(self) -> dict[str, Any]:
        state = self._state
        return {
            "status": state.status,
            "started_at": state.started_at,
            "finished_at": state.finished_at,
            "current_step": state.current_step,
            "progress": state.progress,
            "log_tail": list(state.log_lines)[-_LOG_TAIL_SIZE:],
            "log_lines": list(state.log_lines),
            "result": dict(state.result),
        }

    def _run_wrapper(
        self,
        run_id: int,
        state: JobState,
        cancel_event: threading.Event,
        overwrite: bool = False,
    ) -> None:
        try:
            run_ingest_all(state, cancel_event, overwrite=overwrite)
            with self._lock:
                if self._run_id != run_id:
                    return
                state.status = "cancelled" if cancel_event.is_set() else "succeeded"
                state.finished_at = _utc_now_iso()
        except CancelledError:
            with self._lock:
                if self._run_id != run_id:
                    return
                state.status = "cancelled"
                state.finished_at = _utc_now_iso()
        except Exception as exc:
            with self._lock:
                if self._run_id != run_id:
                    return
                state.status = "failed"
                state.finished_at = _utc_now_iso()
                state.result = {"error": str(exc)}
                state.log_lines.append(f"ERROR: {exc}")


job_manager = JobManager()
