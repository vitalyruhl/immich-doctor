from __future__ import annotations

from pathlib import Path

from immich_doctor.backup.targets.models import (
    BackupTargetConfig,
    BackupTargetKnownHostMode,
    BackupTargetTransportSettings,
    BackupTargetType,
)
from immich_doctor.core.config import AppSettings
from immich_doctor.services.backup_target_settings_service import BackupTargetSettingsService
from immich_doctor.services.backup_transport_service import BackupTransportService


def test_backup_transport_service_supports_agent_auth_without_private_key(
    tmp_path: Path,
) -> None:
    settings = AppSettings(_env_file=None, config_path=tmp_path / "config")
    target = BackupTargetConfig(
        targetId="target-1",
        targetName="Remote Agent",
        targetType=BackupTargetType.SSH,
        transport=BackupTargetTransportSettings(
            host="backup.example",
            port=22,
            remotePath="/srv/backup",
            username="backup",
            authMode="agent",
            knownHostMode="strict",
        ),
    )
    transport = BackupTransportService(BackupTargetSettingsService().secrets)

    with transport.prepared_remote_connection(settings, target) as material:
        assert material.remote_host_reference == "backup@backup.example"
        assert "-i" not in material.remote_shell_argv


def test_backup_transport_service_maps_strict_and_accept_new_known_host_modes(
    tmp_path: Path,
) -> None:
    settings = AppSettings(_env_file=None, config_path=tmp_path / "config")
    known_hosts_path = (tmp_path / "known_hosts").as_posix()
    strict_target = BackupTargetConfig(
        targetId="target-1",
        targetName="Remote Agent",
        targetType=BackupTargetType.SSH,
        transport=BackupTargetTransportSettings(
            host="backup.example",
            port=22,
            remotePath="/srv/backup",
            username="backup",
            authMode="agent",
            knownHostMode=BackupTargetKnownHostMode.STRICT,
            knownHostReference=known_hosts_path,
        ),
    )
    accept_new_target = strict_target.model_copy(
        update={
            "transport": strict_target.transport.model_copy(
                update={"known_host_mode": BackupTargetKnownHostMode.ACCEPT_NEW}
            )
        }
    )
    transport = BackupTransportService(BackupTargetSettingsService().secrets)

    with transport.prepared_remote_connection(settings, strict_target) as strict_material:
        strict_command = " ".join(strict_material.remote_shell_argv)
    with transport.prepared_remote_connection(settings, accept_new_target) as accept_new_material:
        accept_new_command = " ".join(accept_new_material.remote_shell_argv)

    assert "StrictHostKeyChecking=yes" in strict_command
    assert f"UserKnownHostsFile={Path(known_hosts_path).as_posix()}" in strict_command
    assert "StrictHostKeyChecking=accept-new" in accept_new_command


def test_backup_transport_service_uses_only_strict_host_key_disable_flag_for_disabled_mode(
    tmp_path: Path,
) -> None:
    settings = AppSettings(_env_file=None, config_path=tmp_path / "config")
    target = BackupTargetConfig(
        targetId="target-1",
        targetName="Remote Agent",
        targetType=BackupTargetType.SSH,
        transport=BackupTargetTransportSettings(
            host="backup.example",
            port=22,
            remotePath="/srv/backup",
            username="backup",
            authMode="agent",
            knownHostMode=BackupTargetKnownHostMode.DISABLED,
        ),
    )
    transport = BackupTransportService(BackupTargetSettingsService().secrets)

    with transport.prepared_remote_connection(settings, target) as material:
        command = " ".join(material.remote_shell_argv)

    assert "StrictHostKeyChecking=no" in command
    assert "UserKnownHostsFile" not in command
