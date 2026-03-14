"""Helpers for deterministic versioned backup destination paths."""

from __future__ import annotations

import re
from dataclasses import dataclass

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
        timestamp_label = request.timestamp.strftime("%Y%m%dT%H%M%SZ")
        source_label = _slugify_label(request.source_label)
        destination_path = (
            request.target_root / timestamp_label / self.files_directory_name / source_label
        )
        return FileBackupExecutionPlan(request=request, destination_path=destination_path)
