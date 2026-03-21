from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.backup.core.job_models import (
    TERMINAL_BACKGROUND_JOB_STATES,
    BackgroundJobState,
)
from immich_doctor.backup.core.models import (
    BackupArtifact,
    BackupSnapshot,
    BackupTarget,
    SnapshotCoverage,
    SnapshotKind,
)
from immich_doctor.backup.core.store import BackupSnapshotStore
from immich_doctor.backup.files.executor import FileBackupExecutionError
from immich_doctor.backup.files.transfer import ManagedRsyncTransferExecutor
from immich_doctor.backup.targets.models import (
    BackupRestoreReadiness,
    BackupTargetLastBackupMetadata,
    BackupTargetMountStrategy,
    BackupTargetType,
    VerificationLevel,
)
from immich_doctor.core.config import AppSettings
from immich_doctor.services.backup_asset_workflow_service import BackupAssetWorkflowService
from immich_doctor.services.backup_job_service import BackgroundJobRuntime, ManagedJobHandle
from immich_doctor.services.backup_size_service import BackupSizeEstimationService
from immich_doctor.services.backup_snapshot_service import summarize_backup_snapshot
from immich_doctor.services.backup_target_settings_service import BackupTargetSettingsService
from immich_doctor.services.backup_target_validation_service import BackupTargetValidationService
from immich_doctor.services.backup_transport_service import BackupTransportService

BACKUP_EXECUTION_JOB_TYPE = "backup_manual_execution"


class PreparedBackupAccessKind(StrEnum):
    PATH_LIKE = "path_like"
    TRANSPORT_PREPARED = "transport_prepared"


class PreparedBackupDestinationSemantics(StrEnum):
    MIRROR_SYNC = "mirror_sync"
    VERSIONED_SNAPSHOT = "versioned_snapshot"


class PreparedBackupExecutionMode(StrEnum):
    ASSET_AWARE_SYNC = "asset_aware_sync"
    VERSIONED_TRANSFER = "versioned_transfer"


@dataclass(slots=True, frozen=True)
class PreparedBackupExecutionContext:
    target_id: str
    target_type: BackupTargetType
    access_kind: PreparedBackupAccessKind
    destination_semantics: PreparedBackupDestinationSemantics
    execution_mode: PreparedBackupExecutionMode
    effective_destination_path: str | None
    prepared_target_reference: str | None
    restore_readiness: BackupRestoreReadiness
    warnings: tuple[str, ...] = ()

    @property
    def is_path_like_usable_destination(self) -> bool:
        return self.access_kind == PreparedBackupAccessKind.PATH_LIKE

    @property
    def is_transport_prepared_destination(self) -> bool:
        return self.access_kind == PreparedBackupAccessKind.TRANSPORT_PREPARED

    @property
    def is_versioned_snapshot_destination(self) -> bool:
        return (
            self.destination_semantics
            == PreparedBackupDestinationSemantics.VERSIONED_SNAPSHOT
        )

    @property
    def is_mirror_sync_destination(self) -> bool:
        return self.destination_semantics == PreparedBackupDestinationSemantics.MIRROR_SYNC

    def to_dict(self) -> dict[str, object]:
        return {
            "targetId": self.target_id,
            "targetType": self.target_type.value,
            "accessKind": self.access_kind.value,
            "destinationSemantics": self.destination_semantics.value,
            "executionMode": self.execution_mode.value,
            "effectiveDestinationPath": self.effective_destination_path,
            "preparedTargetReference": self.prepared_target_reference,
            "restoreReadiness": self.restore_readiness.value,
            "pathLikeUsableDestination": self.is_path_like_usable_destination,
            "transportPreparedDestination": self.is_transport_prepared_destination,
            "versionedSnapshotDestination": self.is_versioned_snapshot_destination,
            "mirrorSyncDestination": self.is_mirror_sync_destination,
            "warnings": list(self.warnings),
        }


