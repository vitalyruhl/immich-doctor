"""Helpers for deterministic versioned backup destination paths."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from immich_doctor.backup.files.models import FileBackupExecutionPlan, FileBackupRequest

_NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")


def _slugify_label(label: str) -> str:
    normalized = _NON_ALNUM_PATTERN.sub("-", label.strip().lower()).strip("-")
    return normalized or "files"


@dataclass(slots=True)
class VersionedDestinationBuilder:
    """Builds timestamped local file-backup destinations without creating them."""

    files_directory_name: str = "files"

    def build(self, request: FileBackupRequest) -> FileBackupExecutionPlan:
        timestamp_label = request.context.started_at.strftime("%Y%m%dT%H%M%SZ")
        source_label = _slugify_label(request.source_label)
        artifact_relative_path = Path(self.files_directory_name) / source_label
        backup_root_path = request.location.root_path / timestamp_label
        destination_path = backup_root_path / artifact_relative_path
        return FileBackupExecutionPlan(
            request=request,
            backup_root_path=backup_root_path,
            artifact_relative_path=artifact_relative_path,
            destination_path=destination_path,
        )
