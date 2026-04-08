from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from immich_doctor.api.models import (
    CatalogScanApiResponse,
    CatalogStatusApiResponse,
    CatalogZeroByteApiResponse,
)
from immich_doctor.catalog.service import (
    CatalogInventoryScanService,
    CatalogStatusService,
    CatalogZeroByteReportService,
)
from immich_doctor.core.config import load_settings

analyze_router = APIRouter(prefix="/analyze", tags=["analyze"])


class CatalogScanRequest(BaseModel):
    root: str | None = None
    resume_session_id: str | None = None
    max_files: int | None = Field(default=None, ge=1)


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
    data = CatalogZeroByteReportService().run(
        load_settings(),
        root_slug=root,
        limit=limit,
    ).to_dict()
    return CatalogZeroByteApiResponse(data=data)
