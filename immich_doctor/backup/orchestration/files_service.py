"""Thin application service for the user-facing backup files flow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.backup.core.models import (
    BackupContext,
    BackupResult,
    BackupTarget,
    ResolvedBackupLocation,
)
from immich_doctor.backup.core.resolver import BackupLocationResolver
from immich_doctor.backup.files.executor import FileBackupExecutionError, LocalFileBackupExecutor
from immich_doctor.backup.files.models import FileBackupRequest
from immich_doctor.backup.files.versioning import VersionedDestinationBuilder
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus


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
    clock: Callable[[], datetime] = field(default_factory=lambda: lambda: datetime.now(UTC))

    def run(self, settings: AppSettings) -> BackupResult:
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
            return self.executor.execute(plan)
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
