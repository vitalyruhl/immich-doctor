from __future__ import annotations

import json
from typing import Any

from immich_doctor.backup.core.models import BackupResult


def render_backup_result_json(result: BackupResult) -> dict[str, Any]:
    return result.to_dict()


def render_backup_result_text(result: BackupResult) -> str:
    lines = [
        f"Domain: {result.domain}",
        f"Action: {result.action}",
        f"Status: {result.status.upper()}",
        f"Summary: {result.summary}",
        f"Started at: {result.context.started_at.isoformat()}",
        f"Target: {result.context.target.reference}",
    ]

    if result.artifacts:
        lines.append("Artifacts:")
        for artifact in result.artifacts:
            lines.append(
                f"- {artifact.name}: {artifact.relative_path.as_posix()} "
                f"(root={artifact.target.reference})"
            )

    if result.snapshot is not None:
        lines.append("Snapshot Record:")
        lines.append(
            f"- id={result.snapshot.snapshot_id}, kind={result.snapshot.kind.value}, "
            f"coverage={result.snapshot.coverage.value}, "
            f"manifest={result.snapshot.manifest_path.as_posix()}"
        )

    if result.warnings:
        lines.append("Warnings:")
        for warning in result.warnings:
            lines.append(f"- {warning}")

    if result.details:
        lines.append(f"Details: {json.dumps(result.details, ensure_ascii=True, sort_keys=True)}")

    return "\n".join(lines)
