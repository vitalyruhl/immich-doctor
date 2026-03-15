from __future__ import annotations

import json

from immich_doctor.core.models import CheckResult, RepairReport, ValidationReport


def render_text_report(report: ValidationReport | RepairReport, verbose: bool = False) -> str:
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
