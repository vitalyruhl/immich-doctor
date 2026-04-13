from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from immich_doctor.api.models import (
    CatalogScanApiResponse,
    CatalogScanJobApiResponse,
    CatalogStatusApiResponse,
    CatalogZeroByteApiResponse,
    DbCorruptionApiResponse,
    EmptyFolderActionApiResponse,
    EmptyFolderScanApiResponse,
)
from immich_doctor.catalog.service import (
    CatalogInventoryScanService,
    CatalogStatusService,
    CatalogZeroByteReportService,
)
from immich_doctor.catalog.workflow_service import CatalogWorkflowService
from immich_doctor.core.config import load_settings
from immich_doctor.db.corruption import DbCorruptionScanService
from immich_doctor.storage.empty_folders import (
    EmptyDirQuarantineManager,
    EmptyFolderScanStatusTracker,
    EmptyFolderScanner,
)

analyze_router = APIRouter(prefix="/analyze", tags=["analyze"])
empty_folder_scan_status = EmptyFolderScanStatusTracker()


class CatalogScanRequest(BaseModel):
    root: str | None = None
    resume_session_id: str | None = None
    max_files: int | None = Field(default=None, ge=1)


class CatalogScanJobRequest(BaseModel):
    force: bool = False


class CatalogScanJobWorkersRequest(BaseModel):
    workers: int = Field(ge=1)


class EmptyFolderScanRequest(BaseModel):
    root: str | None = None


class EmptyFolderQuarantineRequest(BaseModel):
    root_slugs: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)
    quarantine_all: bool = False
    dry_run: bool = False


class EmptyFolderRestoreRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)
    restore_all: bool = False
    dry_run: bool = False


class EmptyFolderDeleteRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)
    delete_all: bool = False
    dry_run: bool = False


@analyze_router.post("/catalog/scan", response_model=CatalogScanApiResponse)
def start_catalog_scan(payload: CatalogScanRequest) -> CatalogScanApiResponse:
    data = (
        CatalogInventoryScanService()
        .run(
            load_settings(),
            root_slug=payload.root,
            resume_session_id=payload.resume_session_id,
            max_files=payload.max_files,
        )
        .to_dict()
    )
    return CatalogScanApiResponse(data=data)


@analyze_router.get("/catalog/status", response_model=CatalogStatusApiResponse)
def catalog_status(root: str | None = None) -> CatalogStatusApiResponse:
    data = CatalogStatusService().run(load_settings(), root_slug=root).to_dict()
    return CatalogStatusApiResponse(data=data)


@analyze_router.get("/catalog/zero-byte", response_model=CatalogZeroByteApiResponse)
def catalog_zero_byte(
    root: str | None = None,
    limit: int = Query(default=100, ge=1),
) -> CatalogZeroByteApiResponse:
    data = (
        CatalogZeroByteReportService()
        .run(
            load_settings(),
            root_slug=root,
            limit=limit,
        )
        .to_dict()
    )
    return CatalogZeroByteApiResponse(data=data)


@analyze_router.get("/catalog/scan-job", response_model=CatalogScanJobApiResponse)
def catalog_scan_job(request: Request) -> CatalogScanJobApiResponse:
    data = CatalogWorkflowService(runtime=request.app.state.backup_job_runtime).get_scan_job(
        load_settings()
    )
    return CatalogScanJobApiResponse(data=data)


@analyze_router.post("/catalog/scan-job/start", response_model=CatalogScanJobApiResponse)
def start_catalog_scan_job(
    request: Request,
    payload: CatalogScanJobRequest,
) -> CatalogScanJobApiResponse:
    data = CatalogWorkflowService(runtime=request.app.state.backup_job_runtime).start_scan(
        load_settings(),
        force=payload.force,
    )
    return CatalogScanJobApiResponse(data=data)


@analyze_router.post("/catalog/scan-job/pause", response_model=CatalogScanJobApiResponse)
def pause_catalog_scan_job(request: Request) -> CatalogScanJobApiResponse:
    data = CatalogWorkflowService(runtime=request.app.state.backup_job_runtime).pause_scan(
        load_settings()
    )
    return CatalogScanJobApiResponse(data=data)


@analyze_router.post("/catalog/scan-job/resume", response_model=CatalogScanJobApiResponse)
def resume_catalog_scan_job(request: Request) -> CatalogScanJobApiResponse:
    data = CatalogWorkflowService(runtime=request.app.state.backup_job_runtime).resume_scan(
        load_settings()
    )
    return CatalogScanJobApiResponse(data=data)


@analyze_router.post("/catalog/scan-job/stop", response_model=CatalogScanJobApiResponse)
def stop_catalog_scan_job(request: Request) -> CatalogScanJobApiResponse:
    data = CatalogWorkflowService(runtime=request.app.state.backup_job_runtime).stop_scan(
        load_settings()
    )
    return CatalogScanJobApiResponse(data=data)


@analyze_router.post(
    "/catalog/scan-job/actors/{actor_id}/pause",
    response_model=CatalogScanJobApiResponse,
)
def pause_catalog_scan_actor(request: Request, actor_id: str) -> CatalogScanJobApiResponse:
    data = CatalogWorkflowService(runtime=request.app.state.backup_job_runtime).pause_scan_actor(
        load_settings(),
        actor_id=actor_id,
    )
    return CatalogScanJobApiResponse(data=data)


