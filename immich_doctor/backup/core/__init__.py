"""Core backup abstractions shared by future backup workflows."""

from immich_doctor.backup.core.models import (
    BackupArtifact,
    BackupContext,
    BackupJob,
    BackupManifest,
    BackupResult,
    BackupTarget,
)
from immich_doctor.backup.core.resolver import BackupLocationResolver

__all__ = [
    "BackupArtifact",
    "BackupContext",
    "BackupJob",
    "BackupLocationResolver",
    "BackupManifest",
    "BackupResult",
    "BackupTarget",
]
