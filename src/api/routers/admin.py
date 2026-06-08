"""Admin endpoints (ingest refresh jobs)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..jobs import job_manager
from ..security import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


class RefreshDataRequest(BaseModel):
    restart: bool = True


@router.get("/refresh-data/status")
def refresh_data_status(_user: str = Depends(require_admin)) -> dict[str, object]:
    return job_manager.get_state()


@router.post("/refresh-data")
def refresh_data_start(
    _payload: RefreshDataRequest,
    _user: str = Depends(require_admin),
) -> dict[str, object]:
    return job_manager.start_or_restart()


@router.post("/refresh-data/cancel")
def refresh_data_cancel(_user: str = Depends(require_admin)) -> dict[str, object]:
    return job_manager.cancel()
