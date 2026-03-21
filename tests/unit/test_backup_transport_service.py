from __future__ import annotations

from pathlib import Path

from immich_doctor.backup.targets.models import (
    BackupTargetAuthMode,
    BackupTargetConfig,
    BackupTargetKnownHostMode,
    BackupTargetTransportSettings,
    BackupTargetType,
    BackupTargetUpsertPayload,
)
from immich_doctor.backup.targets.paths import backup_secret_path
from immich_doctor.backup.targets.secrets import StoredSecretRecord
from immich_doctor.core.config import AppSettings
from immich_doctor.services.backup_target_settings_service import BackupTargetSettingsService
from immich_doctor.services.backup_transport_service import BackupTransportService

PRIVATE_KEY_FIXTURE_LF = """-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACCW8F1L1O5U6jQvI6X6d3gR3M4Nq7e9Q9mXg6vNwX2bTwAAAJiGx4MPhseDDw
AAAAtzc2gtZWQyNTUxOQAAACCW8F1L1O5U6jQvI6X6d3gR3M4Nq7e9Q9mXg6vNwX2bTwAAAED
7nD1U0b8Z9hF9m0R2rP9vRzE0S0Z7mQvL7M0wP4jVYJbwXUvU7lTqNC8jpfp3eBHczg2rt71D
2ZeDq83BfZtPAAAAE2ltbWljaC1kb2N0b3ItdGVzdAECAwQF
-----END OPENSSH PRIVATE KEY-----
"""

PRIVATE_KEY_FIXTURE_CRLF = PRIVATE_KEY_FIXTURE_LF.replace("\n", "\r\n").lstrip().rstrip("\r\n")


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


def test_backup_transport_service_normalizes_legacy_private_key_secret_before_writing_temp_key(
    tmp_path: Path,
) -> None:
    settings = AppSettings(_env_file=None, config_path=tmp_path / "config")
    service = BackupTargetSettingsService()
    secret_id = "legacy-secret"
    record = StoredSecretRecord(
        secretId=secret_id,
        kind="private_key",
        label="Legacy SSH key",
        createdAt="2026-03-21T12:00:00+00:00",
        material=PRIVATE_KEY_FIXTURE_CRLF,
    )
    secret_path = backup_secret_path(settings, secret_id)
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.write_text(record.model_dump_json(by_alias=True, indent=2), encoding="utf-8")

    created = service.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="Remote Key",
            targetType=BackupTargetType.SSH,
            connectionString="backup@backup.example",
            remotePath="/srv/backup",
            authMode=BackupTargetAuthMode.PRIVATE_KEY,
            knownHostMode=BackupTargetKnownHostMode.DISABLED,
            privateKeySecret={"secretId": secret_id},
        ),
    )
    target = service.get_target(settings, target_id=created["item"]["targetId"])
    transport = BackupTransportService(service.secrets)

    with transport.prepared_remote_connection(settings, target) as material:
        key_index = material.remote_shell_argv.index("-i")
        key_path = Path(material.remote_shell_argv[key_index + 1])
        assert key_path.read_bytes() == PRIVATE_KEY_FIXTURE_LF.encode("utf-8")
