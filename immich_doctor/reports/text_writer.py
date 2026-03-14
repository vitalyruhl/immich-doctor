from __future__ import annotations

from immich_doctor.core.models import ValidationReport


def render_text_report(report: ValidationReport) -> str:
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
    if report.sections:
        lines.append("Sections:")
        for section in report.sections:
            lines.append(f"- [{section.status.value.upper()}] {section.name}")
            if section.rows:
                for row in section.rows:
                    lines.append(f"  - {row}")
            else:
                lines.append("  - []")
    if report.metrics:
        lines.append("Metrics:")
        for metric in report.metrics:
            lines.append(f"- {metric}")
    if report.recommendations:
        lines.append("Recommendations:")
        for recommendation in report.recommendations:
            lines.append(f"- {recommendation}")
    return "\n".join(lines)
