from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from immich_doctor.backup import BackupContext
from immich_doctor.backup.core import (
    BackupArtifact,
    BackupJob,
    BackupManifest,
    BackupResult,
    BackupTarget,
    ResolvedBackupLocation,
)
from immich_doctor.backup.core.placeholder import __doc__ as core_placeholder_doc
from immich_doctor.backup.db.placeholder import __doc__ as db_placeholder_doc
from immich_doctor.backup.files.placeholder import __doc__ as files_placeholder_doc
from immich_doctor.backup.metadata.placeholder import __doc__ as metadata_placeholder_doc
from immich_doctor.backup.orchestration import BackupOrchestrator
from immich_doctor.backup.remote.placeholder import __doc__ as remote_placeholder_doc
from immich_doctor.backup.scheduler.placeholder import __doc__ as scheduler_placeholder_doc


def test_backup_foundation_models_can_be_instantiated() -> None:
    target = BackupTarget(kind="local", reference="/backups/immich", display_name="Local backup")
    resolved = ResolvedBackupLocation(target=target, root_path=Path("/backups/immich"))
    context = BackupContext(
        job_name="nightly-backup",
        requested_components=("database", "files"),
        target=target,
        started_at=datetime(2026, 3, 14, 12, 0, tzinfo=UTC),
    )
    artifact = BackupArtifact(
        name="database.sql",
        kind="database_dump",
        target=target,
        relative_path=Path("database.sql"),
    )
    manifest = BackupManifest(
        timestamp=datetime(2026, 3, 14, 12, 5, tzinfo=UTC),
        included_components=("database", "files"),
        artifacts=(artifact,),
    )
    job = BackupJob(
        name="database-dump",
        component="database",
        description="Placeholder database backup job.",
        target=target,
    )
    result = BackupResult(
        domain="backup",
        action="run",
        status="pending",
        summary="Not implemented.",
        context=context,
    )

    assert context.target is target
    assert resolved.root_path == Path("/backups/immich")
    assert artifact.target is target
    assert manifest.artifacts == (artifact,)
    assert job.component == "database"
    assert result.status == "pending"


def test_backup_foundation_packages_import_without_runtime_side_effects() -> None:
    assert "backup-core" in (core_placeholder_doc or "")
    assert "database backup" in (db_placeholder_doc or "")
    assert "file backup" in (files_placeholder_doc or "")
    assert "metadata snapshot" in (metadata_placeholder_doc or "")
    assert "scheduler adapters" in (scheduler_placeholder_doc or "")
    assert "remote transport" in (remote_placeholder_doc or "")
    assert BackupOrchestrator.__name__ == "BackupOrchestrator"
