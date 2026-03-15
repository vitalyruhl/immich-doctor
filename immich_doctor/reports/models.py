from __future__ import annotations

from typing import Any

from immich_doctor.backup.restore.models import RestoreSimulationResult
from immich_doctor.consistency.models import ConsistencyRepairResult, ConsistencyValidationReport
from immich_doctor.core.models import RepairReport, ValidationReport
from immich_doctor.repair.undo_models import UndoExecutionResult, UndoPlanResult
from immich_doctor.runtime.integrity.models import FileIntegrityInspectResult
from immich_doctor.runtime.metadata_failures.models import (
    MetadataFailureInspectResult,
    MetadataFailureRepairResult,
)


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
    return report.to_dict()
