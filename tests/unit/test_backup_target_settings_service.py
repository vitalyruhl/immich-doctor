from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from immich_doctor.backup.targets.models import BackupTargetType, BackupTargetUpsertPayload
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


def test_backup_target_service_parses_connection_string_for_ssh_agent_targets(
    tmp_path: Path,
) -> None:
    settings = AppSettings(_env_file=None, config_path=tmp_path / "config")
    service = BackupTargetSettingsService()

    result = service.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="Remote SSH",
            targetType=BackupTargetType.SSH,
            connectionString="root@192.168.2.2",
            remotePath="/srv/backup/immich",
            authMode="agent",
            knownHostMode="strict",
        ),
    )

    transport = result["item"]["transport"]
    assert transport["username"] == "root"
    assert transport["host"] == "192.168.2.2"
    assert transport["authMode"] == "agent"
    assert transport["port"] == 22
    assert transport["privateKeySecretRef"] is None


def test_backup_target_service_parses_connection_string_port_for_ssh_targets(
    tmp_path: Path,
) -> None:
    settings = AppSettings(_env_file=None, config_path=tmp_path / "config")
    service = BackupTargetSettingsService()

    result = service.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="Remote SSH",
            targetType=BackupTargetType.SSH,
            connectionString="root@192.168.2.2:2222",
            remotePath="/srv/backup/immich",
            authMode="agent",
            knownHostMode="strict",
        ),
    )

    transport = result["item"]["transport"]
    assert transport["username"] == "root"
    assert transport["host"] == "192.168.2.2"
    assert transport["port"] == 2222


def test_backup_target_service_returns_secret_reference_without_secret_echo(
    tmp_path: Path,
) -> None:
    settings = AppSettings(_env_file=None, config_path=tmp_path / "config")
    service = BackupTargetSettingsService()

    result = service.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="Remote SSH",
            targetType=BackupTargetType.SSH,
            connectionString="backup@backup.example",
            remotePath="/srv/backup/immich",
            authMode="private_key",
            knownHostMode="strict",
            privateKeySecret={"label": "Main SSH key", "material": "PRIVATE KEY DATA"},
        ),
    )

    item = result["item"]
    secret_ref = item["transport"]["privateKeySecretRef"]
    assert secret_ref is not None
    assert "maskedValue" not in secret_ref
    assert "PRIVATE KEY DATA" not in str(item)


def test_backup_target_service_accepts_smb_pre_mounted_mode_without_credentials(
    tmp_path: Path,
) -> None:
    settings = AppSettings(_env_file=None, config_path=tmp_path / "config")
    service = BackupTargetSettingsService()

    result = service.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="SMB Pre-Mounted",
            targetType=BackupTargetType.SMB,
            host="nas.local",
            share="immich",
            remotePath="/backups",
            mountStrategy="pre_mounted_path",
            mountedPath=(tmp_path / "mnt" / "immich-backup").as_posix(),
        ),
    )

    warnings = result["item"]["warnings"]
    assert result["item"]["restoreReadiness"] == "partial"
    assert any("already authenticated mount" in warning for warning in warnings)


def test_backup_target_service_rejects_smb_system_mount_without_credentials(
    tmp_path: Path,
) -> None:
    settings = AppSettings(_env_file=None, config_path=tmp_path / "config")
    service = BackupTargetSettingsService()

    with pytest.raises(ValueError, match="password secret reference"):
        service.create_target(
            settings,
            BackupTargetUpsertPayload(
                targetName="SMB Share",
                targetType=BackupTargetType.SMB,
                host="nas.local",
                share="immich",
                remotePath="/backups",
                mountStrategy="system_mount",
                username="backup",
            ),
        )


def test_backup_target_service_accepts_smb_system_mount_with_reused_secret_reference(
    tmp_path: Path,
) -> None:
    settings = AppSettings(_env_file=None, config_path=tmp_path / "config")
    service = BackupTargetSettingsService()

    ssh_target = service.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="Remote SSH",
            targetType=BackupTargetType.SSH,
            connectionString="backup@backup.example",
            remotePath="/srv/backup/immich",
            authMode="password",
            knownHostMode="strict",
            passwordSecret={"label": "SSH password", "material": "secret"},
        ),
    )
    secret_id = ssh_target["item"]["transport"]["passwordSecretRef"]["secretId"]

    smb_target = service.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="SMB Share",
            targetType=BackupTargetType.SMB,
            host="nas.local",
            share="immich",
            remotePath="/backups",
            mountStrategy="system_mount",
            username="backup",
            passwordSecret={"secretId": secret_id},
        ),
    )

    assert smb_target["item"]["transport"]["passwordSecretRef"]["secretId"] == secret_id


def test_backup_target_service_clears_irrelevant_secret_refs_on_auth_mode_change(
    tmp_path: Path,
) -> None:
    settings = AppSettings(_env_file=None, config_path=tmp_path / "config")
    service = BackupTargetSettingsService()

    created = service.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="Remote SSH",
            targetType=BackupTargetType.SSH,
            connectionString="backup@backup.example",
            remotePath="/srv/backup/immich",
            authMode="private_key",
            knownHostMode="strict",
            privateKeySecret={"label": "Main SSH key", "material": "PRIVATE KEY DATA"},
        ),
    )

    updated = service.update_target(
        settings,
        target_id=created["item"]["targetId"],
        payload=BackupTargetUpsertPayload(
            targetName="Remote SSH",
            targetType=BackupTargetType.SSH,
            connectionString="backup@backup.example",
            remotePath="/srv/backup/immich",
            authMode="agent",
            knownHostMode="strict",
        ),
    )

    transport = updated["item"]["transport"]
    assert transport["privateKeySecretRef"] is None
    assert transport["passwordSecretRef"] is None


def test_backup_target_payload_rejects_empty_smb_username_for_system_mount() -> None:
    with pytest.raises(ValidationError, match="SMB system-mount targets require a username"):
        BackupTargetUpsertPayload(
            targetName="SMB Share",
            targetType=BackupTargetType.SMB,
            host="nas.local",
            share="immich",
            remotePath="/backups",
            mountStrategy="system_mount",
            username="",
        )


def test_backup_target_payload_rejects_relative_local_paths() -> None:
    with pytest.raises(ValidationError):
        BackupTargetUpsertPayload(
            targetName="Relative",
            targetType=BackupTargetType.LOCAL,
            path="relative/path",
        )
