"""Thin application service for the user-facing backup files flow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.backup.core.models import (
    BackupContext,
    BackupManifest,
    BackupResult,
    BackupSnapshot,
    BackupTarget,
    ResolvedBackupLocation,
    SnapshotCoverage,
    SnapshotKind,
)
from immich_doctor.backup.core.resolver import BackupLocationResolver
from immich_doctor.backup.core.store import BackupSnapshotStore
from immich_doctor.backup.files.executor import FileBackupExecutionError, LocalFileBackupExecutor
from immich_doctor.backup.files.models import FileBackupRequest
from immich_doctor.backup.files.versioning import VersionedDestinationBuilder
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.repair.guards import fingerprint_payload


class LocalBackupLocationResolver(BackupLocationResolver):
    """Resolve a local backup target to a concrete filesystem root."""

    def resolve(self, context: BackupContext) -> ResolvedBackupLocation:
        return ResolvedBackupLocation(
            target=context.target,
            root_path=Path(context.target.reference).expanduser(),
        )


@dataclass(slots=True)
class BackupFilesService:
    """Application-layer entrypoint for one local file backup operation."""

    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    location_resolver: BackupLocationResolver = field(default_factory=LocalBackupLocationResolver)
    destination_builder: VersionedDestinationBuilder = field(
        default_factory=VersionedDestinationBuilder
    )
    executor: LocalFileBackupExecutor = field(default_factory=LocalFileBackupExecutor)
    snapshot_store: BackupSnapshotStore = field(default_factory=BackupSnapshotStore)
    clock: Callable[[], datetime] = field(default_factory=lambda: lambda: datetime.now(UTC))

    def run(
        self,
        settings: AppSettings,
        *,
        snapshot_kind: SnapshotKind = SnapshotKind.MANUAL,
        repair_run_id: str | None = None,
        source_fingerprint: str | None = None,
    ) -> BackupResult:
        target_path = settings.backup_target_path
        source_path = settings.immich_library_root

        context = BackupContext(
            job_name="backup-files",
            requested_components=("files",),
            target=BackupTarget(
                kind="local",
                reference=str(target_path) if target_path else "",
                display_name=target_path.name if target_path else "backup-target",
            ),
            started_at=self.clock(),
        )

        issues = self._configuration_issues(source_path=source_path, target_path=target_path)
        if issues:
            return BackupResult(
                domain="backup.files",
                action="run",
                status="fail",
                summary="File backup configuration is invalid.",
                context=context,
                warnings=tuple(issue["message"] for issue in issues),
                details={"issues": issues},
            )

        resolved_location = self.location_resolver.resolve(context)
        request = FileBackupRequest(
            context=context,
            location=resolved_location,
            source_path=source_path,
            source_label="immich-library",
        )
        plan = self.destination_builder.build(request)

        try:
            result = self.executor.execute(plan)
        except FileBackupExecutionError as exc:
            return BackupResult(
                domain="backup.files",
                action="run",
                status="fail",
                summary="File backup execution failed.",
                context=context,
                warnings=(exc.message,),
                details={
                    "resolved_location": resolved_location.to_dict(),
                    "execution_plan": {
                        "backup_root_path": plan.backup_root_path.as_posix(),
                        "artifact_relative_path": plan.artifact_relative_path.as_posix(),
                        "destination_path": plan.destination_path.as_posix(),
                    },
                    "error": exc.to_dict(),
                },
            )

        return self._attach_snapshot(
            settings,
            result=result,
            source_path=source_path,
            snapshot_kind=snapshot_kind,
            repair_run_id=repair_run_id,
            source_fingerprint=source_fingerprint,
        )

    def _configuration_issues(
        self,
        *,
        source_path: Path | None,
        target_path: Path | None,
    ) -> list[dict[str, object]]:
        issues: list[dict[str, object]] = []

        if source_path is None:
            issues.append(
                {
                    "name": "immich_library_root",
                    "message": "Immich library root is not configured.",
                }
            )
        else:
            issues.extend(
                self._issue_from_check(
                    self.filesystem.validate_directory("source_path", source_path)
                )
            )
            issues.extend(
                self._issue_from_check(
                    self.filesystem.validate_readable_directory("source_path_readable", source_path)
                )
            )

        if target_path is None:
            issues.append(
                {
                    "name": "backup_target_path",
                    "message": "Backup target path is not configured.",
                }
            )
        else:
            issues.extend(
                self._issue_from_check(
                    self.filesystem.validate_directory("target_path", target_path)
                )
            )
            issues.extend(
                self._issue_from_check(
                    self.filesystem.validate_writable_directory("target_path_writable", target_path)
                )
            )

        return issues

    def _issue_from_check(self, check: CheckResult) -> list[dict[str, object]]:
        if check.status == CheckStatus.PASS:
            return []

        issue: dict[str, object] = {
            "name": check.name,
            "status": check.status.value.upper(),
            "message": check.message,
        }
        if check.details:
            issue["details"] = check.details
        return [issue]

    def _attach_snapshot(
        self,
        settings: AppSettings,
        *,
        result: BackupResult,
        source_path: Path | None,
        snapshot_kind: SnapshotKind,
        repair_run_id: str | None,
        source_fingerprint: str | None,
    ) -> BackupResult:
        snapshot = BackupSnapshot(
            snapshot_id=uuid4().hex,
            kind=snapshot_kind,
            created_at=result.context.started_at,
            source_fingerprint=source_fingerprint
            or self._default_source_fingerprint(result.context, source_path),
            coverage=SnapshotCoverage.FILES_ONLY,
            file_artifacts=result.artifacts,
            db_artifact=None,
            manifest_path=Path("pending"),
            verified=False,
            repair_run_id=repair_run_id,
        )
        persisted_snapshot = self.snapshot_store.persist_snapshot(settings, snapshot)
        manifest = BackupManifest(
            timestamp=result.context.started_at,
            included_components=result.context.requested_components,
            artifacts=result.artifacts,
            snapshot=persisted_snapshot,
        )
        details = dict(result.details)
        details["snapshot_id"] = persisted_snapshot.snapshot_id
        details["snapshot_kind"] = persisted_snapshot.kind.value
        details["snapshot_manifest_path"] = persisted_snapshot.manifest_path.as_posix()
        details["snapshot_coverage"] = persisted_snapshot.coverage.value
        if persisted_snapshot.repair_run_id is not None:
            details["repair_run_id"] = persisted_snapshot.repair_run_id
        return BackupResult(
            domain=result.domain,
            action=result.action,
            status=result.status,
            summary=result.summary,
            context=result.context,
            artifacts=result.artifacts,
            manifest=manifest,
            snapshot=persisted_snapshot,
            warnings=result.warnings,
            details=details,
        )

    def _default_source_fingerprint(
        self,
        context: BackupContext,
        source_path: Path | None,
    ) -> str:
        return fingerprint_payload(
            {
                "job_name": context.job_name,
                "requested_components": list(context.requested_components),
                "target_reference": context.target.reference,
                "started_at": context.started_at.isoformat(),
                "source_path": str(source_path) if source_path is not None else None,
            }
        )
