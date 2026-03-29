from __future__ import annotations

from immich_doctor.consistency.models import (
    ConsistencyCategory,
    ConsistencyFinding,
    ConsistencyRepairAction,
    ConsistencyRepairMode,
    ConsistencyRepairPlan,
    ConsistencyRepairResult,
    ConsistencyRepairStatus,
    ConsistencySeverity,
    ConsistencySummary,
    ConsistencyValidationReport,
)
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.reports.text_writer import render_text_report


def _summary(profile_supported: bool = True) -> ConsistencySummary:
    return ConsistencySummary(
        profile_name="immich_db_schema_detection_v1",
        profile_supported=profile_supported,
        support_status="supported" if profile_supported else "unsupported",
        product_version_current="2.5.6" if profile_supported else None,
        product_version_confidence="high" if profile_supported else "unknown",
        schema_generation_key="immich_schema:album_asset.assetId+memory_asset+album_thumbnail_asset+stack_primary_asset+version_history",
        schema_fingerprint="abc123",
        asset_reference_column="assetId" if profile_supported else None,
        risk_flags=(),
        executed_categories=("db.orphan.album_asset.missing_asset",) if profile_supported else (),
    )


def test_consistency_validation_text_output_groups_by_category() -> None:
    report = ConsistencyValidationReport(
        domain="consistency",
        action="validate",
        summary="Consistency validation found repairable server-side PostgreSQL orphan links.",
        checks=[CheckResult(name="schema_profile", status=CheckStatus.PASS, message="Supported.")],
        categories=[
            ConsistencyCategory(
                name="db.orphan.album_asset.missing_asset",
                severity=ConsistencySeverity.FAIL,
                repair_mode=ConsistencyRepairMode.SAFE_DELETE,
                status=CheckStatus.FAIL,
                count=2,
                repairable=True,
                message="Orphan album_asset rows whose assetId references no asset row.",
                sample_findings=(
                    ConsistencyFinding(
                        category="db.orphan.album_asset.missing_asset",
                        finding_id="album_asset:missing_asset:album-1:asset-missing-1",
                        severity=ConsistencySeverity.FAIL,
                        repair_mode=ConsistencyRepairMode.SAFE_DELETE,
                        affected_tables=("public.album_asset", "public.asset"),
                        key_fields={"albumId": "album-1", "assetId": "asset-missing-1"},
                        message="album_asset references a missing asset row.",
                    ),
                ),
            )
        ],
        findings=[],
        consistency_summary=_summary(),
    )

    output = render_text_report(report)

    assert "Database State:" in output
    assert "product_version=2.5.6" in output
    assert "asset_reference_column=assetId" in output
    assert "Categories:" in output
    assert "db.orphan.album_asset.missing_asset" in output
    assert "REPAIRABLE" in output


def test_consistency_repair_text_output_shows_selected_scope() -> None:
    report = ConsistencyRepairResult(
        domain="consistency",
        action="repair",
        summary="Consistency repair dry-run planned changes for 1 selected repairable rows.",
        checks=[CheckResult(name="schema_profile", status=CheckStatus.PASS, message="Supported.")],
        repair_plan=ConsistencyRepairPlan(
            selected_categories=("db.orphan.album_asset.missing_asset",),
            selected_ids=(),
            all_safe=False,
            actions=(
                ConsistencyRepairAction(
                    category="db.orphan.album_asset.missing_asset",
                    repair_mode=ConsistencyRepairMode.SAFE_DELETE,
                    status=ConsistencyRepairStatus.WOULD_REPAIR,
                    message="Dry-run would repair category `db.orphan.album_asset.missing_asset`.",
                    target_table="public.album_asset",
                    finding_ids=("album_asset:missing_asset:album-1:asset-missing-1",),
                    row_count=1,
                    dry_run=True,
                    applied=False,
                ),
            ),
        ),
        consistency_summary=_summary(),
    )

    output = render_text_report(report)

    assert "Database State:" in output
    assert "selected_categories=['db.orphan.album_asset.missing_asset']" in output
    assert "[WOULD_REPAIR] db.orphan.album_asset.missing_asset" in output
