from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from immich_doctor.api.models import (
    CatalogScanApiResponse,
    CatalogScanJobApiResponse,
    CatalogStatusApiResponse,
    CatalogZeroByteApiResponse,
)
from immich_doctor.catalog.service import (
    CatalogInventoryScanService,
    CatalogStatusService,
    CatalogZeroByteReportService,
)
from immich_doctor.catalog.workflow_service import CatalogWorkflowService
from immich_doctor.core.config import load_settings

analyze_router = APIRouter(prefix="/analyze", tags=["analyze"])


class CatalogScanRequest(BaseModel):
    root: str | None = None
    resume_session_id: str | None = None
    max_files: int | None = Field(default=None, ge=1)


class CatalogScanJobRequest(BaseModel):
    force: bool = False


class CatalogScanJobWorkersRequest(BaseModel):
    workers: int = Field(ge=1)


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


@analyze_router.post("/catalog/scan-job/actors/{actor_id}/pause", response_model=CatalogScanJobApiResponse)
def pause_catalog_scan_actor(request: Request, actor_id: str) -> CatalogScanJobApiResponse:
    data = CatalogWorkflowService(runtime=request.app.state.backup_job_runtime).pause_scan_actor(
        load_settings(),
        actor_id=actor_id,
    )
    return CatalogScanJobApiResponse(data=data)


@analyze_router.post("/catalog/scan-job/actors/{actor_id}/resume", response_model=CatalogScanJobApiResponse)
def resume_catalog_scan_actor(request: Request, actor_id: str) -> CatalogScanJobApiResponse:
    data = CatalogWorkflowService(runtime=request.app.state.backup_job_runtime).resume_scan_actor(
        load_settings(),
        actor_id=actor_id,
    )
    return CatalogScanJobApiResponse(data=data)


@analyze_router.post("/catalog/scan-job/actors/{actor_id}/stop", response_model=CatalogScanJobApiResponse)
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
