from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import AliasChoices, BaseModel, Field

from immich_doctor.api.models import (
    CatalogConsistencyJobApiResponse,
    CatalogRemediationApplyApiResponse,
    CatalogRemediationPreviewApiResponse,
    CatalogRemediationScanApiResponse,
    MissingAssetApplyApiResponse,
    MissingAssetPreviewApiResponse,
    MissingAssetRestoreApiResponse,
    MissingAssetRestorePointDeleteApiResponse,
    MissingAssetRestorePointsApiResponse,
    MissingAssetScanApiResponse,
)
from immich_doctor.catalog.remediation_service import CatalogRemediationService
from immich_doctor.catalog.workflow_service import CatalogWorkflowService
from immich_doctor.consistency.missing_asset_service import MissingAssetReferenceService
from immich_doctor.core.config import load_settings

consistency_router = APIRouter(prefix="/consistency", tags=["consistency"])


class MissingAssetPreviewRequest(BaseModel):
    asset_ids: list[str] = Field(default_factory=list)
    select_all: bool = False
    limit: int | None = Field(default=100, ge=1)
    offset: int = Field(default=0, ge=0)


class MissingAssetApplyRequest(BaseModel):
    repair_run_id: str


class MissingAssetRestoreRequest(BaseModel):
    restore_point_ids: list[str] = Field(default_factory=list)
    select_all: bool = Field(
        default=False,
        validation_alias=AliasChoices("select_all", "restore_all"),
    )


class MissingAssetDeleteRestorePointsRequest(BaseModel):
    restore_point_ids: list[str] = Field(default_factory=list)
    select_all: bool = Field(
        default=False,
        validation_alias=AliasChoices("select_all", "delete_all"),
    )


class CatalogConsistencyJobRequest(BaseModel):
    force: bool = False


class CatalogRemediationBrokenPreviewRequest(BaseModel):
    asset_ids: list[str] = Field(default_factory=list)
    select_all: bool = False


class CatalogRemediationFusePreviewRequest(BaseModel):
    finding_ids: list[str] = Field(default_factory=list)
    select_all: bool = False


class CatalogRemediationApplyRequest(BaseModel):
    repair_run_id: str


@consistency_router.get(
    "/missing-asset-references/findings",
    response_model=MissingAssetScanApiResponse,
)
def scan_missing_asset_references(
    limit: int = 100,
    offset: int = 0,
) -> MissingAssetScanApiResponse:
    data = (
        MissingAssetReferenceService()
        .scan(
            load_settings(),
            limit=limit,
            offset=offset,
        )
        .to_dict()
    )
    return MissingAssetScanApiResponse(data=data)


@consistency_router.post(
    "/missing-asset-references/preview",
    response_model=MissingAssetPreviewApiResponse,
)
def preview_missing_asset_references(
    payload: MissingAssetPreviewRequest,
) -> MissingAssetPreviewApiResponse:
    data = (
        MissingAssetReferenceService()
        .preview(
            load_settings(),
            asset_ids=tuple(payload.asset_ids),
            select_all=payload.select_all,
            limit=payload.limit,
            offset=payload.offset,
        )
        .to_dict()
    )
    return MissingAssetPreviewApiResponse(data=data)


@consistency_router.post(
    "/missing-asset-references/apply",
    response_model=MissingAssetApplyApiResponse,
)
def apply_missing_asset_reference_removal(
    payload: MissingAssetApplyRequest,
) -> MissingAssetApplyApiResponse:
    data = (
        MissingAssetReferenceService()
        .apply(
            load_settings(),
            repair_run_id=payload.repair_run_id,
        )
        .to_dict()
    )
    return MissingAssetApplyApiResponse(data=data)


@consistency_router.get(
    "/missing-asset-references/restore-points",
    response_model=MissingAssetRestorePointsApiResponse,
)
def list_missing_asset_restore_points() -> MissingAssetRestorePointsApiResponse:
    data = MissingAssetReferenceService().list_restore_points(load_settings()).to_dict()
    return MissingAssetRestorePointsApiResponse(data=data)


