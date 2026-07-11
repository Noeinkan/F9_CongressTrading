"""In-process background job runner for admin ingest tasks."""
from __future__ import annotations

import os
import sys
import threading
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal

JobStatus = Literal["idle", "running", "succeeded", "failed", "cancelled"]

ProgressHook = Callable[[str, int, int], None]

_LOG_MAX_LINES = 500
_LOG_TAIL_SIZE = 50

# (step_id, human label, progress_start, progress_span)
_PIPELINE_PHASES: tuple[tuple[str, str, int, int], ...] = (
    ("download-house-fd", "Downloading House FD", 0, 15),
    ("ingest-house", "Ingesting House PTRs", 15, 50),
    ("ingest-senate", "Ingesting Senate PTRs", 65, 15),
    ("download-oge", "Downloading OGE filings", 80, 10),
    ("ingest-oge", "Ingesting OGE filings", 90, 10),
)


class CancelledError(Exception):
    """Raised when a job observes a cancel signal between coarse steps."""


@dataclass
class JobState:
    status: JobStatus = "idle"
    started_at: str | None = None
    finished_at: str | None = None
    current_step: str = ""
    progress: int = 0
    phase_label: str = ""
    phase_index: int = 0
    phase_total: int = len(_PIPELINE_PHASES)
    sub_progress: int = 0
    sub_done: int = 0
    sub_total: int = 0
    sub_unit: str = ""
    eta_seconds: float | None = None
    step_started_at: str | None = None
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


def _begin_phase(
    state: JobState,
    *,
    phase: str,
    phase_label: str,
    phase_index: int,
    phase_total: int,
    progress_start: int,
) -> None:
    state.current_step = phase
    state.phase_label = phase_label
    state.phase_index = phase_index
    state.phase_total = phase_total
    state.step_started_at = _utc_now_iso()
    state.sub_done = 0
    state.sub_total = 0
    state.sub_unit = ""
    state.sub_progress = 0
    state.eta_seconds = None
    state.progress = progress_start


def _emit_progress(
    state: JobState,
    *,
    phase: str,
    phase_label: str,
    phase_index: int,
    phase_total: int,
    progress_start: int,
    progress_span: int,
    label: str,
    done: int,
    total: int,
    unit: str = "",
) -> None:
    if state.current_step != phase:
        _begin_phase(
            state,
            phase=phase,
            phase_label=phase_label,
            phase_index=phase_index,
            phase_total=phase_total,
            progress_start=progress_start,
        )

    state.phase_label = label or phase_label
    state.sub_done = done
    state.sub_total = total
    state.sub_unit = unit

    if total > 0:
        state.sub_progress = min(100, max(0, round(100 * done / total)))
        state.progress = min(
            progress_start + progress_span - 1,
            progress_start + int(progress_span * done / total),
        )
    else:
        state.sub_progress = 0

    if state.step_started_at and done > 0 and total > done:
        try:
            started = datetime.fromisoformat(state.step_started_at)
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            if elapsed > 2:
                state.eta_seconds = elapsed * (total - done) / done
            else:
                state.eta_seconds = None
        except (TypeError, ValueError):
            state.eta_seconds = None
    else:
        state.eta_seconds = None


def _make_progress_hook(
    state: JobState,
    *,
    phase: str,
    phase_label: str,
    phase_index: int,
    phase_total: int,
    progress_start: int,
    progress_span: int,
) -> ProgressHook:
    def hook(label: str, done: int, total: int, *, unit: str = "") -> None:
        _emit_progress(
            state,
            phase=phase,
            phase_label=phase_label,
            phase_index=phase_index,
            phase_total=phase_total,
            progress_start=progress_start,
            progress_span=progress_span,
            label=label,
            done=done,
            total=total,
            unit=unit,
        )

    return hook


