from __future__ import annotations

import json

from immich_doctor.backup.restore.models import RestoreSimulationResult
from immich_doctor.consistency.models import (
    ConsistencyRepairResult,
    ConsistencyValidationReport,
)
from immich_doctor.core.models import CheckResult, RepairReport, ValidationReport
from immich_doctor.repair.undo_models import UndoExecutionResult, UndoPlanResult
from immich_doctor.runtime.integrity.models import FileIntegrityInspectResult
from immich_doctor.runtime.metadata_failures.models import (
    MetadataFailureInspectResult,
    MetadataFailureRepairResult,
)


def render_text_report(
    report: ValidationReport
    | RepairReport
    | ConsistencyValidationReport
    | ConsistencyRepairResult
    | RestoreSimulationResult
    | FileIntegrityInspectResult
    | MetadataFailureInspectResult
    | MetadataFailureRepairResult
    | UndoPlanResult
    | UndoExecutionResult,
    verbose: bool = False,
) -> str:
    if isinstance(report, ConsistencyValidationReport):
        return _render_consistency_validation_report(report, verbose)
    if isinstance(report, ConsistencyRepairResult):
        return _render_consistency_repair_report(report, verbose)
    if isinstance(report, FileIntegrityInspectResult):
        return _render_file_integrity_report(report, verbose)
    if isinstance(report, MetadataFailureInspectResult):
        return _render_metadata_failure_inspect_report(report, verbose)
    if isinstance(report, MetadataFailureRepairResult):
        return _render_metadata_failure_repair_report(report, verbose)
    if isinstance(report, UndoPlanResult):
        return _render_undo_plan_report(report, verbose)
    if isinstance(report, UndoExecutionResult):
        return _render_undo_execution_report(report, verbose)
    if isinstance(report, RestoreSimulationResult):
        return _render_restore_simulation_report(report, verbose)

    lines = [
        f"Domain: {report.domain}",
        f"Action: {report.action}",
        f"Status: {report.overall_status.value.upper()}",
        f"Summary: {report.summary}",
        f"Generated at: {report.generated_at}",
    ]
    if report.metadata:
        lines.append(f"Metadata: {report.metadata}")
    if report.checks:
        lines.append("Checks:")
        for check in report.checks:
            lines.append(f"- [{check.status.value.upper()}] {check.name}: {check.message}")
            if report.domain == "remote.sync":
                lines.extend(_render_remote_sync_check_details(check, verbose))
    if isinstance(report, RepairReport) and report.plans:
        lines.append("Plans:")
        for plan in report.plans:
            lines.append(
                f"- [{plan.status.value.upper()}] {plan.action} {plan.target_table}: "
                f"{plan.reason} ({plan.row_count} rows)"
            )
            lines.append(
                f"  - dry_run={plan.dry_run}, applied={plan.applied}, "
                f"key_columns={', '.join(plan.key_columns) if plan.key_columns else '[]'}"
            )
            if plan.sample_rows:
                preview_limit = len(plan.sample_rows) if verbose else 3
                preview, truncated = _preview_rows(plan.sample_rows, limit=preview_limit)
                for item in preview:
                    lines.append(f"  - sample: {item}")
                if truncated:
                    lines.append("  - sample: ...")
            if plan.backup_sql:
                lines.append(f"  - backup_sql: {plan.backup_sql}")
    sections = getattr(report, "sections", [])
    if sections and not verbose and report.domain == "db.performance.indexes":
        lines.extend(_render_compact_db_index_sections(report))
    elif sections:
        lines.append("Sections:")
        for section in sections:
            lines.append(f"- [{section.status.value.upper()}] {section.name}")
            if section.rows:
                for row in section.rows:
                    lines.append(f"  - {row}")
            else:
                lines.append("  - []")
    metrics = getattr(report, "metrics", [])
    if metrics:
        lines.append("Metrics:")
        for metric in metrics:
            lines.append(f"- {metric}")
    recommendations = getattr(report, "recommendations", [])
    if recommendations:
        lines.append("Recommendations:")
        for recommendation in recommendations:
            lines.append(f"- {recommendation}")
    return "\n".join(lines)


