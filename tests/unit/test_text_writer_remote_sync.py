from __future__ import annotations

from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport
from immich_doctor.reports.text_writer import render_text_report


def test_remote_sync_text_output_includes_counts_and_samples() -> None:
    report = ValidationReport(
        domain="remote.sync",
        action="validate",
        summary="Remote sync validation found foreign key inconsistencies.",
        checks=[
            CheckResult(
                name="remote_album_asset_missing_assets",
                status=CheckStatus.FAIL,
                message=(
                    "Remote album asset rows with missing asset references: "
                    "found 2 broken references."
                ),
                details={
                    "severity": "error",
                    "count": 2,
                    "samples": [
                        {"asset_id": "asset-1", "album_id": "album-1"},
                        {"asset_id": "asset-2", "album_id": "album-2"},
                    ],
                    "impacted_tables": [
                        "public.remote_album_asset_entity",
                        "public.asset_entity",
                    ],
                    "remediation_hint": "Investigate manually.",
                },
            )
        ],
    )

    output = render_text_report(report)

    assert "severity=error, count=2" in output
    assert "impacted_tables=public.remote_album_asset_entity, public.asset_entity" in output
    assert "sample: asset_id=asset-1, album_id=album-1" in output
    assert "hint: Investigate manually." in output
