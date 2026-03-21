from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from immich_doctor.api.models import (
    BackupAssetWorkflowApiResponse,
    BackupExecutionApiResponse,
    BackupExecutionStatusApiResponse,
    BackupRestoreActionApiResponse,
    BackupSizeEstimateApiResponse,
    BackupSnapshotsApiResponse,
    BackupTargetsApiResponse,
    BackupTargetValidationApiResponse,
    BackupTestCopyApiResponse,
)
from immich_doctor.backup.core.models import SnapshotKind
from immich_doctor.backup.targets.models import BackupTargetUpsertPayload
from immich_doctor.core.config import load_settings
from immich_doctor.services.backup_asset_workflow_service import BackupAssetWorkflowService
from immich_doctor.services.backup_execution_service import BackupExecutionService
from immich_doctor.services.backup_job_service import BackgroundJobRuntime
from immich_doctor.services.backup_runtime_capability_service import (
    BackupRuntimeCapabilityService,
)
from immich_doctor.services.backup_size_service import BackupSizeEstimationService
from immich_doctor.services.backup_snapshot_service import BackupSnapshotVisibilityService
from immich_doctor.services.backup_target_settings_service import BackupTargetSettingsService
from immich_doctor.services.backup_target_validation_service import BackupTargetValidationService
from immich_doctor.services.manual_backup_execution_service import ManualBackupExecutionService

backup_router = APIRouter(prefix="/backup", tags=["backup"])


class BackupExecutionRequest(BaseModel):
    kind: Literal["manual", "pre_repair"] = "manual"


class BackupSizeCollectionRequest(BaseModel):
    force: bool = False


class ManualBackupExecutionRequest(BaseModel):
    target_id: str
    kind: Literal["manual", "pre_repair"] = "manual"


class BackupRestoreRequest(BaseModel):
    asset_ids: list[str]
    apply: bool = False


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


@backup_router.get("/targets", response_model=BackupTargetsApiResponse)
def list_backup_targets(request: Request) -> BackupTargetsApiResponse:
    data = BackupTargetSettingsService().list_targets(load_settings())
    runtime_capabilities = BackupRuntimeCapabilityService(runtime=_job_runtime(request))
    data["runtimeCapabilities"] = {
        "rsync": runtime_capabilities.probe_rsync(),
        "sshAgent": runtime_capabilities.probe_ssh_agent(),
    }
    return BackupTargetsApiResponse(data=data)


@backup_router.post("/targets", response_model=BackupTargetsApiResponse)
def create_backup_target(payload: BackupTargetUpsertPayload) -> BackupTargetsApiResponse:
    data = BackupTargetSettingsService().create_target(load_settings(), payload)
    return BackupTargetsApiResponse(data=data)


@backup_router.put("/targets/{target_id}", response_model=BackupTargetsApiResponse)
def update_backup_target(
    target_id: str,
    payload: BackupTargetUpsertPayload,
) -> BackupTargetsApiResponse:
    data = BackupTargetSettingsService().update_target(
        load_settings(),
        target_id=target_id,
        payload=payload,
    )
    return BackupTargetsApiResponse(data=data)


@backup_router.delete("/targets/{target_id}", response_model=BackupTargetsApiResponse)
def delete_backup_target(target_id: str) -> BackupTargetsApiResponse:
    data = BackupTargetSettingsService().delete_target(load_settings(), target_id=target_id)
    return BackupTargetsApiResponse(data=data)


@backup_router.get(
    "/targets/{target_id}/validation",
    response_model=BackupTargetValidationApiResponse,
)
def get_backup_target_validation(
    request: Request,
    target_id: str,
) -> BackupTargetValidationApiResponse:
    data = BackupTargetValidationService(runtime=_job_runtime(request)).get_validation(
        load_settings(),
        target_id=target_id,
    )
    return BackupTargetValidationApiResponse(data=data)


@backup_router.post(
    "/targets/{target_id}/validate",
    response_model=BackupTargetValidationApiResponse,
)
def start_backup_target_validation(
    request: Request,
    target_id: str,
) -> BackupTargetValidationApiResponse:
    data = BackupTargetValidationService(runtime=_job_runtime(request)).start_validation(
        load_settings(),
        target_id=target_id,
    )
    return BackupTargetValidationApiResponse(data=data)


@backup_router.get("/executions/current", response_model=BackupExecutionStatusApiResponse)
def get_current_backup_execution(request: Request) -> BackupExecutionStatusApiResponse:
    data = ManualBackupExecutionService(runtime=_job_runtime(request)).get_current(load_settings())
    return BackupExecutionStatusApiResponse(data=data)


@backup_router.post("/executions", response_model=BackupExecutionStatusApiResponse)
def start_manual_backup_execution(
    request: Request,
    payload: ManualBackupExecutionRequest,
) -> BackupExecutionStatusApiResponse:
    data = ManualBackupExecutionService(runtime=_job_runtime(request)).start_execution(
        load_settings(),
        target_id=payload.target_id,
        snapshot_kind=SnapshotKind(payload.kind),
    )
    return BackupExecutionStatusApiResponse(data=data)


@backup_router.post("/executions/cancel", response_model=BackupExecutionStatusApiResponse)
def cancel_manual_backup_execution(request: Request) -> BackupExecutionStatusApiResponse:
    service = ManualBackupExecutionService(runtime=_job_runtime(request))
    data = service.request_cancel() or service.get_current(load_settings())
    return BackupExecutionStatusApiResponse(data=data)


@backup_router.get(
    "/targets/{target_id}/assets/overview",
    response_model=BackupAssetWorkflowApiResponse,
)
def get_backup_asset_workflow_overview(target_id: str) -> BackupAssetWorkflowApiResponse:
    data = BackupAssetWorkflowService().get_overview(load_settings(), target_id=target_id)
    return BackupAssetWorkflowApiResponse(data=data)


@backup_router.post(
    "/targets/{target_id}/assets/test-copy",
    response_model=BackupTestCopyApiResponse,
)
def run_backup_test_copy(target_id: str) -> BackupTestCopyApiResponse:
    data = BackupAssetWorkflowService().run_test_copy(load_settings(), target_id=target_id)
    return BackupTestCopyApiResponse(data=data)


@backup_router.post(
    "/targets/{target_id}/assets/restore",
    response_model=BackupRestoreActionApiResponse,
)
def run_backup_restore_action(
    target_id: str,
    payload: BackupRestoreRequest,
) -> BackupRestoreActionApiResponse:
    data = BackupAssetWorkflowService().restore_items(
        load_settings(),
        target_id=target_id,
        asset_ids=payload.asset_ids,
        apply=payload.apply,
    )
    return BackupRestoreActionApiResponse(data=data)


@backup_router.get("/targets/{target_id}/assets/preview/content", response_model=None)
def get_backup_asset_preview_content(
    target_id: str,
    side: Literal["source", "backup"],
    asset_id: str,
) -> FileResponse:
    try:
        path, media_type = BackupAssetWorkflowService().resolve_preview_file(
            load_settings(),
            target_id=target_id,
            side=side,
            asset_id=asset_id,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type=media_type)
