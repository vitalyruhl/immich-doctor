from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from immich_doctor.consistency.models import (
    ConsistencySummary,
    ConsistencyValidationReport,
)
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.reports.json_writer import render_json_report


def test_render_json_report_normalizes_non_json_native_values() -> None:
    sample_uuid = uuid4()
    report = ConsistencyValidationReport(
        domain="consistency",
        action="validate",
        summary="summary",
        checks=[
            CheckResult(
                name="sample",
                status=CheckStatus.PASS,
                message="ok",
                details={"sample_uuid": sample_uuid},
            )
        ],
        categories=[],
        findings=[],
        consistency_summary=ConsistencySummary(
            profile_name="schema-aware",
            profile_supported=True,
            support_status="supported",
        ),
        metadata={
            "sample_uuid": sample_uuid,
            "sample_path": Path("/tmp/example"),
        },
    )

    payload = render_json_report(report)

    assert payload["metadata"]["sample_uuid"] == str(sample_uuid)
    assert payload["metadata"]["sample_path"] == str(Path("/tmp/example"))
    assert payload["checks"][0]["details"]["sample_uuid"] == str(sample_uuid)
