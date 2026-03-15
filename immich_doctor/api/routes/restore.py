from __future__ import annotations

from fastapi import APIRouter, HTTPException

from immich_doctor.api.models import RestoreSimulationApiResponse
from immich_doctor.backup.restore import BackupRestoreSimulationService
from immich_doctor.core.config import load_settings

restore_router = APIRouter(prefix="/restore", tags=["restore"])


@restore_router.get("/simulate", response_model=RestoreSimulationApiResponse)
def simulate_full_restore(
    snapshot_id: str | None = None,
    repair_run_id: str | None = None,
) -> RestoreSimulationApiResponse:
    try:
        result = BackupRestoreSimulationService().simulate(
            load_settings(),
            snapshot_id=snapshot_id,
            repair_run_id=repair_run_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Selected snapshot or repair run was not found.",
        ) from exc
    payload = result.to_dict() if hasattr(result, "to_dict") else result
    return RestoreSimulationApiResponse(data=payload)
