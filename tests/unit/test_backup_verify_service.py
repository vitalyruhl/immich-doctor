from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from immich_doctor.backup.core.models import (
    BackupArtifact,
    BackupSnapshot,
    BackupTarget,
    SnapshotCoverage,
    SnapshotKind,
)
from immich_doctor.backup.core.store import BackupSnapshotStore
from immich_doctor.backup.verify.service import BackupVerifyService
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckStatus


def test_backup_verify_reports_persisted_snapshot_manifests(tmp_path: Path) -> None:
    backup_target = tmp_path / "backup"
    backup_target.mkdir()
    settings = AppSettings(
        _env_file=None,
        backup_target_path=backup_target,
        manifests_path=tmp_path / "manifests",
        quarantine_path=tmp_path / "quarantine",
    )
    target = BackupTarget(kind="local", reference=str(backup_target), display_name="backup")
    artifact = BackupArtifact(
        name="immich-library",
        kind="file_archive",
        target=target,
        relative_path=Path("files/immich-library"),
    )
    snapshot = BackupSnapshot(
        snapshot_id="snapshot-1",
        kind=SnapshotKind.MANUAL,
        created_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
        source_fingerprint="fingerprint",
        coverage=SnapshotCoverage.FILES_ONLY,
        file_artifacts=(artifact,),
        db_artifact=None,
        manifest_path=Path("pending"),
        verified=False,
    )
    BackupSnapshotStore().persist_snapshot(settings, snapshot)

    report = BackupVerifyService().run(settings)

    snapshot_checks = [check for check in report.checks if check.name.startswith("backup_snapshot")]
    assert any(check.name == "backup_snapshot_manifests" for check in report.checks)
    assert any(check.status == CheckStatus.PASS for check in snapshot_checks)


def test_backup_verify_fails_on_inconsistent_snapshot_coverage(tmp_path: Path) -> None:
    backup_target = tmp_path / "backup"
    backup_target.mkdir()
    settings = AppSettings(
        _env_file=None,
        backup_target_path=backup_target,
        manifests_path=tmp_path / "manifests",
        quarantine_path=tmp_path / "quarantine",
    )
    snapshot = BackupSnapshot(
        snapshot_id="snapshot-bad",
        kind=SnapshotKind.PERIODIC,
        created_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
        source_fingerprint="fingerprint",
        coverage=SnapshotCoverage.PAIRED,
        file_artifacts=(),
        db_artifact=None,
        manifest_path=Path("pending"),
        verified=False,
    )
    BackupSnapshotStore().persist_snapshot(settings, snapshot)

    report = BackupVerifyService().run(settings)

    failing_checks = [check for check in report.checks if check.status == CheckStatus.FAIL]
    assert any(check.name == "backup_snapshot:snapshot-bad" for check in failing_checks)


def test_backup_verify_fails_on_unparseable_snapshot_manifest(tmp_path: Path) -> None:
    backup_target = tmp_path / "backup"
    backup_target.mkdir()
    manifests_path = tmp_path / "manifests"
    snapshot_root = manifests_path / "backup" / "snapshots"
    snapshot_root.mkdir(parents=True)
    (snapshot_root / "broken.json").write_text("{not-json", encoding="utf-8")
    settings = AppSettings(
        _env_file=None,
        backup_target_path=backup_target,
        manifests_path=manifests_path,
        quarantine_path=tmp_path / "quarantine",
    )

    report = BackupVerifyService().run(settings)

    failing_checks = [check for check in report.checks if check.status == CheckStatus.FAIL]
    assert any(check.name == "backup_snapshot_manifest:broken" for check in failing_checks)
