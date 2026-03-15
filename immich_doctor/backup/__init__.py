"""Backup domain package and shared abstractions."""

from immich_doctor.backup.core.models import (
    BackupArtifact,
    BackupContext,
    BackupJob,
    BackupManifest,
    BackupResult,
    BackupSnapshot,
    BackupTarget,
    ResolvedBackupLocation,
    SnapshotCoverage,
    SnapshotKind,
)
from immich_doctor.backup.core.resolver import BackupLocationResolver
from immich_doctor.backup.core.store import BackupSnapshotStore

__all__ = [
    "BackupArtifact",
    "BackupContext",
    "BackupJob",
    "BackupLocationResolver",
    "BackupManifest",
    "BackupResult",
    "BackupSnapshot",
    "BackupSnapshotStore",
    "ResolvedBackupLocation",
    "SnapshotCoverage",
    "SnapshotKind",
    "BackupTarget",
]
