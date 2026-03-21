from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from immich_doctor.backup.core.models import (
    BackupContext,
    BackupResult,
    BackupSnapshot,
    BackupTarget,
    SnapshotCoverage,
    SnapshotKind,
)
from immich_doctor.core.config import AppSettings
from immich_doctor.services.backup_execution_service import BackupExecutionService


@dataclass(slots=True)
class _FakeBackupFilesService:
    def run(
        self, settings: AppSettings, *, snapshot_kind: SnapshotKind = SnapshotKind.MANUAL
    ) -> BackupResult:
        del settings
        snapshot = BackupSnapshot(
            snapshot_id="snapshot-1",
            kind=snapshot_kind,
            created_at=datetime(2026, 3, 21, 12, 0, tzinfo=UTC),
            source_fingerprint="backup-files:test",
            coverage=SnapshotCoverage.FILES_ONLY,
            file_artifacts=(),
            db_artifact=None,
            manifest_path=Path("backup/snapshots/snapshot-1.json"),
            verified=False,
        )
        return BackupResult(
            domain="backup.files",
            action="run",
            status="success",
            summary="Legacy backup files execution completed.",
            context=BackupContext(
                job_name="backup.files",
                requested_components=("files",),
                target=BackupTarget(
                    kind="local",
                    reference="/backup",
                    display_name="Legacy Backup",
                ),
                started_at=datetime(2026, 3, 21, 12, 0, tzinfo=UTC),
            ),
            snapshot=snapshot,
        )


def test_backup_execution_service_marks_backup_files_path_as_legacy(tmp_path: Path) -> None:
    service = BackupExecutionService(backup_files_service=_FakeBackupFilesService())
    settings = AppSettings(_env_file=None, config_path=tmp_path / "config")

    result = service.run_files_backup(settings, snapshot_kind=SnapshotKind.MANUAL)

    assert result["limitations"][0].startswith("This backup files path is legacy.")
