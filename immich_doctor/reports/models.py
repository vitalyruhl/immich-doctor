from __future__ import annotations

from typing import Any

from immich_doctor.core.models import ValidationReport


def build_report_payload(report: ValidationReport) -> dict[str, Any]:
    return report.to_dict()
