from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.backup.verify.service import BackupVerifyService
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport
from immich_doctor.core.paths import configured_immich_paths
from immich_doctor.db.health.service import DbHealthCheckService
from immich_doctor.runtime.validate.service import RuntimeValidationService


class DashboardHealthStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    UNKNOWN = "unknown"


class DashboardHealthItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: str
    status: DashboardHealthStatus
    summary: str
    details: str
    updated_at: str = Field(alias="updatedAt")
    blocking: bool
    source: str


class DashboardHealthOverview(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    generated_at: str = Field(alias="generatedAt")
    overall_status: DashboardHealthStatus = Field(alias="overallStatus")
    items: list[DashboardHealthItem]


@dataclass(slots=True)
class DashboardHealthService:
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    db_health: DbHealthCheckService = field(default_factory=DbHealthCheckService)
    runtime_validation: RuntimeValidationService = field(default_factory=RuntimeValidationService)
    backup_verify: BackupVerifyService = field(default_factory=BackupVerifyService)

    def run(self, settings: AppSettings) -> DashboardHealthOverview:
        timestamp = datetime.now(UTC).isoformat()
        items = [
            self._build_immich_configured_item(timestamp),
            self._build_immich_reachable_item(timestamp),
            self._build_db_item(settings, timestamp),
            self._build_storage_item(settings, timestamp),
            self._build_path_readiness_item(settings, timestamp),
            self._build_backup_item(settings, timestamp),
            self._build_runtime_scheduler_item(settings, timestamp),
        ]
        return DashboardHealthOverview(
            generatedAt=timestamp,
            overallStatus=self._derive_overall_status(items),
            items=items,
        )

    def _build_immich_configured_item(self, timestamp: str) -> DashboardHealthItem:
        return DashboardHealthItem(
            id="immich-configured",
            title="Immich configured",
            status=DashboardHealthStatus.UNKNOWN,
            summary="Immich server connection settings are not implemented yet.",
            details=(
                "This backend currently validates local runtime, database, storage, and backup "
                "state, but has no Immich API base URL or token settings to verify."
            ),
            updatedAt=timestamp,
            blocking=True,
            source="immich",
        )

    def _build_immich_reachable_item(self, timestamp: str) -> DashboardHealthItem:
        return DashboardHealthItem(
            id="immich-reachable",
            title="Immich reachable",
            status=DashboardHealthStatus.UNKNOWN,
            summary="Immich reachability cannot be verified yet.",
            details=(
                "An Immich API adapter is not implemented yet, so the dashboard cannot truthfully "
                "check server reachability."
            ),
            updatedAt=timestamp,
            blocking=True,
            source="immich",
        )

    def _build_db_item(self, settings: AppSettings, timestamp: str) -> DashboardHealthItem:
        host, port = settings.postgres_target()
        dsn = settings.postgres_dsn_value()

        if host is None or port is None:
            return DashboardHealthItem(
                id="db-reachability",
                title="DB reachable",
                status=DashboardHealthStatus.UNKNOWN,
                summary="Database target is not configured.",
                details=(
                    "Set DB_HOST/DB_PORT or IMMICH_DOCTOR_POSTGRES_DSN before DB "
                    "reachability can be checked."
                ),
                updatedAt=timestamp,
                blocking=True,
                source="db",
            )

        if dsn is None:
            return DashboardHealthItem(
                id="db-reachability",
                title="DB reachable",
                status=DashboardHealthStatus.UNKNOWN,
                summary="Database credentials are incomplete.",
                details=(
                    "Host resolution and TCP target are configured, but login credentials are not "
                    "complete enough for a full PostgreSQL connection test."
                ),
                updatedAt=timestamp,
                blocking=True,
                source="db",
            )

        report = self.db_health.run(settings)
        failing_messages = self._collect_check_messages(
            report,
            {CheckStatus.FAIL, CheckStatus.WARN},
        )
        status = self._map_report_status(report)

        if status == DashboardHealthStatus.OK:
            summary = "PostgreSQL host, TCP reachability, login, and round-trip query passed."
            details = f"Database checks completed successfully against {host}:{port}."
        else:
            summary = "PostgreSQL reachability or login checks failed."
            details = " ".join(failing_messages) if failing_messages else report.summary

        return DashboardHealthItem(
            id="db-reachability",
            title="DB reachable",
            status=status,
            summary=summary,
            details=details,
            updatedAt=timestamp,
            blocking=True,
            source="db",
        )

    def _build_storage_item(self, settings: AppSettings, timestamp: str) -> DashboardHealthItem:
        source_paths = configured_immich_paths(settings)
        if not source_paths:
            return DashboardHealthItem(
                id="storage-reachability",
                title="Storage reachable",
                status=DashboardHealthStatus.UNKNOWN,
                summary="No Immich storage paths are configured.",
                details=(
                    "Set at least one Immich storage path before the dashboard can verify source "
                    "storage reachability."
                ),
                updatedAt=timestamp,
                blocking=True,
                source="storage",
            )

        failed_checks: list[CheckResult] = []
        for name, path in source_paths.items():
            directory_check = self.filesystem.validate_directory(name=name, path=path)
            if directory_check.status != CheckStatus.PASS:
                failed_checks.append(directory_check)
                continue

            readable_check = self.filesystem.validate_readable_directory(
                name=f"{name}_readable",
                path=path,
            )
            if readable_check.status != CheckStatus.PASS:
                failed_checks.append(readable_check)

        if failed_checks:
            return DashboardHealthItem(
                id="storage-reachability",
                title="Storage reachable",
                status=DashboardHealthStatus.ERROR,
                summary="One or more configured storage paths are not reachable.",
                details=" ".join(check.message for check in failed_checks),
                updatedAt=timestamp,
                blocking=True,
                source="storage",
            )

        return DashboardHealthItem(
            id="storage-reachability",
            title="Storage reachable",
            status=DashboardHealthStatus.OK,
            summary="Configured storage paths exist and are readable.",
            details=f"Verified {len(source_paths)} configured Immich storage paths.",
            updatedAt=timestamp,
            blocking=True,
            source="storage",
        )

    def _build_path_readiness_item(
        self,
        settings: AppSettings,
        timestamp: str,
    ) -> DashboardHealthItem:
        expected_paths = {
            "immich_library_root": settings.immich_library_root,
            "immich_uploads_path": settings.immich_uploads_path,
            "immich_thumbs_path": settings.immich_thumbs_path,
            "immich_profile_path": settings.immich_profile_path,
            "immich_video_path": settings.immich_video_path,
        }
        configured_paths = {name: path for name, path in expected_paths.items() if path is not None}
        missing_names = [name for name, path in expected_paths.items() if path is None]

        if not configured_paths:
            return DashboardHealthItem(
                id="path-readiness",
                title="Path readiness",
                status=DashboardHealthStatus.UNKNOWN,
                summary="No Immich path configuration is present.",
                details=(
                    "All configured-path checks remain unknown until Immich storage paths are set."
                ),
                updatedAt=timestamp,
                blocking=False,
                source="storage",
            )

        failures: list[str] = []
        warnings: list[str] = []

        for name, path in configured_paths.items():
            if not self.filesystem.path_exists(path):
                failures.append(f"{name} does not exist at {path}.")

        root = settings.immich_library_root
        child_paths = {
            "immich_uploads_path": settings.immich_uploads_path,
            "immich_thumbs_path": settings.immich_thumbs_path,
            "immich_profile_path": settings.immich_profile_path,
            "immich_video_path": settings.immich_video_path,
        }

        if root is None:
            warnings.append(
                "immich_library_root is not configured; child path relationships "
                "cannot be fully verified."
            )
        else:
            for name, path in child_paths.items():
                if path is None:
                    continue
                if not self.filesystem.is_child_path(parent=root, child=path):
                    failures.append(f"{name} is outside immich_library_root.")

        if missing_names:
            warnings.append(f"Missing expected path settings: {', '.join(missing_names)}.")

        if failures:
            return DashboardHealthItem(
                id="path-readiness",
                title="Path readiness",
                status=DashboardHealthStatus.ERROR,
                summary="Path configuration contains blocking problems.",
                details=" ".join(failures + warnings),
                updatedAt=timestamp,
                blocking=False,
                source="storage",
            )

        if warnings:
            return DashboardHealthItem(
                id="path-readiness",
                title="Path readiness",
                status=DashboardHealthStatus.WARNING,
                summary="Path configuration is only partially ready.",
                details=" ".join(warnings),
                updatedAt=timestamp,
                blocking=False,
                source="storage",
            )

        return DashboardHealthItem(
            id="path-readiness",
            title="Path readiness",
            status=DashboardHealthStatus.OK,
            summary="Expected Immich path settings are configured and structurally valid.",
            details=(
                "Library root and child path relationships passed the current readiness checks."
            ),
            updatedAt=timestamp,
            blocking=False,
            source="storage",
        )

    def _build_backup_item(self, settings: AppSettings, timestamp: str) -> DashboardHealthItem:
        if settings.backup_target_path is None:
            return DashboardHealthItem(
                id="backup-readiness",
                title="Backup readiness",
                status=DashboardHealthStatus.UNKNOWN,
                summary="Backup target path is not configured.",
                details="Set BACKUP_TARGET_PATH before backup readiness can be verified.",
                updatedAt=timestamp,
                blocking=False,
                source="backup",
            )

        report = self.backup_verify.run(settings)
        failing_messages = self._collect_check_messages(
            report,
            {CheckStatus.FAIL, CheckStatus.WARN},
        )
        status = self._map_report_status(report)

        if status == DashboardHealthStatus.OK:
            summary = "Backup target checks passed."
            details = (
                "Backup target path exists and passed readability, writability, and "
                "required tool checks."
            )
        else:
            summary = "Backup readiness checks found blocking issues."
            details = " ".join(failing_messages) if failing_messages else report.summary

        return DashboardHealthItem(
            id="backup-readiness",
            title="Backup readiness",
            status=status,
            summary=summary,
            details=details,
            updatedAt=timestamp,
            blocking=False,
            source="backup",
        )

    def _build_runtime_scheduler_item(
        self,
        settings: AppSettings,
        timestamp: str,
    ) -> DashboardHealthItem:
        report = self.runtime_validation.run(settings)
        failing_messages = self._collect_check_messages(
            report,
            {CheckStatus.FAIL, CheckStatus.WARN},
        )

        if report.overall_status == CheckStatus.FAIL:
            return DashboardHealthItem(
                id="scheduler-runtime-readiness",
                title="Scheduler / runtime readiness",
                status=DashboardHealthStatus.ERROR,
                summary="Runtime validation failed.",
                details=" ".join(failing_messages) if failing_messages else report.summary,
                updatedAt=timestamp,
                blocking=False,
                source="runtime",
            )

        return DashboardHealthItem(
            id="scheduler-runtime-readiness",
            title="Scheduler / runtime readiness",
            status=DashboardHealthStatus.UNKNOWN,
            summary="Runtime checks passed, but scheduler health is not implemented yet.",
            details=(
                "Runtime identity and Python/platform checks are available. Scheduler readiness "
                "remains unknown until scheduling support exists in the backend."
            ),
            updatedAt=timestamp,
            blocking=False,
            source="runtime",
        )

    def _collect_check_messages(
        self,
        report: ValidationReport,
        statuses: set[CheckStatus],
    ) -> list[str]:
        return [check.message for check in report.checks if check.status in statuses]

    def _map_report_status(self, report: ValidationReport) -> DashboardHealthStatus:
        return self._map_check_status(report.overall_status)

    def _map_check_status(self, status: CheckStatus) -> DashboardHealthStatus:
        mapping = {
            CheckStatus.PASS: DashboardHealthStatus.OK,
            CheckStatus.WARN: DashboardHealthStatus.WARNING,
            CheckStatus.FAIL: DashboardHealthStatus.ERROR,
            CheckStatus.SKIP: DashboardHealthStatus.UNKNOWN,
        }
        return mapping[status]

    def _derive_overall_status(
        self,
        items: list[DashboardHealthItem],
    ) -> DashboardHealthStatus:
        statuses = {item.status for item in items}
        if DashboardHealthStatus.ERROR in statuses:
            return DashboardHealthStatus.ERROR
        if DashboardHealthStatus.WARNING in statuses:
            return DashboardHealthStatus.WARNING
        if DashboardHealthStatus.UNKNOWN in statuses:
            return DashboardHealthStatus.UNKNOWN
        return DashboardHealthStatus.OK
