from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import AliasChoices, BaseModel, Field

from immich_doctor.api.models import (
    MissingAssetApplyApiResponse,
    MissingAssetPreviewApiResponse,
    MissingAssetRestoreApiResponse,
    MissingAssetRestorePointDeleteApiResponse,
    MissingAssetRestorePointsApiResponse,
    MissingAssetScanApiResponse,
    MissingAssetScanStatusApiResponse,
)
from immich_doctor.consistency.missing_asset_scan_manager import MissingAssetScanManager
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


def _missing_asset_scan_manager(request: Request) -> MissingAssetScanManager:
    return request.app.state.missing_asset_scan_manager  # type: ignore[no-any-return]


@consistency_router.get(
    "/missing-asset-references/status",
    response_model=MissingAssetScanStatusApiResponse,
)
def get_missing_asset_reference_scan_status(
    request: Request,
) -> MissingAssetScanStatusApiResponse:
    data = _missing_asset_scan_manager(request).get_status(load_settings()).to_dict()
    return MissingAssetScanStatusApiResponse(data=data)


@consistency_router.post(
    "/missing-asset-references/scan",
    response_model=MissingAssetScanStatusApiResponse,
)
def trigger_missing_asset_reference_scan(
    request: Request,
) -> MissingAssetScanStatusApiResponse:
    data = _missing_asset_scan_manager(request).start_scan(load_settings()).to_dict()
    return MissingAssetScanStatusApiResponse(data=data)


@consistency_router.get(
    "/missing-asset-references/findings",
    response_model=MissingAssetScanApiResponse,
)
def scan_missing_asset_references(
    request: Request,
    limit: int | None = None,
    offset: int = 0,
) -> MissingAssetScanApiResponse:
    data = _missing_asset_scan_manager(request).get_latest_findings(
        load_settings(),
        limit=limit,
        offset=offset,
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
