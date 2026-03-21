from __future__ import annotations

import time
from contextlib import contextmanager
from pathlib import Path
from subprocess import CompletedProcess

from immich_doctor.backup.files.transfer import RsyncTransferMetrics, RsyncTransferResult
from immich_doctor.backup.targets.models import BackupTargetType, BackupTargetUpsertPayload
from immich_doctor.core.config import AppSettings
from immich_doctor.services.backup_job_service import BackgroundJobRuntime
from immich_doctor.services.backup_target_settings_service import BackupTargetSettingsService
from immich_doctor.services.backup_transport_service import RemoteConnectionMaterial
from immich_doctor.services.manual_backup_execution_service import (
    BACKUP_EXECUTION_JOB_TYPE,
    ManualBackupExecutionService,
)


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        _env_file=None,
        config_path=tmp_path / "config",
        manifests_path=tmp_path / "manifests",
        quarantine_path=tmp_path / "quarantine",
        immich_library_root=tmp_path / "library",
    )


def _wait_for_execution(runtime: BackgroundJobRuntime) -> None:
    deadline = time.monotonic() + 5
    while runtime.active_job(job_type=BACKUP_EXECUTION_JOB_TYPE) is not None:
        assert time.monotonic() < deadline
        time.sleep(0.05)


def test_manual_backup_execution_service_prepares_smb_pre_mounted_context(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    source_root = settings.immich_library_root
    assert source_root is not None
    source_root.mkdir(parents=True)

    target_settings = BackupTargetSettingsService()
    created = target_settings.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="Mounted SMB",
            targetType=BackupTargetType.SMB,
            host="nas.local",
            share="immich",
            remotePath="/backup",
            mountStrategy="pre_mounted_path",
            mountedPath=(tmp_path / "mounted-backup").as_posix(),
        ),
    )
    target = target_settings.get_target(settings, target_id=created["item"]["targetId"])

    runtime = BackgroundJobRuntime()
    try:
        context = ManualBackupExecutionService(
            runtime=runtime,
            target_settings=target_settings,
        ).prepare_execution_context(target)
    finally:
        runtime.shutdown()

    assert context.execution_mode.value == "asset_aware_sync"
    assert context.destination_semantics.value == "mirror_sync"
    assert context.is_path_like_usable_destination is True
    assert context.effective_destination_path == (tmp_path / "mounted-backup").as_posix()