@analyze_router.post(
    "/catalog/scan-job/actors/{actor_id}/resume",
    response_model=CatalogScanJobApiResponse,
)
def resume_catalog_scan_actor(request: Request, actor_id: str) -> CatalogScanJobApiResponse:
    data = CatalogWorkflowService(runtime=request.app.state.backup_job_runtime).resume_scan_actor(
        load_settings(),
        actor_id=actor_id,
    )
    return CatalogScanJobApiResponse(data=data)


@analyze_router.post(
    "/catalog/scan-job/actors/{actor_id}/stop",
    response_model=CatalogScanJobApiResponse,
)
def stop_catalog_scan_actor(request: Request, actor_id: str) -> CatalogScanJobApiResponse:
    data = CatalogWorkflowService(runtime=request.app.state.backup_job_runtime).stop_scan_actor(
        load_settings(),
        actor_id=actor_id,
    )
    return CatalogScanJobApiResponse(data=data)


@analyze_router.post("/catalog/scan-job/workers", response_model=CatalogScanJobApiResponse)
def request_catalog_scan_workers(
    request: Request,
    payload: CatalogScanJobWorkersRequest,
) -> CatalogScanJobApiResponse:
    data = CatalogWorkflowService(
        runtime=request.app.state.backup_job_runtime
    ).request_scan_worker_resize(load_settings(), workers=payload.workers)
    return CatalogScanJobApiResponse(data=data)


@analyze_router.post("/storage/empty-folders/scan", response_model=EmptyFolderScanApiResponse)
def scan_empty_folders(payload: EmptyFolderScanRequest) -> EmptyFolderScanApiResponse:
    empty_folder_scan_status.start()
    try:
        report = EmptyFolderScanner().scan(
            load_settings(),
            root_slug=payload.root,
            progress_callback=empty_folder_scan_status.update,
        )
    except Exception as exc:
        empty_folder_scan_status.fail(str(exc))
        raise
    empty_folder_scan_status.finish()
    return EmptyFolderScanApiResponse(data=report.to_dict())


@analyze_router.get(
    "/storage/empty-folders/scan-status",
    response_model=EmptyFolderActionApiResponse,
)
def empty_folder_scan_status_route() -> EmptyFolderActionApiResponse:
    return EmptyFolderActionApiResponse(data=empty_folder_scan_status.snapshot())


@analyze_router.post(
    "/storage/empty-folders/quarantine",
    response_model=EmptyFolderActionApiResponse,
)
def quarantine_empty_folders(
    payload: EmptyFolderQuarantineRequest,
) -> EmptyFolderActionApiResponse:
    result = EmptyDirQuarantineManager().quarantine(
        load_settings(),
        root_slugs=tuple(payload.root_slugs),
        paths=tuple(payload.paths),
        quarantine_all=payload.quarantine_all,
        dry_run=payload.dry_run,
    )
    return EmptyFolderActionApiResponse(data=result.to_dict())


@analyze_router.get(
    "/storage/empty-folders/quarantine-list",
    response_model=EmptyFolderActionApiResponse,
)
def list_quarantined_empty_folders(
    session_id: str | None = None,
) -> EmptyFolderActionApiResponse:
    items = EmptyDirQuarantineManager().list_quarantined(
        load_settings(),
        session_id=session_id,
    )
    return EmptyFolderActionApiResponse(
        data={
            "session_id": session_id,
            "items": [item.to_dict() for item in items],
            "count": len(items),
        }
    )


@analyze_router.post(
    "/storage/empty-folders/quarantine/{session_id}/restore",
    response_model=EmptyFolderActionApiResponse,
)
def restore_empty_folders(
    session_id: str,
    payload: EmptyFolderRestoreRequest,
) -> EmptyFolderActionApiResponse:
    result = EmptyDirQuarantineManager().restore(
        load_settings(),
        session_id=session_id,
        paths=tuple(payload.paths),
        restore_all=payload.restore_all,
        dry_run=payload.dry_run,
    )
    return EmptyFolderActionApiResponse(data=result.to_dict())


@analyze_router.delete(
    "/storage/empty-folders/quarantine/{session_id}",
    response_model=EmptyFolderActionApiResponse,
)
def delete_empty_folders_from_quarantine(
    session_id: str,
    payload: EmptyFolderDeleteRequest,
) -> EmptyFolderActionApiResponse:
    result = EmptyDirQuarantineManager().finalize_delete(
        load_settings(),
        session_id=session_id,
        paths=tuple(payload.paths),
        delete_all=payload.delete_all,
        dry_run=payload.dry_run,
    )
    return EmptyFolderActionApiResponse(data=result.to_dict())


@analyze_router.post("/db/corruption/scan", response_model=DbCorruptionApiResponse)
def scan_db_corruption() -> DbCorruptionApiResponse:
    report = DbCorruptionScanService().run(load_settings())
    return DbCorruptionApiResponse(data=report.to_dict())
