from __future__ import annotations

from typing import Any

from immich_doctor.consistency.models import ConsistencyRepairResult, ConsistencyValidationReport
from immich_doctor.core.models import RepairReport, ValidationReport
from immich_doctor.reports.models import build_report_payload
from immich_doctor.runtime.integrity.models import FileIntegrityInspectResult
from immich_doctor.runtime.metadata_failures.models import (
    MetadataFailureInspectResult,
    MetadataFailureRepairResult,
)


def render_json_report(
    report: ValidationReport
    | RepairReport
    | ConsistencyValidationReport
    | ConsistencyRepairResult
    | FileIntegrityInspectResult
    | MetadataFailureInspectResult
    | MetadataFailureRepairResult,
) -> dict[str, Any]:
    return build_report_payload(report)