def _summarize_house_fd_extract(year: int) -> dict[str, int]:
    """
    Legge il TXT appena estratto per anno `year` e conta righe totali + righe PTR (FilingType=P).
    Usato dal job per dare un feedback chiaro a video su quanti PTR sono stati visti nei metadata.
    """
    import csv as _csv
    from ..config import HOUSE_RAW_DIR

    txt_path = HOUSE_RAW_DIR / f"{year}FD" / f"{year}FD.txt"
    out = {"year": year, "txt_present": int(txt_path.exists()), "rows_total": 0, "rows_ptr": 0}
    if not txt_path.exists():
        return out
    try:
        with txt_path.open("r", encoding="utf-8", errors="replace") as fh:
            reader = _csv.reader(fh, delimiter="\t")
            header = next(reader, None)
            if not header or "FilingType" not in header:
                return out
            type_idx = header.index("FilingType")
            for row in reader:
                if not row:
                    continue
                out["rows_total"] += 1
                if row[type_idx].strip().upper() == "P":
                    out["rows_ptr"] += 1
    except Exception:
        return out
    return out


def _summarize_senate_dir() -> dict[str, Any]:
    """Conta i PDF PTR nella cartella data/raw/senate per dare feedback chiaro all'utente."""
    from pathlib import Path
    from ..config import SENATE_RAW_DIR

    p = Path(SENATE_RAW_DIR)
    if not p.exists():
        return {"dir": str(p), "exists": False, "pdfs": 0, "reason": "directory non presente"}
    pdfs = list(p.glob("*.pdf"))
    reason = ""
    if not pdfs:
        reason = (
            "Nessun PDF trovato in data/raw/senate/. Senate eFD non consente scrape automatico: "
            "scarica i PTR a mano da https://efdsearch.senate.gov/ e copiali in quella cartella."
        )
    return {"dir": str(p), "exists": True, "pdfs": len(pdfs), "reason": reason}


def _summarize_oge_registry() -> dict[str, int]:
    """Quanti filing sono registrati in src/oge_source.py per dare feedback prima del download."""
    from ..oge_source import all_filings

    filings = all_filings()
    return {
        "registered": len(filings),
        "registered_278t": sum(1 for f in filings if f.is_periodic()),
        "registered_278e": sum(1 for f in filings if f.is_annual()),
    }


