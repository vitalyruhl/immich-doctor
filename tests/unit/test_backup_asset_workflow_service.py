from __future__ import annotations

from pathlib import Path

from immich_doctor.backup.targets.models import BackupTargetType, BackupTargetUpsertPayload
from immich_doctor.backup.targets.paths import backup_workflow_current_library_root
from immich_doctor.core.config import AppSettings
from immich_doctor.services.backup_asset_workflow_service import (
    BackupAssetComparisonStatus,
    BackupAssetWorkflowService,
)
from immich_doctor.services.backup_target_settings_service import BackupTargetSettingsService


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        _env_file=None,
        immich_library_root=tmp_path / "library",
        quarantine_path=tmp_path / "quarantine",
        config_path=tmp_path / "config",
        manifests_path=tmp_path / "manifests",
    )


def _create_local_target(settings: AppSettings, tmp_path: Path) -> str:
    created = BackupTargetSettingsService().create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="Local Backup",
            targetType=BackupTargetType.LOCAL,
            path=(tmp_path / "backup").as_posix(),
        ),
    )
    return str(created["item"]["targetId"])


def test_backup_asset_workflow_overview_reports_statuses_and_folder_hints(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    source_root = settings.immich_library_root
    assert source_root is not None
    source_root.mkdir(parents=True)
    (source_root / "photos").mkdir()
    (source_root / "photos" / "same.jpg").write_bytes(b"same")
    (source_root / "photos" / "missing.jpg").write_bytes(b"missing")
    (source_root / "photos" / "mismatch.jpg").write_bytes(b"source-new")

    target_id = _create_local_target(settings, tmp_path)
    backup_root = backup_workflow_current_library_root(tmp_path / "backup")
    (backup_root / "photos").mkdir(parents=True)
    (backup_root / "photos" / "same.jpg").write_bytes(b"same")
    (backup_root / "photos" / "mismatch.jpg").write_bytes(b"backup-old-mismatch")
    (backup_root / "photos" / "restore.jpg").write_bytes(b"restore-only")

    service = BackupAssetWorkflowService()

    result = service.get_overview(settings, target_id=target_id)

    counts = result["comparison"]["statusCounts"]
    assert counts[BackupAssetComparisonStatus.IDENTICAL.value] == 1
    assert counts[BackupAssetComparisonStatus.MISSING_IN_BACKUP.value] == 1
    assert counts[BackupAssetComparisonStatus.MISMATCH.value] == 1
    assert counts[BackupAssetComparisonStatus.RESTORE_CANDIDATE.value] == 1
    assert result["folders"]["suspiciousCount"] >= 1


def test_backup_asset_workflow_test_copy_runs_real_copy_and_verifies(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    source_root = settings.immich_library_root
    assert source_root is not None
    source_root.mkdir(parents=True)
    (source_root / "asset.jpg").write_bytes(b"payload")
    target_id = _create_local_target(settings, tmp_path)

    result = BackupAssetWorkflowService().run_test_copy(settings, target_id=target_id)

    assert result["supported"] is True
    assert result["result"]["copied"] is True
    assert result["result"]["verified"] is True
    assert result["result"]["verificationMethod"] == "sha256"


def test_backup_asset_workflow_restore_uses_quarantine_before_overwrite(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    source_root = settings.immich_library_root
    assert source_root is not None
    source_root.mkdir(parents=True)
    (source_root / "photos").mkdir()
    (source_root / "photos" / "asset.jpg").write_bytes(b"broken-source")

    target_id = _create_local_target(settings, tmp_path)
    backup_root = backup_workflow_current_library_root(tmp_path / "backup")
    (backup_root / "photos").mkdir(parents=True)
    (backup_root / "photos" / "asset.jpg").write_bytes(b"backup-good")

    service = BackupAssetWorkflowService()
    dry_run = service.restore_items(
        settings,
        target_id=target_id,
        asset_ids=["photos/asset.jpg"],
        apply=False,
    )
    result = service.restore_items(
        settings,
        target_id=target_id,
        asset_ids=["photos/asset.jpg"],
        apply=True,
    )

    assert dry_run["results"][0]["actionOutcome"] == "planned"
    assert result["results"][0]["resultStatus"] == BackupAssetComparisonStatus.RESTORED.value
    assert result["results"][0]["quarantinePath"] is not None
    assert (source_root / "photos" / "asset.jpg").read_bytes() == b"backup-good"
    assert Path(str(result["results"][0]["quarantinePath"])).read_bytes() == b"broken-source"
