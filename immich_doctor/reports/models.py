from __future__ import annotations

from typing import Any

from immich_doctor.core.models import RepairReport, ValidationReport


def build_report_payload(report: ValidationReport | RepairReport) -> dict[str, Any]:
    return report.to_dict()
