"""Admin endpoints (ingest refresh jobs)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..jobs import job_manager
from ..security import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


class RefreshDataRequest(BaseModel):
    restart: bool = True
    # Opt-in: re-parse every PDF already on disk, ignoring the (path, sha256)
    # dedup in ingested_files. OFF by default — a normal Refresh only touches
    # PDFs that are new or whose sha256 changed. Enable explicitly (e.g. via
    # the CLI flag) when you want parser/ticker/date fixes to be re-applied
    # to every PDF without manually clearing the dedup table.
    force_reparse: bool = False
    # Legacy knobs retained for backward compat with older frontends; the
    # current sidebar UI no longer surfaces them. Safe to drop from new clients.
    overwrite: bool = False
    force_extract: bool = False
    skip_senate: bool = False
    # Skip the OGE Executive branch (download + ingest). Defaults to False so
    # the dashboard "Refresh data" button also populates the Executive page.
    skip_oge: bool = False


@router.get("/refresh-data/status")
def refresh_data_status(_user: str = Depends(require_admin)) -> dict[str, object]:
    return job_manager.get_state()


@router.post("/refresh-data")
def refresh_data_start(
    payload: RefreshDataRequest,
    _user: str = Depends(require_admin),
) -> dict[str, object]:
    return job_manager.start_or_restart(
        force_reparse=payload.force_reparse,
        overwrite=payload.overwrite,
        force_extract=payload.force_extract,
        skip_senate=payload.skip_senate,
        skip_oge=payload.skip_oge,
    )


@router.post("/refresh-data/cancel")
def refresh_data_cancel(_user: str = Depends(require_admin)) -> dict[str, object]:
    return job_manager.cancel()
