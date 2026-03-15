from __future__ import annotations

from fastapi import APIRouter, HTTPException

from immich_doctor.api.models import (
    QuarantineSummaryApiResponse,
    RepairRunDetailApiResponse,
    RepairRunsApiResponse,
)
from immich_doctor.core.config import load_settings
from immich_doctor.services.repair_visibility_service import RepairVisibilityService

repair_router = APIRouter(prefix="/repair", tags=["repair"])


@repair_router.get("/runs", response_model=RepairRunsApiResponse)
def list_repair_runs() -> RepairRunsApiResponse:
    data = RepairVisibilityService().list_runs(load_settings())
    return RepairRunsApiResponse(data=data)


@repair_router.get("/runs/{repair_run_id}", response_model=RepairRunDetailApiResponse)
def get_repair_run_detail(repair_run_id: str) -> RepairRunDetailApiResponse:
    try:
        data = RepairVisibilityService().get_run_detail(load_settings(), repair_run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Repair run not found.") from exc
    return RepairRunDetailApiResponse(data=data)


@repair_router.get("/quarantine/summary", response_model=QuarantineSummaryApiResponse)
def get_quarantine_summary() -> QuarantineSummaryApiResponse:
    data = RepairVisibilityService().quarantine_summary(load_settings())
    return QuarantineSummaryApiResponse(data=data)
