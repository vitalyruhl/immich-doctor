from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from immich_doctor.backup.targets.models import (
    BackupTargetType,
    BackupTargetUpsertPayload,
)
from immich_doctor.core.config import AppSettings
from immich_doctor.services.backup_target_settings_service import BackupTargetSettingsService


def test_backup_target_service_persists_local_target_without_secret_leakage(
    tmp_path: Path,
) -> None:
    settings = AppSettings(_env_file=None, config_path=tmp_path / "config")
    service = BackupTargetSettingsService()

    result = service.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="Local Backup",
            targetType=BackupTargetType.LOCAL,
            path=(tmp_path / "backups").as_posix(),
        ),
    )

    assert result["applied"] is True
    item = result["item"]
    assert item["targetType"] == "local"
    assert item["transport"]["path"] == (tmp_path / "backups").as_posix()
    assert item["transport"]["passwordSecretRef"] is None


def test_backup_target_service_masks_stored_secrets_for_ssh_targets(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, config_path=tmp_path / "config")
    service = BackupTargetSettingsService()

    result = service.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="Remote SSH",
            targetType=BackupTargetType.SSH,
            host="backup.example",
            port=22,
            remotePath="/srv/backup/immich",
            username="backup",
            authMode="private_key",
            hostKeyVerification="known_hosts",
            privateKeySecret={"label": "Main SSH key", "material": "PRIVATE KEY DATA"},
        ),
    )

    item = result["item"]
    secret_ref = item["transport"]["privateKeySecretRef"]
    assert secret_ref is not None
    assert secret_ref["maskedValue"] == "Configured"
    assert "PRIVATE KEY DATA" not in str(item)


def test_backup_target_service_marks_smb_as_configuration_only(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, config_path=tmp_path / "config")
    service = BackupTargetSettingsService()

    result = service.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="SMB Share",
            targetType=BackupTargetType.SMB,
            host="nas.local",
            share="immich",
            remotePath="/backups",
            mountStrategy="system_mount",
        ),
    )

    warnings = result["item"]["warnings"]
    assert any("productive execution is disabled" in warning for warning in warnings)


def test_backup_target_payload_rejects_relative_local_paths() -> None:
    with pytest.raises(ValidationError):
        BackupTargetUpsertPayload(
            targetName="Relative",
            targetType=BackupTargetType.LOCAL,
            path="relative/path",
        )
