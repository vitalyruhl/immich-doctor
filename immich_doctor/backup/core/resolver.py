"""Contracts for future backup location resolution."""

from __future__ import annotations

from typing import Protocol

from immich_doctor.backup.core.models import BackupContext, BackupTarget


class BackupLocationResolver(Protocol):
    """Resolves a backup destination contract without performing filesystem work."""

    def resolve(self, context: BackupContext) -> BackupTarget:
        """Return the resolved backup target for the provided backup context."""

