from __future__ import annotations

from fastapi import APIRouter

from immich_doctor.api.models import BackupSnapshotsApiResponse
from immich_doctor.core.config import load_settings
from immich_doctor.services.backup_snapshot_service import BackupSnapshotVisibilityService

backup_router = APIRouter(prefix="/backup", tags=["backup"])


@backup_router.get("/snapshots", response_model=BackupSnapshotsApiResponse)
def list_backup_snapshots() -> BackupSnapshotsApiResponse:
    data = BackupSnapshotVisibilityService().list_snapshots(load_settings())
    return BackupSnapshotsApiResponse(data=data)
