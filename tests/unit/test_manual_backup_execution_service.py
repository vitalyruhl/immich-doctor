from __future__ import annotations

import time
from pathlib import Path

from immich_doctor.backup.files.transfer import RsyncTransferMetrics, RsyncTransferResult
from immich_doctor.backup.targets.models import BackupTargetType, BackupTargetUpsertPayload
from immich_doctor.core.config import AppSettings
from immich_doctor.services.backup_job_service import BackgroundJobRuntime
from immich_doctor.services.backup_target_settings_service import BackupTargetSettingsService
from immich_doctor.services.manual_backup_execution_service import (
    BACKUP_EXECUTION_JOB_TYPE,
    ManualBackupExecutionService,
)


def test_manual_backup_execution_service_completes_local_backup(tmp_path: Path) -> None:
    source_root = tmp_path / "library"
    source_root.mkdir()
    (source_root / "asset.jpg").write_bytes(b"payload")

    settings = AppSettings(
        _env_file=None,
        config_path=tmp_path / "config",
        manifests_path=tmp_path / "manifests",
        immich_library_root=source_root,
    )
    target_settings = BackupTargetSettingsService()
    created = target_settings.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="Local Backup",
            targetType=BackupTargetType.LOCAL,
            path=(tmp_path / "backup").as_posix(),
        ),
    )
    target_id = created["item"]["targetId"]

    class FakeTransferExecutor:
        def execute(
            self,
            *,
            source_path: Path,
            destination_reference: str,
            create_local_parent: Path | None = None,
            remote_shell_argv=None,
            cancel_requested=None,
        ) -> RsyncTransferResult:
            del source_path, remote_shell_argv, cancel_requested
            destination_path = Path(destination_reference)
            if create_local_parent is not None:
                create_local_parent.mkdir(parents=True, exist_ok=True)
            destination_path.mkdir(parents=True, exist_ok=True)
            (destination_path / "asset.jpg").write_bytes(b"payload")
            return RsyncTransferResult(
                command=("rsync",),
                stdout="",
                stderr="",
                duration_seconds=0.1,
                metrics=RsyncTransferMetrics(
                    total_file_size_bytes=7,
                    sent_bytes=7,
                    received_bytes=0,
                    file_count=1,
                    regular_files_transferred=1,
                ),
            )

    runtime = BackgroundJobRuntime()
    try:
        service = ManualBackupExecutionService(
            runtime=runtime,
            target_settings=target_settings,
            transfer_executor=FakeTransferExecutor(),
        )
        started = service.start_execution(settings, target_id=target_id)
        assert started["state"] == "pending"

        deadline = time.monotonic() + 5
        while runtime.active_job(job_type=BACKUP_EXECUTION_JOB_TYPE) is not None:
            assert time.monotonic() < deadline
            time.sleep(0.05)

        current = service.get_current(settings)
        updated_target = target_settings.get_target(settings, target_id=target_id)
    finally:
        runtime.shutdown()

    assert current["state"] == "completed"
    assert current["snapshot"] is not None
    assert updated_target.last_successful_backup is not None
