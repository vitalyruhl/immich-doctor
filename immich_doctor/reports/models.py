from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

from immich_doctor.backup.restore.models import RestoreSimulationResult
from immich_doctor.consistency.models import ConsistencyRepairResult, ConsistencyValidationReport
from immich_doctor.core.models import RepairReport, ValidationReport
from immich_doctor.repair.undo_models import UndoExecutionResult, UndoPlanResult
from immich_doctor.runtime.integrity.models import FileIntegrityInspectResult
from immich_doctor.runtime.metadata_failures.models import (
    MetadataFailureInspectResult,
    MetadataFailureRepairResult,
)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID | Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_safe(item) for item in value]
    if hasattr(value, "to_dict"):
        return _json_safe(value.to_dict())
    return str(value)


def build_report_payload(
    report: ValidationReport
    | RepairReport
    | ConsistencyValidationReport
    | ConsistencyRepairResult
    | RestoreSimulationResult
    | FileIntegrityInspectResult
    | MetadataFailureInspectResult
    | MetadataFailureRepairResult
    | UndoPlanResult
    | UndoExecutionResult,
) -> dict[str, Any]:
    return _json_safe(report.to_dict())