@dataclass(slots=True)
class ManualBackupExecutionService:
    runtime: BackgroundJobRuntime
    target_settings: BackupTargetSettingsService = field(
        default_factory=BackupTargetSettingsService
    )
    validator: BackupTargetValidationService | None = None
    snapshot_store: BackupSnapshotStore = field(default_factory=BackupSnapshotStore)
    transfer_executor: ManagedRsyncTransferExecutor = field(
        default_factory=ManagedRsyncTransferExecutor
    )
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    asset_workflow_service: BackupAssetWorkflowService = field(
        default_factory=BackupAssetWorkflowService
    )

    def __post_init__(self) -> None:
        if self.validator is None:
            self.validator = BackupTargetValidationService(runtime=self.runtime)

    def get_current(self, settings: AppSettings) -> dict[str, object]:
        active = self.runtime.active_job(job_type=BACKUP_EXECUTION_JOB_TYPE)
        if active is not None:
            return active.result

        latest = self.runtime.store.find_latest_job(
            settings,
            job_type=BACKUP_EXECUTION_JOB_TYPE,
            states=set(TERMINAL_BACKGROUND_JOB_STATES),
        )
        if latest is None:
            return self._idle_snapshot()
        return latest.result

    def start_execution(
        self,
        settings: AppSettings,
        *,
        target_id: str,
        snapshot_kind: SnapshotKind = SnapshotKind.MANUAL,
    ) -> dict[str, object]:
        active = self.runtime.active_job(job_type=BACKUP_EXECUTION_JOB_TYPE)
        if active is not None:
            return active.result

        target = self.target_settings.get_target(settings, target_id=target_id)
        pending = {
            "generatedAt": datetime.now(UTC).isoformat(),
            "jobId": None,
            "targetId": target_id,
            "targetType": target.target_type.value,
            "requestedKind": snapshot_kind.value,
            "coverage": "files_only",
            "restoreReadiness": target.restore_readiness.value,
            "state": "pending",
            "summary": self._pending_summary(target),
            "report": None,
            "snapshot": None,
            "warnings": list(target.warnings),
        }
        record = self.runtime.start_job(
            settings,
            job_type=BACKUP_EXECUTION_JOB_TYPE,
            initial_result=pending,
            summary=str(pending["summary"]),
            runner=lambda handle: self._run_execution(
                handle,
                target_id=target_id,
                snapshot_kind=snapshot_kind,
            ),
        )
        pending["jobId"] = record.job_id
        return pending

    def request_cancel(self) -> dict[str, object] | None:
        record = self.runtime.request_cancel(job_type=BACKUP_EXECUTION_JOB_TYPE)
        if record is None:
            return None
        return record.result

    def _run_execution(
        self,
        handle: ManagedJobHandle,
        *,
        target_id: str,
        snapshot_kind: SnapshotKind,
    ) -> dict[str, object]:
        target = self.target_settings.get_target(handle.settings, target_id=target_id)
        validation = self.validator.validate_target_now(handle.settings, target=target)
        if validation["state"] not in {"completed", "partial"}:
            return {
                "generatedAt": datetime.now(UTC).isoformat(),
                "jobId": handle.record.job_id,
                "targetId": target_id,
                "targetType": target.target_type.value,
                "requestedKind": snapshot_kind.value,
                "coverage": "files_only",
                "restoreReadiness": target.restore_readiness.value,
                "state": validation["state"],
                "summary": (
                    "Backup execution cannot start because target validation did not pass."
                ),
                "report": {
                    "verificationLevel": VerificationLevel.NONE.value,
                    "warnings": list(validation["warnings"]),
                    "validationChecks": validation["checks"],
                },
                "snapshot": None,
                "warnings": list(validation["warnings"]),
            }

        source_path = handle.settings.immich_library_root
        if source_path is None:
            return self._failed_result(
                handle.record.job_id,
                target,
                snapshot_kind=snapshot_kind,
                summary="Backup execution failed because IMMICH library root is not configured.",
            )
        source_check = self.filesystem.validate_readable_directory("source_path", source_path)
        if source_check.status.value != "pass":
            return self._failed_result(
                handle.record.job_id,
                target,
                snapshot_kind=snapshot_kind,
                summary=source_check.message,
            )

        started_at = datetime.now(UTC)
        version_id = started_at.strftime("%Y%m%dT%H%M%SZ")
        artifact_relative_path = Path("files/immich-library")
        planned = self._planned_metrics(handle.settings)
        try:
            prepared_context = self.prepare_execution_context(target)
        except ValueError as exc:
            return {
                "generatedAt": datetime.now(UTC).isoformat(),
                "jobId": handle.record.job_id,
                "targetId": target_id,
                "targetType": target.target_type.value,
                "requestedKind": snapshot_kind.value,
                "coverage": "files_only",
                "restoreReadiness": target.restore_readiness.value,
                "state": "unsupported",
                "summary": str(exc),
                "report": {
                    "verificationLevel": VerificationLevel.NONE.value,
                    "details": {
                        "executionPreparationError": str(exc),
                    },
                },
                "snapshot": None,
                "warnings": [str(exc)],
            }
        running_summary = self._running_summary(prepared_context)

        handle.update(
            state=BackgroundJobState.RUNNING,
            summary=running_summary,
            result={
                "generatedAt": datetime.now(UTC).isoformat(),
                "jobId": handle.record.job_id,
                "targetId": target_id,
                "targetType": target.target_type.value,
                "requestedKind": snapshot_kind.value,
                "coverage": "files_only",
                "restoreReadiness": target.restore_readiness.value,
                "state": "running",
                "summary": running_summary,
                "report": planned,
                "snapshot": None,
                "warnings": list(prepared_context.warnings),
            },
        )

        if prepared_context.execution_mode == PreparedBackupExecutionMode.ASSET_AWARE_SYNC:
            workflow_result = self.asset_workflow_service.sync_missing(
                handle.settings,
                target_id=target_id,
            )
            bytes_transferred = sum(
                int(item.get("details", {}).get("targetSize") or 0)
                for item in workflow_result["report"]["results"]
                if item.get("resultStatus") == "restored"
            )
            copied_count = int(workflow_result["report"]["copiedCount"])
            updated_target = target.model_copy(
                update={
                    "last_successful_backup": BackupTargetLastBackupMetadata(
                        backupId=version_id,
                        completedAt=datetime.now(UTC).isoformat(),
                        sourceScope="files_only",
                        bytesTransferred=bytes_transferred,
                        verificationLevel=VerificationLevel.COPIED_FILES_SHA256,
                        snapshotId=None,
                    )
                }
            )
            self.target_settings.save_target(handle.settings, updated_target)
            return {
                "generatedAt": datetime.now(UTC).isoformat(),
                "jobId": handle.record.job_id,
                "targetId": target_id,
                "targetType": target.target_type.value,
                "requestedKind": snapshot_kind.value,
                "coverage": "files_only",
                "restoreReadiness": target.restore_readiness.value,
                "state": workflow_result["state"],
                "summary": workflow_result["summary"],
                "report": {
                    "sourceScope": "files_only",
                    "targetType": target.target_type.value,
                    "bytesPlanned": planned.get("bytesPlanned"),
                    "bytesTransferred": bytes_transferred,
                    "fileCounts": {
                        "planned": planned.get("fileCount"),
                        "transferred": copied_count,
                    },
                    "durationSeconds": None,
                    "warnings": list(prepared_context.warnings),
                    "verificationLevel": VerificationLevel.COPIED_FILES_SHA256.value,
                    "versionId": version_id,
                    "details": {
                        "executionContext": prepared_context.to_dict(),
                        "workflow": workflow_result["report"],
                    },
                },
                "snapshot": None,
                "warnings": list(prepared_context.warnings),
            }

        try:
            transfer, backup_root_reference, verification_level = self._execute_transfer(
                handle,
                target=target,
                prepared_context=prepared_context,
                source_path=source_path,
                version_id=version_id,
            )
        except FileBackupExecutionError as exc:
            state = "canceled" if "canceled" in exc.message.lower() else "failed"
            return {
                "generatedAt": datetime.now(UTC).isoformat(),
                "jobId": handle.record.job_id,
                "targetId": target_id,
                "targetType": target.target_type.value,
                "requestedKind": snapshot_kind.value,
                "coverage": "files_only",
                "restoreReadiness": target.restore_readiness.value,
                "state": state,
                "summary": exc.message,
                "report": {
                    "sourceScope": "files_only",
                    "targetType": target.target_type.value,
                    "bytesPlanned": planned.get("bytesPlanned"),
                    "bytesTransferred": None,
                    "fileCounts": None,
                    "durationSeconds": None,
                    "warnings": [
                        "Execution may have left an incomplete destination version behind."
                    ],
                    "verificationLevel": VerificationLevel.NONE.value,
                    "details": {
                        "executionContext": prepared_context.to_dict(),
                        "transferError": exc.to_dict(),
                    },
                },
                "snapshot": None,
                "warnings": [exc.message],
            }

        snapshot = self._persist_snapshot(
            handle.settings,
            target=target,
            prepared_context=prepared_context,
            snapshot_kind=snapshot_kind,
            started_at=started_at,
            backup_root_reference=backup_root_reference,
            artifact_relative_path=artifact_relative_path,
            total_size_bytes=transfer.metrics.total_file_size_bytes,
        )
        updated_target = target.model_copy(
            update={
                "last_successful_backup": BackupTargetLastBackupMetadata(
                    backupId=version_id,
                    completedAt=datetime.now(UTC).isoformat(),
                    sourceScope="files_only",
                    bytesTransferred=transfer.metrics.bytes_transferred,
                    verificationLevel=verification_level,
                    snapshotId=snapshot.snapshot_id,
                )
            }
        )
        self.target_settings.save_target(handle.settings, updated_target)

        return {
            "generatedAt": datetime.now(UTC).isoformat(),
            "jobId": handle.record.job_id,
            "targetId": target_id,
            "targetType": target.target_type.value,
            "requestedKind": snapshot_kind.value,
            "coverage": "files_only",
            "restoreReadiness": target.restore_readiness.value,
            "state": "completed",
            "summary": (
                "Manual files-only backup completed. Restore execution remains unavailable."
            ),
            "report": {
                "sourceScope": "files_only",
                "targetType": target.target_type.value,
                "bytesPlanned": planned.get("bytesPlanned"),
                "bytesTransferred": transfer.metrics.bytes_transferred,
                "fileCounts": {
                    "planned": planned.get("fileCount"),
                    "transferred": transfer.metrics.regular_files_transferred,
                },
                "durationSeconds": transfer.duration_seconds,
                "warnings": list(target.warnings),
                "verificationLevel": verification_level.value,
                "versionId": version_id,
                "snapshotId": snapshot.snapshot_id,
                "details": {
                    "executionContext": prepared_context.to_dict(),
                },
            },
            "snapshot": summarize_backup_snapshot(snapshot),
            "warnings": list(target.warnings),
        }

    def prepare_execution_context(
        self,
        target,
    ) -> PreparedBackupExecutionContext:
        warnings = tuple(target.warnings)
        if target.target_type == BackupTargetType.LOCAL and target.transport.path is not None:
            destination_path = Path(target.transport.path).expanduser().as_posix()
            return PreparedBackupExecutionContext(
                target_id=target.target_id,
                target_type=target.target_type,
                access_kind=PreparedBackupAccessKind.PATH_LIKE,
                destination_semantics=PreparedBackupDestinationSemantics.MIRROR_SYNC,
                execution_mode=PreparedBackupExecutionMode.ASSET_AWARE_SYNC,
                effective_destination_path=destination_path,
                prepared_target_reference=destination_path,
                restore_readiness=target.restore_readiness,
                warnings=warnings,
            )
        if (
            target.target_type == BackupTargetType.SMB
            and target.transport.mount_strategy == BackupTargetMountStrategy.PRE_MOUNTED_PATH
            and target.transport.mounted_path is not None
        ):
            destination_path = Path(target.transport.mounted_path).expanduser().as_posix()
            return PreparedBackupExecutionContext(
                target_id=target.target_id,
                target_type=target.target_type,
                access_kind=PreparedBackupAccessKind.PATH_LIKE,
                destination_semantics=PreparedBackupDestinationSemantics.MIRROR_SYNC,
                execution_mode=PreparedBackupExecutionMode.ASSET_AWARE_SYNC,
                effective_destination_path=destination_path,
                prepared_target_reference=destination_path,
                restore_readiness=target.restore_readiness,
                warnings=warnings,
            )
        if target.target_type in {BackupTargetType.SSH, BackupTargetType.RSYNC}:
            remote_path = target.transport.remote_path
            prepared_target_reference = None
            if (
                target.transport.username is not None
                and target.transport.host is not None
                and remote_path is not None
            ):
                prepared_target_reference = (
                    f"{target.transport.username}@{target.transport.host}:{remote_path}"
                )
            return PreparedBackupExecutionContext(
                target_id=target.target_id,
                target_type=target.target_type,
                access_kind=PreparedBackupAccessKind.TRANSPORT_PREPARED,
                destination_semantics=PreparedBackupDestinationSemantics.VERSIONED_SNAPSHOT,
                execution_mode=PreparedBackupExecutionMode.VERSIONED_TRANSFER,
                effective_destination_path=remote_path,
                prepared_target_reference=prepared_target_reference,
                restore_readiness=target.restore_readiness,
                warnings=warnings,
            )
        raise ValueError(
            "Selected target does not expose a prepared execution context for the currently implemented backup flow."
        )

    def _execute_transfer(
        self,
        handle: ManagedJobHandle,
        *,
        target,
        prepared_context: PreparedBackupExecutionContext,
        source_path: Path,
        version_id: str,
    ):
        backup_root_reference: str
        verification_level = VerificationLevel.TRANSPORT_SUCCESS_ONLY
        if not prepared_context.is_transport_prepared_destination:
            raise FileBackupExecutionError(
                "Prepared backup execution context does not support transport-based versioned transfer."
            )
        transport = BackupTransportService(self.target_settings.secrets)
        with transport.prepared_remote_connection(handle.settings, target) as material:
            backup_root_path = f"{material.remote_path.rstrip('/')}/{version_id}"
            destination_path = f"{backup_root_path}/files/immich-library"
            transfer = self.transfer_executor.execute(
                source_path=source_path,
                destination_reference=transport.destination_reference(material, destination_path),
                remote_shell_argv=transport.remote_shell_command(material),
                cancel_requested=handle.cancel_requested,
            )
            verify = transport.run_remote_command(
                material,
                f"test -d {transport.quoted_remote_path(destination_path)}",
            )
            if verify.returncode == 0:
                verification_level = VerificationLevel.DESTINATION_EXISTS
            backup_root_reference = transport.destination_reference(material, backup_root_path)
            return transfer, backup_root_reference, verification_level

    def _persist_snapshot(
        self,
        settings: AppSettings,
        *,
        target,
        prepared_context: PreparedBackupExecutionContext,
        snapshot_kind: SnapshotKind,
        started_at: datetime,
        backup_root_reference: str,
        artifact_relative_path: Path,
        total_size_bytes: int | None,
    ) -> BackupSnapshot:
        artifact_target = BackupTarget(
            kind="local" if prepared_context.is_path_like_usable_destination else "remote",
            reference=backup_root_reference,
            display_name=target.target_name,
        )
        artifact = BackupArtifact(
            name="immich-library",
            kind="file_archive",
            target=artifact_target,
            relative_path=artifact_relative_path,
            size_bytes=total_size_bytes,
        )
        snapshot = BackupSnapshot(
            snapshot_id=uuid4().hex,
            kind=snapshot_kind,
            created_at=started_at,
            source_fingerprint=f"manual-backup:{target.target_id}:{started_at.isoformat()}",
            coverage=SnapshotCoverage.FILES_ONLY,
            file_artifacts=(artifact,),
            db_artifact=None,
            manifest_path=Path("pending"),
            verified=False,
        )
        return self.snapshot_store.persist_snapshot(settings, snapshot)

    def _planned_metrics(self, settings: AppSettings) -> dict[str, object]:
        size_snapshot = BackupSizeEstimationService(runtime=self.runtime).get_snapshot(settings)
        for scope in size_snapshot.scopes:
            scope_name = scope.scope
            if scope_name != "storage":
                continue
            return {
                "bytesPlanned": scope.bytes,
                "fileCount": scope.file_count,
            }
        return {"bytesPlanned": None, "fileCount": None}

    def _pending_summary(self, target) -> str:
        return (
            "Backup check/sync is pending."
            if self._uses_asset_aware_sync(target)
            else "Manual files-only backup is pending."
        )

    def _running_summary(self, prepared_context: PreparedBackupExecutionContext) -> str:
        return (
            "Backup check/sync is running."
            if prepared_context.execution_mode
            == PreparedBackupExecutionMode.ASSET_AWARE_SYNC
            else "Manual files-only backup is running."
        )

    def _uses_asset_aware_sync(self, target) -> bool:
        return target.target_type == BackupTargetType.LOCAL or (
            target.target_type == BackupTargetType.SMB
            and target.transport.mount_strategy == BackupTargetMountStrategy.PRE_MOUNTED_PATH
            and target.transport.mounted_path is not None
        )

    def _failed_result(
        self,
        job_id: str,
        target,
        *,
        snapshot_kind: SnapshotKind,
        summary: str,
    ) -> dict[str, object]:
        return {
            "generatedAt": datetime.now(UTC).isoformat(),
            "jobId": job_id,
            "targetId": target.target_id,
            "targetType": target.target_type.value,
            "requestedKind": snapshot_kind.value,
            "coverage": "files_only",
            "restoreReadiness": target.restore_readiness.value,
            "state": "failed",
            "summary": summary,
            "report": {
                "verificationLevel": VerificationLevel.NONE.value,
            },
            "snapshot": None,
            "warnings": [],
        }

    def _idle_snapshot(self) -> dict[str, object]:
        return {
            "generatedAt": datetime.now(UTC).isoformat(),
            "jobId": None,
            "state": "pending",
            "summary": "Backup check/sync has not run yet.",
            "report": None,
            "snapshot": None,
            "warnings": [],
        }