def _render_consistency_validation_report(
    report: ConsistencyValidationReport,
    verbose: bool,
) -> str:
    lines = [
        f"Domain: {report.domain}",
        f"Action: {report.action}",
        f"Status: {report.overall_status.value.upper()}",
        f"Summary: {report.summary}",
        f"Generated at: {report.generated_at}",
    ]
    if report.metadata:
        lines.append(f"Metadata: {report.metadata}")
    lines.append("Checks:")
    for check in report.checks:
        lines.append(f"- [{check.status.value.upper()}] {check.name}: {check.message}")
    lines.append("Database State:")
    lines.append(
        f"- support_status={report.consistency_summary.support_status}, "
        f"product_version={report.consistency_summary.product_version_current or 'unknown'}, "
        f"confidence={report.consistency_summary.product_version_confidence}"
    )
    lines.append(
        f"- schema_generation_key={report.consistency_summary.schema_generation_key}, "
        f"schema_fingerprint={report.consistency_summary.schema_fingerprint}"
    )
    lines.append(
        f"- asset_reference_column={report.consistency_summary.asset_reference_column}, "
        f"risk_flags={list(report.consistency_summary.risk_flags)}"
    )
    lines.append("Categories:")
    for category in report.categories:
        repairability = "REPAIRABLE" if category.repairable else "INSPECT_ONLY"
        lines.append(
            f"- [{category.status.value.upper()}] {category.name}: "
            f"count={category.count}, severity={category.severity.value}, "
            f"repair_mode={category.repair_mode.value}, {repairability}"
        )
        lines.append(f"  - {category.message}")
        preview = category.sample_findings if verbose else category.sample_findings[:3]
        for finding in preview:
            lines.append(
                f"  - finding: id={finding.finding_id}, rows={finding.row_count}, "
                f"message={finding.message}"
            )
        if not preview:
            lines.append("  - finding: []")
    lines.append(f"Consistency Summary: {report.consistency_summary.to_dict()}")
    if report.recommendations:
        lines.append("Recommendations:")
        for recommendation in report.recommendations:
            lines.append(f"- {recommendation}")
    return "\n".join(lines)


def _render_consistency_repair_report(
    report: ConsistencyRepairResult,
    verbose: bool,
) -> str:
    lines = [
        f"Domain: {report.domain}",
        f"Action: {report.action}",
        f"Status: {report.overall_status.value.upper()}",
        f"Summary: {report.summary}",
        f"Generated at: {report.generated_at}",
    ]
    if report.metadata:
        lines.append(f"Metadata: {report.metadata}")
    lines.append("Checks:")
    for check in report.checks:
        lines.append(f"- [{check.status.value.upper()}] {check.name}: {check.message}")
    lines.append("Database State:")
    lines.append(
        f"- support_status={report.consistency_summary.support_status}, "
        f"product_version={report.consistency_summary.product_version_current or 'unknown'}, "
        f"confidence={report.consistency_summary.product_version_confidence}"
    )
    lines.append(
        f"- schema_generation_key={report.consistency_summary.schema_generation_key}, "
        f"schema_fingerprint={report.consistency_summary.schema_fingerprint}"
    )
    lines.append(
        f"- asset_reference_column={report.consistency_summary.asset_reference_column}, "
        f"risk_flags={list(report.consistency_summary.risk_flags)}"
    )
    lines.append("Repair Plan:")
    lines.append(
        f"- selected_categories={list(report.repair_plan.selected_categories)}, "
        f"selected_ids={list(report.repair_plan.selected_ids)}, "
        f"all_safe={report.repair_plan.all_safe}"
    )
    for action in report.repair_plan.actions:
        lines.append(
            f"- [{action.status.value.upper()}] {action.category}: "
            f"{action.message} ({action.row_count} rows)"
        )
        lines.append(
            f"  - repair_mode={action.repair_mode.value}, dry_run={action.dry_run}, "
            f"applied={action.applied}, target_table={action.target_table}"
        )
        preview = action.sample_findings if verbose else action.sample_findings[:3]
        for finding in preview:
            lines.append(
                f"  - finding: id={finding.finding_id}, rows={finding.row_count}, "
                f"message={finding.message}"
            )
        if action.backup_sql:
            lines.append(f"  - backup_sql: {action.backup_sql}")
    lines.append(f"Consistency Summary: {report.consistency_summary.to_dict()}")
    if report.recommendations:
        lines.append("Recommendations:")
        for recommendation in report.recommendations:
            lines.append(f"- {recommendation}")
    return "\n".join(lines)


