from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from subprocess import CompletedProcess

from immich_doctor.backup.targets.models import BackupTargetType, BackupTargetUpsertPayload
from immich_doctor.core.config import AppSettings
from immich_doctor.services.backup_job_service import BackgroundJobRuntime
from immich_doctor.services.backup_target_settings_service import BackupTargetSettingsService
from immich_doctor.services.backup_target_validation_service import BackupTargetValidationService
from immich_doctor.services.backup_transport_service import RemoteConnectionMaterial


def test_backup_target_validation_service_validates_local_target(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        config_path=tmp_path / "config",
        immich_library_root=tmp_path / "library",
    )
    settings.immich_library_root.mkdir()
    service = BackupTargetSettingsService()
    target = service.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="Local",
            targetType=BackupTargetType.LOCAL,
            path=(tmp_path / "backup").as_posix(),
        ),
    )["item"]

    runtime = BackgroundJobRuntime()
    try:
        result = BackupTargetValidationService(runtime=runtime).validate_target_now(
            settings,
            target=service.get_target(settings, target_id=target["targetId"]),
        )
    finally:
        runtime.shutdown()

    assert result["state"] == "completed"
    assert any(check["name"] == "local_target_path" for check in result["checks"])


def test_backup_target_validation_service_marks_password_auth_unsupported(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, config_path=tmp_path / "config")
    service = BackupTargetSettingsService()
    created = service.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="Remote Password",
            targetType=BackupTargetType.SSH,
            connectionString="backup@backup.example",
            remotePath="/srv/backup",
            authMode="password",
            knownHostMode="strict",
            passwordSecret={"label": "SSH Password", "material": "secret"},
        ),
    )
    target = service.get_target(settings, target_id=created["item"]["targetId"])

    runtime = BackgroundJobRuntime()
    try:
        result = BackupTargetValidationService(runtime=runtime).validate_target_now(
            settings,
            target=target,
        )
    finally:
        runtime.shutdown()

    assert result["state"] == "unsupported"
    assert any("Password auth mode" in check["message"] for check in result["checks"])


def test_backup_target_validation_service_supports_agent_auth_for_remote_probe(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = AppSettings(_env_file=None, config_path=tmp_path / "config")
    service = BackupTargetSettingsService()
    created = service.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="Remote Agent",
            targetType=BackupTargetType.SSH,
            connectionString="backup@backup.example",
            remotePath="/srv/backup",
            authMode="agent",
            knownHostMode="strict",
        ),
    )
    target = service.get_target(settings, target_id=created["item"]["targetId"])

    monkeypatch.setattr(
        "immich_doctor.services.backup_target_validation_service.ExternalToolsAdapter.validate_required_tools",
        lambda self, names: [],
    )

    @contextmanager
    def fake_connection(self, settings, target):  # type: ignore[no-untyped-def]
        del self, settings, target
        yield RemoteConnectionMaterial(
            remote_host_reference="backup@backup.example",
            remote_shell_argv=("ssh",),
            remote_path="/srv/backup",
            warnings=(),
        )

    monkeypatch.setattr(
        "immich_doctor.services.backup_transport_service.BackupTransportService.prepared_remote_connection",
        fake_connection,
    )
    monkeypatch.setattr(
        "immich_doctor.services.backup_transport_service.BackupTransportService.run_remote_command",
        lambda self, material, command: CompletedProcess(
            args=(command,),
            returncode=0,
            stdout="ok\n",
            stderr="",
        ),
    )

    runtime = BackgroundJobRuntime()
    try:
        result = BackupTargetValidationService(runtime=runtime).validate_target_now(
            settings,
            target=target,
        )
    finally:
        runtime.shutdown()

    assert result["state"] == "completed"
    assert any(check["name"] == "remote_write_probe" for check in result["checks"])


def test_backup_target_validation_service_marks_smb_pre_mounted_path_executable(
    tmp_path: Path,
) -> None:
    settings = AppSettings(
        _env_file=None,
        config_path=tmp_path / "config",
        immich_library_root=tmp_path / "library",
    )
    settings.immich_library_root.mkdir(parents=True)
    mounted_path = tmp_path / "mounted-backup"
    mounted_path.mkdir()
    service = BackupTargetSettingsService()
    created = service.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="Mounted SMB",
            targetType=BackupTargetType.SMB,
            host="nas.local",
            share="immich",
            remotePath="/backup",
            mountStrategy="pre_mounted_path",
            mountedPath=mounted_path.as_posix(),
        ),
    )
    target = service.get_target(settings, target_id=created["item"]["targetId"])

    runtime = BackgroundJobRuntime()
    try:
        result = BackupTargetValidationService(runtime=runtime).validate_target_now(
            settings,
            target=target,
        )
    finally:
        runtime.shutdown()

    assert result["state"] == "completed"
    assert any(check["name"] == "smb_execution_mode" for check in result["checks"])


def test_backup_target_validation_service_keeps_smb_system_mount_unsupported(
    tmp_path: Path,
) -> None:
    settings = AppSettings(_env_file=None, config_path=tmp_path / "config")
    service = BackupTargetSettingsService()
    created = service.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="SMB Mount Plan",
            targetType=BackupTargetType.SMB,
            host="nas.local",
            share="immich",
            remotePath="/backup",
            mountStrategy="system_mount",
            username="backup",
            passwordSecret={"label": "SMB password", "material": "secret"},
        ),
    )
    target = service.get_target(settings, target_id=created["item"]["targetId"])

    runtime = BackgroundJobRuntime()
    try:
        result = BackupTargetValidationService(runtime=runtime).validate_target_now(
            settings,
            target=target,
        )
    finally:
        runtime.shutdown()

    assert result["state"] == "unsupported"
    assert any(check["name"] == "smb_execution_mode" for check in result["checks"])
