from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from immich_doctor.backup.core.models import BackupResult, SnapshotKind
from immich_doctor.backup.orchestration.files_service import BackupFilesService
from immich_doctor.core.config import AppSettings
from immich_doctor.services.backup_snapshot_service import summarize_backup_snapshot


@dataclass(slots=True)
class BackupExecutionService:
    backup_files_service: BackupFilesService = field(default_factory=BackupFilesService)

    def run_files_backup(
        self,
        settings: AppSettings,
        *,
        snapshot_kind: SnapshotKind,
    ) -> dict[str, object]:
        result = self.backup_files_service.run(settings, snapshot_kind=snapshot_kind)
        return {
            "generatedAt": datetime.now(UTC).isoformat(),
            "requestedKind": snapshot_kind.value,
            "result": self._serialize_result(result),
            "snapshot": (
                summarize_backup_snapshot(result.snapshot) if result.snapshot is not None else None
            ),
            "limitations": [
                "Current executable snapshot creation is files-only.",
                "Restore orchestration is not implemented yet.",
            ],
        }

    def _serialize_result(self, result: BackupResult) -> dict[str, object]:
        return {
            "domain": result.domain,
            "action": result.action,
            "status": result.status.upper(),
            "summary": result.summary,
            "warnings": list(result.warnings),
            "details": result.details,
        }
