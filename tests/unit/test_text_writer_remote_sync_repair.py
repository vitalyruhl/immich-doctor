from __future__ import annotations

from immich_doctor.core.models import (
    CheckResult,
    CheckStatus,
    RepairItemStatus,
    RepairPlanItem,
    RepairReport,
)
from immich_doctor.reports.text_writer import render_text_report


def test_remote_sync_repair_text_output_shows_planned_deletions() -> None:
    report = RepairReport(
        domain="remote.sync",
        action="repair",
        summary="Remote sync repair dry-run planned deletion of 2 orphan album_asset rows.",
        checks=[
            CheckResult(
                name="remote_sync_scope_boundary",
                status=CheckStatus.PASS,
                message="Repair scope is limited to PostgreSQL album_asset rows.",
            )
        ],
        plans=[
            RepairPlanItem(
                action="delete",
                target_table="public.album_asset",
                reason="orphan album_asset rows with missing asset references",
                key_columns=("assetsId", "albumId"),
                row_count=2,
                sample_rows=[{"albumId": "album-1", "assetsId": "asset-missing-1"}],
                dry_run=True,
                applied=False,
                status=RepairItemStatus.PLANNED,
                backup_sql="CREATE TABLE backup AS SELECT * FROM public.album_asset;",
            )
        ],
    )

    output = render_text_report(report)

    assert "[PLANNED] delete public.album_asset" in output
    assert "dry_run=True, applied=False" in output
    assert "sample: albumId=album-1, assetsId=asset-missing-1" in output
    assert "backup_sql: CREATE TABLE backup AS SELECT * FROM public.album_asset;" in output
