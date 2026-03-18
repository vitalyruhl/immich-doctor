from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from immich_doctor.api.models import (
    BackupExecutionApiResponse,
    BackupSizeEstimateApiResponse,
    BackupSnapshotsApiResponse,
)
from immich_doctor.backup.core.models import SnapshotKind
from immich_doctor.core.config import load_settings
from immich_doctor.services.backup_execution_service import BackupExecutionService
from immich_doctor.services.backup_job_service import BackgroundJobRuntime
from immich_doctor.services.backup_size_service import BackupSizeEstimationService
from immich_doctor.services.backup_snapshot_service import BackupSnapshotVisibilityService

backup_router = APIRouter(prefix="/backup", tags=["backup"])


class BackupExecutionRequest(BaseModel):
    kind: Literal["manual", "pre_repair"] = "manual"


class BackupSizeCollectionRequest(BaseModel):
    force: bool = False


def _job_runtime(request: Request) -> BackgroundJobRuntime:
    return request.app.state.backup_job_runtime  # type: ignore[no-any-return]


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


@backup_router.get("/size-estimate", response_model=BackupSizeEstimateApiResponse)
def get_backup_size_estimate(request: Request) -> BackupSizeEstimateApiResponse:
    data = BackupSizeEstimationService(runtime=_job_runtime(request)).get_snapshot(load_settings())
    return BackupSizeEstimateApiResponse(data=data.model_dump(by_alias=True, mode="json"))


@backup_router.post("/size-estimate/collect", response_model=BackupSizeEstimateApiResponse)
def collect_backup_size_estimate(
    request: Request,
    payload: BackupSizeCollectionRequest,
) -> BackupSizeEstimateApiResponse:
    data = BackupSizeEstimationService(runtime=_job_runtime(request)).collect(
        load_settings(),
        force=payload.force,
    )
    return BackupSizeEstimateApiResponse(data=data.model_dump(by_alias=True, mode="json"))


@backup_router.post("/size-estimate/cancel", response_model=BackupSizeEstimateApiResponse)
def cancel_backup_size_estimate(request: Request) -> BackupSizeEstimateApiResponse:
    canceled = BackupSizeEstimationService(runtime=_job_runtime(request)).request_cancel()
    data = canceled or BackupSizeEstimationService(runtime=_job_runtime(request)).get_snapshot(
        load_settings()
    )
    return BackupSizeEstimateApiResponse(data=data.model_dump(by_alias=True, mode="json"))
