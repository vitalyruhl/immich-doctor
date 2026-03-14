from __future__ import annotations

from immich_doctor.core.models import ValidationReport


def render_text_report(report: ValidationReport) -> str:
    lines = [
        f"Command: {report.command}",
        f"Overall status: {report.overall_status.value}",
        f"Generated at: {report.generated_at}",
    ]
    if report.metadata:
        lines.append(f"Metadata: {report.metadata}")
    lines.append("Checks:")
    for check in report.checks:
        lines.append(f"- [{check.status.value.upper()}] {check.name}: {check.message}")
    return "\n".join(lines)
