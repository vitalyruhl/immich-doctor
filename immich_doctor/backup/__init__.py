"""Backup domain package and shared abstractions."""

from immich_doctor.backup.core.models import (
    BackupArtifact,
    BackupContext,
    BackupJob,
    BackupManifest,
    BackupResult,
    BackupTarget,
    ResolvedBackupLocation,
)
from immich_doctor.backup.core.resolver import BackupLocationResolver

__all__ = [
    "BackupArtifact",
    "BackupContext",
    "BackupJob",
    "BackupLocationResolver",
    "BackupManifest",
    "BackupResult",
    "ResolvedBackupLocation",
    "BackupTarget",
]