def test_manual_backup_execution_service_completes_local_backup_without_rsync(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    source_root = settings.immich_library_root
    assert source_root is not None
    source_root.mkdir(parents=True)
    (source_root / "asset.jpg").write_bytes(b"payload")

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

    class FailIfCalledTransferExecutor:
        def execute(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            raise AssertionError("Local asset-aware execution must not invoke rsync transfer.")

    runtime = BackgroundJobRuntime()
    try:
        service = ManualBackupExecutionService(
            runtime=runtime,
            target_settings=target_settings,
            transfer_executor=FailIfCalledTransferExecutor(),
        )
        started = service.start_execution(settings, target_id=target_id)
        assert started["state"] == "pending"

        _wait_for_execution(runtime)

        current = service.get_current(settings)
        updated_target = target_settings.get_target(settings, target_id=target_id)
    finally:
        runtime.shutdown()

    assert current["state"] == "completed"
    assert current["snapshot"] is None
    assert current["report"]["verificationLevel"] == "copied_files_sha256"
    assert current["report"]["details"]["executionContext"]["executionMode"] == "asset_aware_sync"
    assert updated_target.last_successful_backup is not None


def test_manual_backup_execution_service_runs_smb_pre_mounted_path_like_backup(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    source_root = settings.immich_library_root
    assert source_root is not None
    source_root.mkdir(parents=True)
    (source_root / "album").mkdir()
    (source_root / "album" / "asset.jpg").write_bytes(b"payload")

    target_settings = BackupTargetSettingsService()
    created = target_settings.create_target(
        settings,
        BackupTargetUpsertPayload(
            targetName="Mounted SMB",
            targetType=BackupTargetType.SMB,
            host="nas.local",
            share="immich",
            remotePath="/backup",
            mountStrategy="pre_mounted_path",
            mountedPath=(tmp_path / "mounted-backup").as_posix(),
        ),
    )
    target_id = created["item"]["targetId"]

    class FailIfCalledTransferExecutor:
        def execute(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            raise AssertionError(
                "SMB pre-mounted path execution must stay on the path-like asset workflow."
            )

    runtime = BackgroundJobRuntime()
    try:
        service = ManualBackupExecutionService(
            runtime=runtime,
            target_settings=target_settings,
            transfer_executor=FailIfCalledTransferExecutor(),
        )
        service.start_execution(settings, target_id=target_id)
        _wait_for_execution(runtime)
        current = service.get_current(settings)
        updated_target = target_settings.get_target(settings, target_id=target_id)
    finally:
        runtime.shutdown()

    assert current["state"] == "completed"
    assert current["report"]["verificationLevel"] == "copied_files_sha256"
    assert current["report"]["details"]["executionContext"]["targetType"] == "smb"
    assert current["report"]["details"]["executionContext"]["mirrorSyncDestination"] is True
    assert updated_target.restore_readiness.value == "partial"
    assert (
        Path(tmp_path / "mounted-backup" / "_immich-doctor" / "current" / "immich-library" / "album" / "asset.jpg").read_bytes()
        == b"payload"
    )


def test_manual_backup_execution_service_uses_remote_transfer_for_ssh_target(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    source_root = settings.immich_library_root
    assert source_root is not None
    source_root.mkdir(parents=True)
    (source_root / "asset.jpg").write_bytes(b"payload")

    target_settings = BackupTargetSettingsService()
    created = target_settings.create_target(
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
    target_id = created["item"]["targetId"]

    class FakeValidator:
        def validate_target_now(self, settings: AppSettings, *, target):  # type: ignore[no-untyped-def]
            del settings
            return {
                "generatedAt": "2026-03-21T10:00:00+00:00",
                "jobId": None,
                "targetId": target.target_id,
                "targetType": target.target_type.value,
                "state": "completed",
                "summary": "Target validation completed for currently implemented checks.",
                "checks": [],
                "warnings": [],
            }

    class RecordingTransferExecutor:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def execute(
            self,
            *,
            source_path: Path,
            destination_reference: str,
            create_local_parent: Path | None = None,
            remote_shell_argv=None,
            cancel_requested=None,
        ) -> RsyncTransferResult:
            self.calls.append(
                {
                    "source_path": source_path,
                    "destination_reference": destination_reference,
                    "create_local_parent": create_local_parent,
                    "remote_shell_argv": remote_shell_argv,
                    "cancel_requested": cancel_requested,
                }
            )
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

    @contextmanager
    def fake_connection(self, settings, target):  # type: ignore[no-untyped-def]
        del self, settings, target
        yield RemoteConnectionMaterial(
            remote_host_reference="backup@backup.example",
            remote_shell_argv=("ssh", "-p", "22"),
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

    transfer_executor = RecordingTransferExecutor()
    runtime = BackgroundJobRuntime()
    try:
        service = ManualBackupExecutionService(
            runtime=runtime,
            target_settings=target_settings,
            validator=FakeValidator(),
            transfer_executor=transfer_executor,
        )
        service.start_execution(settings, target_id=target_id)
        _wait_for_execution(runtime)
        current = service.get_current(settings)
    finally:
        runtime.shutdown()

    assert current["state"] == "completed"
    assert current["snapshot"] is not None
    assert current["report"]["verificationLevel"] == "destination_exists"
    assert current["report"]["details"]["executionContext"]["executionMode"] == "versioned_transfer"
    assert str(transfer_executor.calls[0]["destination_reference"]).startswith(
        "backup@backup.example:/srv/backup/"
    )
    assert transfer_executor.calls[0]["create_local_parent"] is None
    assert transfer_executor.calls[0]["remote_shell_argv"] == ("ssh", "-p", "22")


def test_manual_backup_execution_service_blocks_remote_transfer_when_execution_support_is_missing(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    source_root = settings.immich_library_root
    assert source_root is not None
    source_root.mkdir(parents=True)
    (source_root / "asset.jpg").write_bytes(b"payload")

    target_settings = BackupTargetSettingsService()
    created = target_settings.create_target(
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
    target_id = created["item"]["targetId"]

    class FakeValidator:
        def validate_target_now(self, settings: AppSettings, *, target):  # type: ignore[no-untyped-def]
            del settings
            return {
                "generatedAt": "2026-03-21T10:00:00+00:00",
                "jobId": None,
                "targetId": target.target_id,
                "targetType": target.target_type.value,
                "state": "completed",
                "verificationStatus": "ready",
                "summary": (
                    "Target validation completed for currently implemented connectivity and "
                    "destination checks. SSH target reachable, but files-only remote execution "
                    "is blocked because local rsync is not available on PATH."
                ),
                "checks": [],
                "warnings": [],
                "executionSupport": {
                    "supported": False,
                    "state": "blocked",
                    "summary": (
                        "SSH target reachable, but files-only remote execution is blocked "
                        "because local rsync is not available on PATH."
                    ),
                },
            }

    class FailIfCalledTransferExecutor:
        def execute(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            raise AssertionError("Remote transfer must not start when execution support is blocked.")

    runtime = BackgroundJobRuntime()
    try:
        service = ManualBackupExecutionService(
            runtime=runtime,
            target_settings=target_settings,
            validator=FakeValidator(),
            transfer_executor=FailIfCalledTransferExecutor(),
        )
        service.start_execution(settings, target_id=target_id)
        _wait_for_execution(runtime)
        current = service.get_current(settings)
    finally:
        runtime.shutdown()

    assert current["state"] == "unsupported"
    assert "local rsync is not available on PATH" in current["summary"]
