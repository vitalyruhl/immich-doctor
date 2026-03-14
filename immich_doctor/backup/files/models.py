"""Domain-level request and plan models for future file backup workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from immich_doctor.backup.core.models import BackupContext


@dataclass(slots=True, frozen=True)
class FileBackupRequest:
    """Describes one local source to local target file backup request."""

    context: BackupContext
    source_path: Path
    target_root: Path
    source_label: str
    timestamp: datetime


@dataclass(slots=True, frozen=True)
class FileBackupExecutionPlan:
    """Carries the resolved destination path and command-ready backup request."""

    request: FileBackupRequest
    destination_path: Path
