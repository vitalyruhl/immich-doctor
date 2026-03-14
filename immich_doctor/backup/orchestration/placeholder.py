"""Reserved orchestration contracts for future backup workflow execution."""

from __future__ import annotations

from dataclasses import dataclass

from immich_doctor.backup.core.models import BackupContext, BackupJob, BackupResult


@dataclass(slots=True)
class BackupOrchestrator:
    """Placeholder orchestrator for future sequential jobs, locking, and reporting."""

    def plan(self, context: BackupContext) -> tuple[BackupJob, ...]:
        """Return the future execution plan for the provided backup context."""
        raise NotImplementedError("Backup orchestration is not implemented in this phase.")

    def run(self, context: BackupContext) -> BackupResult:
        """Execute the future backup workflow for the provided backup context."""
        raise NotImplementedError("Backup orchestration is not implemented in this phase.")
