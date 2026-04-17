from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from immich_doctor.api.models import (
    DbCorruptionApiResponse,
    QuarantineSummaryApiResponse,
    RepairRunDetailApiResponse,
    RepairRunsApiResponse,
    UndoExecutionApiResponse,
    UndoPlanApiResponse,
)
from immich_doctor.core.config import load_settings
from immich_doctor.db.corruption import DbCorruptionRepairService
from immich_doctor.repair import RepairUndoService
from immich_doctor.services.repair_visibility_service import RepairVisibilityService

repair_router = APIRouter(prefix="/repair", tags=["repair"])


class UndoExecutionRequest(BaseModel):
    apply: bool = False
    entry_ids: list[str] = Field(default_factory=list)


class DbCorruptionPreviewRequest(BaseModel):
    selected_delete_ids: list[str] = Field(default_factory=list)
    backup_confirmed: bool = False
    override_backup_requirement: bool = False
    maintenance_mode_confirmed: bool = False
    system_index_duplicate_error_text: str | None = None
    high_risk_clear_pg_statistic_approval: bool = False
    force_reindex_database: bool = False


class DbCorruptionApplyRequest(BaseModel):
    repair_run_id: str


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


@repair_router.get("/runs/{repair_run_id}/undo-plan", response_model=UndoPlanApiResponse)
def get_undo_plan(
    repair_run_id: str,
    entry_id: list[str] | None = None,
) -> UndoPlanApiResponse:
    try:
        result = RepairUndoService().plan(
            load_settings(),
            repair_run_id=repair_run_id,
            entry_ids=tuple(entry_id or ()),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Repair run not found.") from exc
    payload = result.to_dict() if hasattr(result, "to_dict") else result
    return UndoPlanApiResponse(data=payload)


@repair_router.post("/runs/{repair_run_id}/undo", response_model=UndoExecutionApiResponse)
def execute_undo(
    repair_run_id: str,
    payload: UndoExecutionRequest,
) -> UndoExecutionApiResponse:
    try:
        result = RepairUndoService().execute(
            load_settings(),
            repair_run_id=repair_run_id,
            entry_ids=tuple(payload.entry_ids),
            apply=payload.apply,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Repair run not found.") from exc
    payload = result.to_dict() if hasattr(result, "to_dict") else result
    return UndoExecutionApiResponse(data=payload)


@repair_router.post("/db/corruption/preview", response_model=DbCorruptionApiResponse)
def preview_db_corruption_repair(
    payload: DbCorruptionPreviewRequest,
) -> DbCorruptionApiResponse:
    report = DbCorruptionRepairService().preview(
        load_settings(),
        selected_delete_ids=tuple(payload.selected_delete_ids),
        backup_confirmed=payload.backup_confirmed,
        override_backup_requirement=payload.override_backup_requirement,
        maintenance_mode_confirmed=payload.maintenance_mode_confirmed,
        system_index_duplicate_error_text=payload.system_index_duplicate_error_text,
        high_risk_clear_pg_statistic_approval=payload.high_risk_clear_pg_statistic_approval,
        force_reindex_database=payload.force_reindex_database,
    )
    return DbCorruptionApiResponse(data=report.to_dict())


@repair_router.post("/db/corruption/apply", response_model=DbCorruptionApiResponse)
def apply_db_corruption_repair(
    payload: DbCorruptionApplyRequest,
) -> DbCorruptionApiResponse:
    report = DbCorruptionRepairService().apply(
        load_settings(),
        repair_run_id=payload.repair_run_id,
    )
    return DbCorruptionApiResponse(data=report.to_dict())
