from __future__ import annotations

from typing import Any

from immich_doctor.core.models import ValidationReport
from immich_doctor.reports.models import build_report_payload


def render_json_report(report: ValidationReport) -> dict[str, Any]:
    return build_report_payload(report)