@consistency_router.post(
    "/missing-asset-references/restore-points/restore",
    response_model=MissingAssetRestoreApiResponse,
)
def restore_missing_asset_restore_points(
    payload: MissingAssetRestoreRequest,
) -> MissingAssetRestoreApiResponse:
    data = (
        MissingAssetReferenceService()
        .restore(
            load_settings(),
            restore_point_ids=tuple(payload.restore_point_ids),
            restore_all=payload.select_all,
        )
        .to_dict()
    )
    return MissingAssetRestoreApiResponse(data=data)


@consistency_router.post(
    "/missing-asset-references/restore-points/delete",
    response_model=MissingAssetRestorePointDeleteApiResponse,
)
def delete_missing_asset_restore_points(
    payload: MissingAssetDeleteRestorePointsRequest,
) -> MissingAssetRestorePointDeleteApiResponse:
    data = (
        MissingAssetReferenceService()
        .delete_restore_points(
            load_settings(),
            restore_point_ids=tuple(payload.restore_point_ids),
            delete_all=payload.select_all,
        )
        .to_dict()
    )
    return MissingAssetRestorePointDeleteApiResponse(data=data)


@consistency_router.get(
    "/catalog-remediation/findings",
    response_model=CatalogRemediationScanApiResponse,
)
def scan_catalog_remediation_findings() -> CatalogRemediationScanApiResponse:
    data = CatalogRemediationService().scan(load_settings()).to_dict()
    return CatalogRemediationScanApiResponse(data=data)


@consistency_router.post(
    "/catalog-remediation/broken-db-originals/preview",
    response_model=CatalogRemediationPreviewApiResponse,
)
def preview_broken_db_original_remediation(
    payload: CatalogRemediationBrokenPreviewRequest,
) -> CatalogRemediationPreviewApiResponse:
    data = (
        CatalogRemediationService()
        .preview_broken_db_originals(
            load_settings(),
            asset_ids=tuple(payload.asset_ids),
            select_all=payload.select_all,
        )
        .to_dict()
    )
    return CatalogRemediationPreviewApiResponse(data=data)


@consistency_router.post(
    "/catalog-remediation/fuse-hidden-orphans/preview",
    response_model=CatalogRemediationPreviewApiResponse,
)
def preview_fuse_hidden_remediation(
    payload: CatalogRemediationFusePreviewRequest,
) -> CatalogRemediationPreviewApiResponse:
    data = (
        CatalogRemediationService()
        .preview_fuse_hidden_orphans(
            load_settings(),
            finding_ids=tuple(payload.finding_ids),
            select_all=payload.select_all,
        )
        .to_dict()
    )
    return CatalogRemediationPreviewApiResponse(data=data)


@consistency_router.post(
    "/catalog-remediation/apply",
    response_model=CatalogRemediationApplyApiResponse,
)
def apply_catalog_remediation(
    payload: CatalogRemediationApplyRequest,
) -> CatalogRemediationApplyApiResponse:
    data = (
        CatalogRemediationService()
        .apply(
            load_settings(),
            repair_run_id=payload.repair_run_id,
        )
        .to_dict()
    )
    return CatalogRemediationApplyApiResponse(data=data)


@consistency_router.get("/catalog", response_model=CatalogConsistencyJobApiResponse)
def get_catalog_consistency_job(request: Request) -> CatalogConsistencyJobApiResponse:
    data = CatalogWorkflowService(runtime=request.app.state.backup_job_runtime).get_consistency_job(
        load_settings()
    )
    return CatalogConsistencyJobApiResponse(data=data)


@consistency_router.post("/catalog/start", response_model=CatalogConsistencyJobApiResponse)
def start_catalog_consistency_job(
    request: Request,
    payload: CatalogConsistencyJobRequest,
) -> CatalogConsistencyJobApiResponse:
    data = CatalogWorkflowService(runtime=request.app.state.backup_job_runtime).start_consistency(
        load_settings(),
        force=payload.force,
    )
    return CatalogConsistencyJobApiResponse(data=data)
