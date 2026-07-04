"""In-process background job runner for admin ingest tasks."""
from __future__ import annotations

import os
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
    force_reparse: bool = True,
    overwrite: bool = False,
    force_extract: bool = False,
    skip_senate: bool = False,
    skip_oge: bool = False,
) -> None:
    """Download House FD metadata, then run House + Senate + OGE ingest.

    force_reparse=True: set HOUSE_INGEST_FORCE_REPARSE_PDFS=1 for the ingest
    subprocess so every PDF is re-parsed even if its sha256 is already in
    ingested_files. Required to surface parser/ticker/date fixes across
    refreshes (otherwise the dedup table masks every previously-ingested PDF).
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

        state.current_step = "download-house-fd"
        state.progress = 5
        _check_cancel(cancel_event)

        years = list(range(START_YEAR, datetime.now().year + 1))
        completed_years = download_house_fd_bulk(
            years,
            overwrite=overwrite,
            extract=True,
            force_extract=force_extract,
            cancel_event=cancel_event,
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
        state.current_step = "ingest-house"
        _check_cancel(cancel_event)

        from ..ingest_house import ingest_house

        if force_reparse:
            # Bypass the (path, sha256) dedup so parser/ticker/date improvements
            # are applied on every refresh; the user clicked "Refresh data"
            # expecting new ingestion work, not a no-op.
            os.environ["HOUSE_INGEST_FORCE_REPARSE_PDFS"] = "1"
            print("ingest-house: HOUSE_INGEST_FORCE_REPARSE_PDFS=1 — re-parsing every PDF on disk.")

        ingest_house(cancel_event=cancel_event)

        if skip_senate:
            state.progress = 100
            state.current_step = "done"
            state.result["scope"] = "ingest-house-only"
            return

        state.progress = 65
        state.current_step = "ingest-senate"
        _check_cancel(cancel_event)

        from ..ingest_senate import ingest_senate

        senate_summary = _summarize_senate_dir()
        if senate_summary["pdfs"] == 0:
            print(senate_summary["reason"])
        else:
            print(f"Senate: trovati {senate_summary['pdfs']} PDF in {senate_summary['dir']}.")

        ingest_senate(cancel_event=cancel_event)
        state.result["senate"] = senate_summary

        if skip_oge:
            state.progress = 100
            state.current_step = "done"
            state.result["scope"] = "ingest-all-no-oge"
            state.result["oge_skipped"] = True
            return

        state.progress = 80
        state.current_step = "download-oge"
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
        try:
            downloaded, already_present = download_oge_filings(overwrite=False)
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
        state.current_step = "ingest-oge"
        _check_cancel(cancel_event)

        try:
            ingest_oge(cancel_event=cancel_event)
        except CancelledError:
            raise
        except Exception as exc:
            print(f"OGE ingest error: {exc}")
            state.result["oge_ingest_error"] = str(exc)

        state.progress = 100
        state.current_step = "done"
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
        force_reparse: bool = True,
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
            "log_tail": list(state.log_lines)[-_LOG_TAIL_SIZE:],
            "log_lines": list(state.log_lines),
            "result": dict(state.result),
        }

    def _run_wrapper(
        self,
        run_id: int,
        state: JobState,
        cancel_event: threading.Event,
        force_reparse: bool = True,
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
