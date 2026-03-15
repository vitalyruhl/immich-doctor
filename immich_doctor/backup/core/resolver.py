"""Contracts for future backup location resolution."""

from __future__ import annotations

from typing import Protocol

from immich_doctor.backup.core.models import BackupContext, ResolvedBackupLocation


class BackupLocationResolver(Protocol):
    """Resolves a backup destination contract without performing filesystem work."""

    def resolve(self, context: BackupContext) -> ResolvedBackupLocation:
        """Return the resolved backup location for the provided backup context."""