def _render_compact_db_index_sections(report: ValidationReport) -> list[str]:
    lines = ["Sections:"]
    hidden_details = False

    for section in report.sections:
        row_count = len(section.rows)

        if section.name == "INDEX_LIST":
            lines.append(
                f"- [{section.status.value.upper()}] {section.name}: {row_count} indexes found."
            )
            if row_count:
                hidden_details = True
            continue

        if section.name == "INVALID_INDEXES":
            lines.append(
                f"- [{section.status.value.upper()}] {section.name}: {row_count} invalid indexes."
            )
            preview, truncated = _preview_rows(section.rows, limit=3)
            if preview:
                hidden_details = True
                lines.extend(f"  - {item}" for item in preview)
            if truncated:
                hidden_details = True
            continue

        if section.name == "MISSING_FK_INDEXES":
            lines.append(
                f"- [{section.status.value.upper()}] {section.name}: "
                f"{row_count} foreign keys without supporting indexes."
            )
            preview, truncated = _preview_rows(section.rows, limit=3)
            if preview:
                hidden_details = True
                lines.extend(f"  - {item}" for item in preview)
            if truncated:
                hidden_details = True
            continue

        if section.name == "UNUSED_INDEXES":
            lines.append(
                f"- [{section.status.value.upper()}] {section.name}: "
                f"{row_count} indexes with idx_scan = 0."
            )
            preview, truncated = _preview_rows(section.rows, limit=3)
            if preview:
                hidden_details = True
                lines.extend(f"  - {item}" for item in preview)
            if truncated:
                hidden_details = True
            continue

        if section.name == "LARGE_INDEXES":
            visible_rows = [row for row in section.rows if row.get("index_size") != "0 bytes"]
            preview_rows = visible_rows[:5]
            hidden_zero_byte = row_count != len(visible_rows)
            hidden_more = len(visible_rows) > len(preview_rows)

            lines.append(
                f"- [{section.status.value.upper()}] {section.name}: "
                f"showing {len(preview_rows)} of {len(visible_rows)} non-empty index sizes."
            )
            if preview_rows:
                lines.extend(f"  - {_format_row(row)}" for row in preview_rows)
            else:
                lines.append("  - []")
            if hidden_zero_byte or hidden_more:
                hidden_details = True
            continue

        lines.append(f"- [{section.status.value.upper()}] {section.name}: {row_count} entries.")
        if row_count:
            hidden_details = True

    if hidden_details:
        lines.append("Hint: Use --verbose for full diagnostic details.")

    return lines


def _preview_rows(rows: list[dict[str, object]], limit: int) -> tuple[list[str], bool]:
    preview = [_format_row(row) for row in rows[:limit]]
    return preview, len(rows) > limit


def _render_remote_sync_check_details(check: CheckResult, verbose: bool) -> list[str]:
    details = check.details
    if not details:
        return []

    lines: list[str] = []
    count = details.get("count")
    severity = details.get("severity")
    impacted_tables = details.get("impacted_tables")
    candidates = details.get("candidates")
    detected_columns = details.get("detected_columns")
    expected_table = details.get("expected_table")
    remediation_hint = details.get("remediation_hint")
    samples = details.get("samples", [])

    if severity or count is not None:
        summary_parts: list[str] = []
        if severity:
            summary_parts.append(f"severity={severity}")
        if count is not None:
            summary_parts.append(f"count={count}")
        lines.append(f"  - {', '.join(summary_parts)}")

    if impacted_tables:
        lines.append(f"  - impacted_tables={', '.join(str(table) for table in impacted_tables)}")

    if expected_table:
        lines.append(f"  - expected_table={expected_table}")

    if detected_columns:
        lines.append(
            f"  - detected_columns={', '.join(str(column) for column in detected_columns)}"
        )

    if candidates and verbose:
        lines.append(f"  - candidates={', '.join(str(candidate) for candidate in candidates)}")

    preview_limit = len(samples) if verbose else 3
    preview, truncated = _preview_rows(list(samples), limit=preview_limit)
    for item in preview:
        lines.append(f"  - sample: {item}")
    if truncated:
        lines.append("  - sample: ...")

    if remediation_hint:
        lines.append(f"  - hint: {remediation_hint}")

    return lines


def _format_row(row: dict[str, object]) -> str:
    preferred_keys = [
        "albumId",
        "assetsId",
        "assetId",
        "asset_id",
        "album_id",
        "index_name",
        "table_name",
        "conname",
        "constraint_definition",
        "index_size",
        "indisvalid",
        "indisready",
        "idx_scan",
    ]
    parts = [f"{key}={row[key]}" for key in preferred_keys if key in row]
    if parts:
        return ", ".join(parts)
    return json.dumps(row, ensure_ascii=True, sort_keys=True)


