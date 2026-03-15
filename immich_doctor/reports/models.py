from __future__ import annotations

from typing import Any

from immich_doctor.consistency.models import ConsistencyRepairResult, ConsistencyValidationReport
from immich_doctor.core.models import RepairReport, ValidationReport


def build_report_payload(
    report: ValidationReport | RepairReport | ConsistencyValidationReport | ConsistencyRepairResult,
) -> dict[str, Any]:
    return report.to_dict()