def run_ingest_all(
    state: JobState,
    cancel_event: threading.Event,
    *,
    force_reparse: bool = False,
    overwrite: bool = False,
    force_extract: bool = False,
    skip_senate: bool = False,
    skip_oge: bool = False,
) -> None:
    """Download House FD metadata, then run House + Senate + OGE ingest.

    force_reparse=True: set HOUSE_INGEST_FORCE_REPARSE_PDFS=1 for the ingest
    subprocess so every PDF is re-parsed even if its sha256 is already in
    ingested_files. OFF by default — a normal "Refresh data" only ingests
    PDFs that are new or whose sha256 changed (the dedup table already covers
    that). Enable it explicitly (CLI flag / explicit job option) when you
    want parser/ticker/date fixes to be re-applied to every PDF on disk
    without manually clearing the dedup table.
    overwrite=True: riscarica gli zip FD dal Clerk anche se gia presenti.
    force_extract=True: dopo l'estrazione, wipe + re-estrazione completa delle dir FD House
    (sicurezza contro metadata locali vecchi non rilevati dal check basato sulla dimensione).
    skip_senate=True: salta la fase Senate (utile per debug locale).
    skip_oge=True: salta la fase OGE (download + ingest Executive branch).
    """
    original_stdout = sys.stdout
    tee = _TeeStdout(original_stdout, state.log_lines)
    sys.stdout = tee
    try:
        from datetime import datetime

        from ..config import START_YEAR
        from ..download_house_fd import download_house_fd_bulk

        phase_total = len(_PIPELINE_PHASES)
        _begin_phase(
            state,
            phase="download-house-fd",
            phase_label="Downloading House FD",
            phase_index=0,
            phase_total=phase_total,
            progress_start=0,
        )
        _check_cancel(cancel_event)

        years = list(range(START_YEAR, datetime.now().year + 1))
        fd_hook = _make_progress_hook(
            state,
            phase="download-house-fd",
            phase_label="Downloading House FD",
            phase_index=0,
            phase_total=phase_total,
            progress_start=0,
            progress_span=15,
        )
        completed_years = download_house_fd_bulk(
            years,
            overwrite=overwrite,
            extract=True,
            force_extract=force_extract,
            cancel_event=cancel_event,
            progress_hook=fd_hook,
        )

        # Validazione post-estrazione: conferma quanti PTR sono effettivamente nei metadata.
        per_year: list[dict[str, int]] = []
        for y in years:
            per_year.append(_summarize_house_fd_extract(y))
        total_ptr = sum(x["rows_ptr"] for x in per_year)
        total_rows = sum(x["rows_total"] for x in per_year)
        for x in per_year:
            if x["txt_present"]:
                print(
                    f"House FD {x['year']}: TXT rows={x['rows_total']} PTR-rows={x['rows_ptr']}"
                )
        print(
            f"House FD bulk: {total_rows} righe metadata totali, di cui {total_ptr} PTR (FilingType=P) "
            f"negli anni {min(years)}-{max(years)}."
        )

        state.result = {
            "download_years": completed_years,
            "force_reparse": force_reparse,
            "overwrite": overwrite,
            "force_extract": force_extract,
            "skip_senate": skip_senate,
            "house_fd_rows_total": total_rows,
            "house_fd_rows_ptr": total_ptr,
            "house_fd_per_year": per_year,
        }

        state.progress = 15
        _begin_phase(
            state,
            phase="ingest-house",
            phase_label="Ingesting House PTRs",
            phase_index=1,
            phase_total=phase_total,
            progress_start=15,
        )
        _check_cancel(cancel_event)

        from ..ingest_house import ingest_house

        if force_reparse:
            # Opt-in only: re-parse every PDF on disk and update transactions
            # via ON CONFLICT upsert. The default Refresh flow relies on the
            # (path, sha256) dedup so it only touches new/changed PDFs and
            # therefore stays cheap when nothing changed since last run.
            os.environ["HOUSE_INGEST_FORCE_REPARSE_PDFS"] = "1"
            print("ingest-house: HOUSE_INGEST_FORCE_REPARSE_PDFS=1 — re-parsing every PDF on disk.")

        house_hook = _make_progress_hook(
            state,
            phase="ingest-house",
            phase_label="Ingesting House PTRs",
            phase_index=1,
            phase_total=phase_total,
            progress_start=15,
            progress_span=50,
        )
        ingest_house(cancel_event=cancel_event, progress_hook=house_hook)

        if skip_senate:
            state.progress = 100
            state.current_step = "done"
            state.result["scope"] = "ingest-house-only"
            return

        state.progress = 65
        _begin_phase(
            state,
            phase="ingest-senate",
            phase_label="Ingesting Senate PTRs",
            phase_index=2,
            phase_total=phase_total,
            progress_start=65,
        )
        _check_cancel(cancel_event)

        from ..ingest_senate import ingest_senate

        senate_summary = _summarize_senate_dir()
        if senate_summary["pdfs"] == 0:
            print(senate_summary["reason"])
        else:
            print(f"Senate: trovati {senate_summary['pdfs']} PDF in {senate_summary['dir']}.")

        senate_hook = _make_progress_hook(
            state,
            phase="ingest-senate",
            phase_label="Ingesting Senate PTRs",
            phase_index=2,
            phase_total=phase_total,
            progress_start=65,
            progress_span=15,
        )
        ingest_senate(cancel_event=cancel_event, progress_hook=senate_hook)
        state.result["senate"] = senate_summary

        if skip_oge:
            state.progress = 100
            state.current_step = "done"
            state.result["scope"] = "ingest-all-no-oge"
            state.result["oge_skipped"] = True
            return

        state.progress = 80
        _begin_phase(
            state,
            phase="download-oge",
            phase_label="Downloading OGE filings",
            phase_index=3,
            phase_total=phase_total,
            progress_start=80,
        )
        _check_cancel(cancel_event)

        from ..download_oge import download_oge_filings
        from ..ingest_oge import ingest_oge

        oge_registry = _summarize_oge_registry()
        print(
            f"OGE registry: {oge_registry['registered']} filing registrati "
            f"({oge_registry['registered_278t']} 278-T, {oge_registry['registered_278e']} 278e)."
        )
        # overwrite=False: scarica solo i PDF mancanti. Il registry è
        # hard-coded, quindi un refresh normale non dovrebbe ri-hammerare
        # extapps2.oge.gov per file già presenti.
        oge_download_error: str | None = None
        oge_download_hook = _make_progress_hook(
            state,
            phase="download-oge",
            phase_label="Downloading OGE filings",
            phase_index=3,
            phase_total=phase_total,
            progress_start=80,
            progress_span=10,
        )
        try:
            downloaded, already_present = download_oge_filings(
                overwrite=False,
                progress_hook=oge_download_hook,
            )
            print(
                f"OGE download: {downloaded} scaricati, {already_present} gia presenti su disco."
            )
        except CancelledError:
            raise
        except Exception as exc:
            # 404 dal registry: fail loud (politica del downloader), ma non
            # blocchiamo l'intero refresh — lasciamo che l'ingest tenti
            # comunque sui file gia presenti.
            print(f"OGE download error: {exc}")
            downloaded, already_present = 0, 0
            oge_download_error = str(exc)

        state.result["oge_download"] = {
            "registry": oge_registry,
            "downloaded": downloaded,
            "already_present": already_present,
            "error": oge_download_error,
        }

        state.progress = 90
        _begin_phase(
            state,
            phase="ingest-oge",
            phase_label="Ingesting OGE filings",
            phase_index=4,
            phase_total=phase_total,
            progress_start=90,
        )
        _check_cancel(cancel_event)

        oge_ingest_hook = _make_progress_hook(
            state,
            phase="ingest-oge",
            phase_label="Ingesting OGE filings",
            phase_index=4,
            phase_total=phase_total,
            progress_start=90,
            progress_span=10,
        )
        try:
            ingest_oge(cancel_event=cancel_event, progress_hook=oge_ingest_hook)
        except CancelledError:
            raise
        except Exception as exc:
            print(f"OGE ingest error: {exc}")
            state.result["oge_ingest_error"] = str(exc)

        state.progress = 100
        state.current_step = "done"
        state.phase_label = "Done"
        state.sub_progress = 100
        state.eta_seconds = None
        state.result["scope"] = "ingest-all"
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

    def start_or_restart(
        self,
        *,
        force_reparse: bool = False,
        overwrite: bool = False,
        force_extract: bool = False,
        skip_senate: bool = False,
        skip_oge: bool = False,
    ) -> dict[str, Any]:
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
                force_reparse,
                overwrite,
                force_extract,
                skip_senate,
                skip_oge,
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
            "phase_label": state.phase_label,
            "phase_index": state.phase_index,
            "phase_total": state.phase_total,
            "sub_progress": state.sub_progress,
            "sub_done": state.sub_done,
            "sub_total": state.sub_total,
            "sub_unit": state.sub_unit,
            "eta_seconds": state.eta_seconds,
            "step_started_at": state.step_started_at,
            "log_tail": list(state.log_lines)[-_LOG_TAIL_SIZE:],
            "log_lines": list(state.log_lines),
            "result": dict(state.result),
        }

    def _run_wrapper(
        self,
        run_id: int,
        state: JobState,
        cancel_event: threading.Event,
        force_reparse: bool = False,
        overwrite: bool = False,
        force_extract: bool = False,
        skip_senate: bool = False,
        skip_oge: bool = False,
    ) -> None:
        try:
            run_ingest_all(
                state,
                cancel_event,
                force_reparse=force_reparse,
                overwrite=overwrite,
                force_extract=force_extract,
                skip_senate=skip_senate,
                skip_oge=skip_oge,
            )
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
