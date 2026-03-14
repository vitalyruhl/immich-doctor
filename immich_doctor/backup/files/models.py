"""Domain-level request and plan models for future file backup workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from immich_doctor.backup.core.models import BackupContext, ResolvedBackupLocation


@dataclass(slots=True, frozen=True)
class FileBackupRequest:
    """Describes one local source to local target file backup request."""

    context: BackupContext
    location: ResolvedBackupLocation
    source_path: Path
    source_label: str


@dataclass(slots=True, frozen=True)
class FileBackupExecutionPlan:
    """Carries the resolved destination path and command-ready backup request."""

    request: FileBackupRequest
    backup_root_path: Path
    artifact_relative_path: Path
    destination_path: Path