def _render_file_integrity_report(report: FileIntegrityInspectResult, verbose: bool) -> str:
    lines = [
        f"Domain: {report.domain}",
        f"Action: {report.action}",
        f"Status: {report.overall_status.value.upper()}",
        f"Summary: {report.summary}",
        f"Generated at: {report.generated_at}",
    ]
    if report.metadata:
        lines.append(f"Metadata: {report.metadata}")
    lines.append("Checks:")
    for check in report.checks:
        lines.append(f"- [{check.status.value.upper()}] {check.name}: {check.message}")
    lines.append("Integrity Summary:")
    for item in report.summary_items:
        lines.append(f"- {item.status.value}: {item.count}")
    lines.append("Findings:")
    preview = report.findings if verbose else report.findings[:10]
    for finding in preview:
        lines.append(
            f"- [{finding.status.value}] asset_id={finding.asset_id}, "
            f"role={finding.file_role.value}, path={finding.path}"
        )
        lines.append(f"  - message={finding.message}")
        lines.append(
            f"  - detected_format={finding.detected_format}, size_bytes={finding.size_bytes}, "
            f"media_kind={finding.media_kind.value}"
        )
    if len(report.findings) > len(preview):
        lines.append("- ...")
    if report.recommendations:
        lines.append("Recommendations:")
        for recommendation in report.recommendations:
            lines.append(f"- {recommendation}")
    return "\n".join(lines)


def _render_metadata_failure_inspect_report(
    report: MetadataFailureInspectResult,
    verbose: bool,
) -> str:
    lines = [
        f"Domain: {report.domain}",
        f"Action: {report.action}",
        f"Status: {report.overall_status.value.upper()}",
        f"Summary: {report.summary}",
        f"Generated at: {report.generated_at}",
    ]
    if report.metadata:
        lines.append(f"Metadata: {report.metadata}")
    lines.append("Checks:")
    for check in report.checks:
        lines.append(f"- [{check.status.value.upper()}] {check.name}: {check.message}")
    lines.append("Integrity Summary:")
    for item in report.integrity_summary:
        lines.append(f"- {item['status']}: {item['count']}")
    lines.append("Metadata Failure Summary:")
    for item in report.metadata_summary:
        lines.append(f"- {item.root_cause.value}: {item.count}")
    lines.append("Diagnostics:")
    preview = report.diagnostics if verbose else report.diagnostics[:10]
    for diagnostic in preview:
        lines.append(
            f"- asset_id={diagnostic.asset_id}, root_cause={diagnostic.root_cause.value}, "
            f"level={diagnostic.failure_level.value}, confidence={diagnostic.confidence.value}"
        )
        lines.append(
            f"  - path={diagnostic.source_path}, file_status={diagnostic.source_file_status}"
        )
        lines.append(f"  - message={diagnostic.source_message}")
        lines.append(
            f"  - suggested_action={diagnostic.suggested_action.value}, "
            f"available_actions={[action.value for action in diagnostic.available_actions]}"
        )
    if len(report.diagnostics) > len(preview):
        lines.append("- ...")
    if report.recommendations:
        lines.append("Recommendations:")
        for recommendation in report.recommendations:
            lines.append(f"- {recommendation}")
    return "\n".join(lines)


def _render_metadata_failure_repair_report(
    report: MetadataFailureRepairResult,
    verbose: bool,
) -> str:
    lines = [
        f"Domain: {report.domain}",
        f"Action: {report.action}",
        f"Status: {report.overall_status.value.upper()}",
        f"Summary: {report.summary}",
        f"Generated at: {report.generated_at}",
    ]
    if report.metadata:
        lines.append(f"Metadata: {report.metadata}")
    lines.append("Checks:")
    for check in report.checks:
        lines.append(f"- [{check.status.value.upper()}] {check.name}: {check.message}")
    lines.append("Repair Actions:")
    for action in report.repair_actions:
        lines.append(
            f"- [{action.status.value.upper()}] {action.action.value}: "
            f"diagnostic={action.diagnostic_id}, path={action.path}"
        )
        lines.append(
            f"  - supports_apply={action.supports_apply}, dry_run={action.dry_run}, "
            f"applied={action.applied}"
        )
        lines.append(f"  - reason={action.reason}")
    if verbose:
        lines.append("Diagnostics:")
        for diagnostic in report.diagnostics:
            lines.append(
                f"- asset_id={diagnostic.asset_id}, root_cause={diagnostic.root_cause.value}, "
                f"suggested_action={diagnostic.suggested_action.value}"
            )
    if report.post_validation:
        lines.append("Post Validation:")
        lines.append(f"- Summary: {report.post_validation.summary}")
        for item in report.post_validation.metadata_summary:
            lines.append(f"  - {item.root_cause.value}: {item.count}")
    if report.recommendations:
        lines.append("Recommendations:")
        for recommendation in report.recommendations:
            lines.append(f"- {recommendation}")
    return "\n".join(lines)


