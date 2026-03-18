from __future__ import annotations

from pathlib import Path

from immich_doctor.backup.targets.models import BackupTargetType, BackupTargetUpsertPayload
from immich_doctor.core.config import AppSettings
from immich_doctor.services.backup_job_service import BackgroundJobRuntime
from immich_doctor.services.backup_target_settings_service import BackupTargetSettingsService
from immich_doctor.services.backup_target_validation_service import BackupTargetValidationService


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
            host="backup.example",
            remotePath="/srv/backup",
            username="backup",
            authMode="password",
            hostKeyVerification="known_hosts",
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
    assert any("private_key auth mode" in check["message"] for check in result["checks"])
