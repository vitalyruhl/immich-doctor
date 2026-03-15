from __future__ import annotations

from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport
from immich_doctor.reports.text_writer import render_text_report


def test_remote_sync_text_output_explains_scope_boundary() -> None:
    report = ValidationReport(
        domain="remote.sync",
        action="validate",
        summary=(
            "Remote sync validation completed. "
            "The reported SQLite signature is likely client-side; "
            "server-side PostgreSQL checks are reported separately below."
        ),
        checks=[
            CheckResult(
                name="remote_sync_scope_boundary",
                status=CheckStatus.PASS,
                message=(
                    "The reported `SqliteException(787)` / `remote_album_asset_entity` "
                    "signature matches a likely client-side mobile app SQLite remote-sync issue."
                ),
                details={
                    "severity": "warning",
                    "remediation_hint": "Inspect the mobile app local state separately.",
                },
            )
        ],
    )

    output = render_text_report(report)

    assert "likely client-side mobile app sqlite remote-sync issue" in output.lower()
    assert "hint: Inspect the mobile app local state separately." in output


def test_remote_sync_text_output_includes_server_counts_and_samples() -> None:
    report = ValidationReport(
        domain="remote.sync",
        action="validate",
        summary="Remote sync validation found server-side PostgreSQL album/asset link issues.",
        checks=[
            CheckResult(
                name="album_asset_missing_assets",
                status=CheckStatus.FAIL,
                message=(
                    "Server-side `album_asset` rows with missing assets: found 2 broken references."
                ),
                details={
                    "severity": "error",
                    "count": 2,
                    "samples": [
                        {"albumId": "album-1", "assetsId": "asset-1"},
                        {"albumId": "album-2", "assetsId": "asset-2"},
                    ],
                    "impacted_tables": [
                        "public.album_asset",
                        "public.asset",
                    ],
                    "remediation_hint": "Review server-side data manually.",
                },
            )
        ],
    )

    output = render_text_report(report)

    assert "severity=error, count=2" in output
    assert "impacted_tables=public.album_asset, public.asset" in output
    assert "sample: albumId=album-1, assetsId=asset-1" in output
    assert "hint: Review server-side data manually." in output