def _render_undo_plan_report(report: UndoPlanResult, verbose: bool) -> str:
    lines = [
        f"Domain: {report.domain}",
        f"Action: {report.action}",
        f"Status: {report.overall_status.value.upper()}",
        f"Summary: {report.summary}",
        f"Generated at: {report.generated_at}",
        f"Repair run: {report.repair_run_id}",
        f"Target status: {report.target_repair_run_status}",
        f"Eligibility: {report.eligibility.value}",
        f"Apply allowed: {report.apply_allowed}",
    ]
    if report.metadata:
        lines.append(f"Metadata: {report.metadata}")
    lines.append("Checks:")
    for check in report.checks:
        lines.append(f"- [{check.status.value.upper()}] {check.name}: {check.message}")
    if report.blockers:
        lines.append("Blockers:")
        for blocker in report.blockers:
            lines.append(f"- [{blocker.severity.upper()}] {blocker.code}: {blocker.message}")
    lines.append("Entry Assessments:")
    for entry in report.entry_assessments:
        lines.append(
            f"- [{entry.eligibility.value}] {entry.operation_type}: "
            f"entry_id={entry.entry_id}, path={entry.original_path}"
        )
        if verbose and entry.details:
            lines.append(f"  - details={entry.details}")
        for blocker in entry.blockers:
            lines.append(f"  - blocker={blocker.code}: {blocker.message}")
    if report.recommendations:
        lines.append("Recommendations:")
        for recommendation in report.recommendations:
            lines.append(f"- {recommendation}")
    return "\n".join(lines)


def _render_undo_execution_report(report: UndoExecutionResult, verbose: bool) -> str:
    lines = [
        f"Domain: {report.domain}",
        f"Action: {report.action}",
        f"Status: {report.overall_status.value.upper()}",
        f"Summary: {report.summary}",
        f"Generated at: {report.generated_at}",
        f"Undo repair run: {report.repair_run_id or 'dry-run'}",
        f"Target repair run: {report.target_repair_run_id}",
        f"Eligibility: {report.eligibility.value}",
    ]
    if report.metadata:
        lines.append(f"Metadata: {report.metadata}")
    lines.append("Checks:")
    for check in report.checks:
        lines.append(f"- [{check.status.value.upper()}] {check.name}: {check.message}")
    if report.blockers:
        lines.append("Blockers:")
        for blocker in report.blockers:
            lines.append(f"- [{blocker.severity.upper()}] {blocker.code}: {blocker.message}")
    lines.append("Execution Items:")
    for item in report.execution_items:
        lines.append(
            f"- [{item.status.value.upper()}] {item.operation_type}: "
            f"entry_id={item.entry_id}, path={item.original_path}"
        )
        lines.append(f"  - message={item.message}")
        if verbose and item.details:
            lines.append(f"  - details={item.details}")
    if report.recommendations:
        lines.append("Recommendations:")
        for recommendation in report.recommendations:
            lines.append(f"- {recommendation}")
    return "\n".join(lines)


def _render_restore_simulation_report(
    report: RestoreSimulationResult,
    verbose: bool,
) -> str:
    lines = [
        f"Domain: {report.domain}",
        f"Action: {report.action}",
        f"Status: {report.overall_status.value.upper()}",
        f"Summary: {report.summary}",
        f"Generated at: {report.generated_at}",
        f"Readiness: {report.readiness.value}",
    ]
    if report.metadata:
        lines.append(f"Metadata: {report.metadata}")
    if report.selected_snapshot:
        lines.append(f"Selected Snapshot: {report.selected_snapshot}")
    lines.append("Checks:")
    for check in report.checks:
        lines.append(f"- [{check.status.value.upper()}] {check.name}: {check.message}")
    if report.blockers:
        lines.append("Blockers:")
        for blocker in report.blockers:
            lines.append(f"- [{blocker.severity.upper()}] {blocker.code}: {blocker.message}")
    lines.append("Instructions:")
    for instruction in report.instructions:
        lines.append(f"- {instruction.phase}/{instruction.step_id}: {instruction.description}")
        if verbose and instruction.command:
            lines.append(f"  - command={instruction.command}")
    if report.recommendations:
        lines.append("Recommendations:")
        for recommendation in report.recommendations:
            lines.append(f"- {recommendation}")
    return "\n".join(lines)
