from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from immich_doctor.api.models import BackupExecutionApiResponse, BackupSnapshotsApiResponse
from immich_doctor.backup.core.models import SnapshotKind
from immich_doctor.core.config import load_settings
from immich_doctor.services.backup_execution_service import BackupExecutionService
from immich_doctor.services.backup_snapshot_service import BackupSnapshotVisibilityService

backup_router = APIRouter(prefix="/backup", tags=["backup"])


class BackupExecutionRequest(BaseModel):
    kind: Literal["manual", "pre_repair"] = "manual"


@backup_router.get("/snapshots", response_model=BackupSnapshotsApiResponse)
def list_backup_snapshots() -> BackupSnapshotsApiResponse:
    data = BackupSnapshotVisibilityService().list_snapshots(load_settings())
    return BackupSnapshotsApiResponse(data=data)


@backup_router.post("/files", response_model=BackupExecutionApiResponse)
def run_backup_files(request: BackupExecutionRequest) -> BackupExecutionApiResponse:
    data = BackupExecutionService().run_files_backup(
        load_settings(),
        snapshot_kind=SnapshotKind(request.kind),
    )
    return BackupExecutionApiResponse(data=data)
