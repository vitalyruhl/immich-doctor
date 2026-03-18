from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import monotonic

from immich_doctor.adapters.filesystem import (
    DirectoryScanCanceledError,
    DirectoryScanTimeoutError,
    FilesystemAdapter,
)
from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.backup.core.job_models import BackgroundJobState
from immich_doctor.backup.estimation.models import (
    BackupSizeCategory,
    BackupSizeEstimateSnapshot,
    BackupSizeProgress,
    BackupSizeScopeEstimate,
)
from immich_doctor.core.config import AppSettings

ProgressCallback = Callable[[BackupSizeEstimateSnapshot], None]

TERMINAL_STATES_WITH_DATA = frozenset(
    {
        BackgroundJobState.PARTIAL,
        BackgroundJobState.COMPLETED,
        BackgroundJobState.UNSUPPORTED,
    }
)


@dataclass(slots=True)
class BackupSizeCollector:
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)
    clock: Callable[[], datetime] = field(default_factory=lambda: lambda: datetime.now(UTC))
    freshness_seconds: int = 3600
    timeout_seconds: int = 300

    def pending_snapshot(self, *, job_id: str | None = None) -> BackupSizeEstimateSnapshot:
        timestamp = self.clock().isoformat()
        return BackupSizeEstimateSnapshot(
            generatedAt=timestamp,
            jobId=job_id,
            state=BackgroundJobState.PENDING,
            summary="Backup size collection is pending.",
            sourceScope="backup.files",
            scopes=[
                BackupSizeScopeEstimate(
                    scope="database",
                    label="Database backup estimate",
                    state=BackgroundJobState.PENDING,
                    sourceScope="database",
                    representation="physical_db_size_proxy",
                ),
                BackupSizeScopeEstimate(
                    scope="storage",
                    label="Storage backup estimate",
                    state=BackgroundJobState.PENDING,
                    sourceScope="immich_library_root",
                    representation="filesystem_usage",
                ),
            ],
            limitations=[
                "Database size currently uses PostgreSQL physical size "
                "as a backup proxy, not a logical dump byte count.",
                "Current executable backup coverage remains files-only "
                "unless a paired DB snapshot phase is added.",
                "Restore execution readiness is not implemented by this size estimate.",
            ],
        )

    def collect(
        self,
        settings: AppSettings,
        *,
        job_id: str,
        progress_callback: ProgressCallback | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> BackupSizeEstimateSnapshot:
        started_at = self.clock()
        started_monotonic = monotonic()
        deadline_monotonic = started_monotonic + self.timeout_seconds
        scope_results: list[BackupSizeScopeEstimate] = []

        self._emit(
            self.pending_snapshot(job_id=job_id).model_copy(
                update={
                    "state": BackgroundJobState.RUNNING,
                    "summary": "Backup size collection is running.",
                    "progress": BackupSizeProgress(
                        scope="database",
                        message="Backup size collection is running.",
                        current=0,
                        unit="scopes",
                    ),
                }
            ),
            progress_callback,
        )

        database_scope = self._collect_database_scope(
            settings,
            deadline_monotonic=deadline_monotonic,
        )
        scope_results.append(database_scope)
        self._emit(
            self._build_snapshot(
                job_id=job_id,
                started_at=started_at,
                scope_results=scope_results + [self._running_storage_placeholder()],
                progress=BackupSizeProgress(
                    scope="storage",
                    message="Backup size collection is running.",
                    current=1,
                    total=2,
                    unit="scopes",
                ),
            ),
            progress_callback,
        )

        storage_scope = self._collect_storage_scope(
            settings,
            deadline_monotonic=deadline_monotonic,
            cancel_requested=cancel_requested,
            progress_callback=progress_callback,
            job_id=job_id,
            started_at=started_at,
            scope_results=scope_results,
        )
        scope_results.append(storage_scope)

        return self._build_snapshot(
            job_id=job_id,
            started_at=started_at,
            scope_results=scope_results,
            progress=None,
        )

    def apply_freshness(
        self,
        snapshot: BackupSizeEstimateSnapshot,
        *,
        now: datetime | None = None,
    ) -> BackupSizeEstimateSnapshot:
        if snapshot.collected_at is None:
            return snapshot

        current_time = now or self.clock()
        collected_at = datetime.fromisoformat(snapshot.collected_at)
        age_seconds = max((current_time - collected_at).total_seconds(), 0.0)
        is_stale = age_seconds > self.freshness_seconds

        return snapshot.model_copy(
            update={
                "stale": is_stale,
                "cache_age_seconds": round(age_seconds, 3),
                "scopes": [
                    scope.model_copy(update={"stale": is_stale}) for scope in snapshot.scopes
                ],
            }
        )

    def is_fresh(self, snapshot: BackupSizeEstimateSnapshot) -> bool:
        return not self.apply_freshness(snapshot).stale

    def _collect_database_scope(
        self,
        settings: AppSettings,
        *,
        deadline_monotonic: float,
    ) -> BackupSizeScopeEstimate:
        started_monotonic = monotonic()
        dsn = settings.postgres_dsn_value()
        if dsn is None:
            return BackupSizeScopeEstimate(
                scope="database",
                label="Database backup estimate",
                state=BackgroundJobState.UNSUPPORTED,
                sourceScope="database",
                representation="physical_db_size_proxy",
                warnings=[
                    "Database size estimate is unavailable because "
                    "PostgreSQL credentials are not configured."
                ],
            )

        if monotonic() > deadline_monotonic:
            return BackupSizeScopeEstimate(
                scope="database",
                label="Database backup estimate",
                state=BackgroundJobState.FAILED,
                sourceScope="database",
                representation="physical_db_size_proxy",
                error="Database size estimate timed out before execution started.",
            )

        try:
            size_bytes = self.postgres.fetch_database_size_bytes(
                dsn,
                settings.postgres_connect_timeout_seconds,
            )
        except Exception as exc:
            return BackupSizeScopeEstimate(
                scope="database",
                label="Database backup estimate",
                state=BackgroundJobState.FAILED,
                sourceScope=settings.db_name or "current_database()",
                representation="physical_db_size_proxy",
                error=f"Database size estimate failed: {exc}",
            )

        return BackupSizeScopeEstimate(
            scope="database",
            label="Database backup estimate",
            state=BackgroundJobState.COMPLETED,
            sourceScope=settings.db_name or "current_database()",
            representation="physical_db_size_proxy",
            bytes=size_bytes,
            collectedAt=self.clock().isoformat(),
            durationSeconds=round(monotonic() - started_monotonic, 3),
            warnings=[
                "This number represents PostgreSQL physical database size, "
                "which is a proxy for backup volume and not an exact logical dump size."
            ],
        )

    def _collect_storage_scope(
        self,
        settings: AppSettings,
        *,
        deadline_monotonic: float,
        cancel_requested: Callable[[], bool] | None,
        progress_callback: ProgressCallback | None,
        job_id: str,
        started_at: datetime,
        scope_results: list[BackupSizeScopeEstimate],
    ) -> BackupSizeScopeEstimate:
        started_monotonic = monotonic()
        library_root = settings.immich_library_root
        if library_root is None:
            return BackupSizeScopeEstimate(
                scope="storage",
                label="Storage backup estimate",
                state=BackgroundJobState.UNSUPPORTED,
                sourceScope="immich_library_root",
                representation="filesystem_usage",
                warnings=[
                    "Storage size estimate is unavailable because "
                    "IMMICH library root is not configured."
                ],
            )

        directory_check = self.filesystem.validate_directory("immich_library_root", library_root)
        if directory_check.status.value != "pass":
            return BackupSizeScopeEstimate(
                scope="storage",
                label="Storage backup estimate",
                state=BackgroundJobState.FAILED,
                sourceScope=library_root.as_posix(),
                representation="filesystem_usage",
                error=directory_check.message,
            )

        category_map = self._category_path_map(settings)
        category_totals: dict[str, int] = {name: 0 for name in category_map}
        category_files: dict[str, int] = {name: 0 for name in category_map}
        other_bytes = 0
        other_files = 0

        def handle_file(path, size):  # type: ignore[no-untyped-def]
            nonlocal other_bytes, other_files
            category_name = self._categorize_path(path.as_posix(), category_map)
            if category_name is None:
                other_bytes += size
                other_files += 1
                return
            category_totals[category_name] += size
            category_files[category_name] += 1

        def handle_progress(progress: dict[str, object]) -> None:
            self._emit(
                self._build_snapshot(
                    job_id=job_id,
                    started_at=started_at,
                    scope_results=scope_results + [self._running_storage_placeholder()],
                    progress=BackupSizeProgress(
                        scope="storage",
                        message=str(progress["message"]),
                        current=int(progress["current"]),
                        unit=str(progress["unit"]),
                        currentPath=str(progress["current_path"]),
                    ),
                ),
                progress_callback,
            )

        try:
            usage = self.filesystem.scan_directory_usage(
                library_root,
                on_file=handle_file,
                on_progress=handle_progress,
                cancel_requested=cancel_requested,
                deadline_monotonic=deadline_monotonic,
            )
        except DirectoryScanCanceledError:
            return BackupSizeScopeEstimate(
                scope="storage",
                label="Storage backup estimate",
                state=BackgroundJobState.CANCELED,
                sourceScope=library_root.as_posix(),
                representation="filesystem_usage",
                error="Storage size collection was canceled.",
            )
        except DirectoryScanTimeoutError:
            return BackupSizeScopeEstimate(
                scope="storage",
                label="Storage backup estimate",
                state=BackgroundJobState.FAILED,
                sourceScope=library_root.as_posix(),
                representation="filesystem_usage",
                error="Storage size collection timed out.",
            )

        categories = [
            BackupSizeCategory(
                name=name,
                label=label,
                path=path,
                bytes=category_totals[name],
                fileCount=category_files[name],
            )
            for name, (label, path) in ((name, category_map[name]) for name in category_map)
        ]
        categories.append(
            BackupSizeCategory(
                name="other",
                label="Other",
                path=library_root.as_posix(),
                bytes=other_bytes,
                fileCount=other_files,
            )
        )

        warnings: list[str] = []
        state = BackgroundJobState.COMPLETED
        if usage.error_count:
            state = BackgroundJobState.PARTIAL
            warnings.append(
                "Storage scan completed with "
                f"{usage.error_count} unreadable or unsupported entries."
            )

        return BackupSizeScopeEstimate(
            scope="storage",
            label="Storage backup estimate",
            state=state,
            sourceScope=library_root.as_posix(),
            representation="filesystem_usage",
            bytes=usage.total_bytes,
            fileCount=usage.file_count,
            collectedAt=self.clock().isoformat(),
            durationSeconds=round(monotonic() - started_monotonic, 3),
            categories=categories,
            warnings=warnings,
            metadata={
                "directoryCount": usage.directory_count,
                "otherEntryCount": usage.other_entry_count,
                "errorCount": usage.error_count,
                "errorSamples": list(usage.error_samples),
            },
        )

    def _build_snapshot(
        self,
        *,
        job_id: str,
        started_at: datetime,
        scope_results: list[BackupSizeScopeEstimate],
        progress: BackupSizeProgress | None,
    ) -> BackupSizeEstimateSnapshot:
        finished_scopes = [
            scope
            for scope in scope_results
            if scope.state not in {BackgroundJobState.PENDING, BackgroundJobState.RUNNING}
        ]
        state = self._derive_overall_state(scope_results)
        return BackupSizeEstimateSnapshot(
            generatedAt=self.clock().isoformat(),
            jobId=job_id,
            state=state,
            summary=self._summary_for_state(state, scope_results),
            sourceScope="backup.files",
            collectedAt=self.clock().isoformat() if finished_scopes else None,
            durationSeconds=round((self.clock() - started_at).total_seconds(), 3)
            if finished_scopes
            else None,
            scopes=scope_results,
            progress=progress,
            warnings=[warning for scope in scope_results for warning in scope.warnings],
            limitations=[
                "Database size currently uses PostgreSQL physical size "
                "as a backup proxy, not a logical dump byte count.",
                "Storage size reflects the configured backup file source scope "
                "and does not claim restore readiness.",
                "Restore execution is not implemented by this estimate flow.",
            ],
        )

    def _derive_overall_state(
        self,
        scope_results: list[BackupSizeScopeEstimate],
    ) -> BackgroundJobState:
        states = {scope.state for scope in scope_results}
        if not scope_results or states == {BackgroundJobState.PENDING}:
            return BackgroundJobState.PENDING
        if BackgroundJobState.RUNNING in states:
            has_finished_data = any(state in states for state in TERMINAL_STATES_WITH_DATA)
            return BackgroundJobState.PARTIAL if has_finished_data else BackgroundJobState.RUNNING
        if states == {BackgroundJobState.UNSUPPORTED}:
            return BackgroundJobState.UNSUPPORTED
        if states == {BackgroundJobState.CANCELED}:
            return BackgroundJobState.CANCELED
        if states <= {BackgroundJobState.COMPLETED}:
            return BackgroundJobState.COMPLETED
        if states <= {BackgroundJobState.FAILED}:
            return BackgroundJobState.FAILED
        return BackgroundJobState.PARTIAL

    def _summary_for_state(
        self,
        state: BackgroundJobState,
        scope_results: list[BackupSizeScopeEstimate],
    ) -> str:
        if state == BackgroundJobState.PENDING:
            return "Backup size collection is pending."
        if state == BackgroundJobState.RUNNING:
            return "Backup size collection is running."
        if state == BackgroundJobState.COMPLETED:
            return "Backup size collection completed."
        if state == BackgroundJobState.UNSUPPORTED:
            return "Backup size collection is unsupported for the current configuration."
        if state == BackgroundJobState.CANCELED:
            return "Backup size collection was canceled."
        if state == BackgroundJobState.FAILED:
            return "Backup size collection failed."
        completed_scopes = [
            scope.label for scope in scope_results if scope.state == BackgroundJobState.COMPLETED
        ]
        if completed_scopes:
            scope_list = ", ".join(completed_scopes)
            return f"Backup size collection completed with partial data for: {scope_list}."
        return "Backup size collection completed with partial data."

    def _category_path_map(self, settings: AppSettings) -> dict[str, tuple[str, str]]:
        library_root = settings.immich_library_root
        if library_root is None:
            return {}

        configured = {
            "originals": ("Originals", settings.immich_uploads_path),
            "thumbs": ("Thumbs", settings.immich_thumbs_path),
            "profile": ("Profile", settings.immich_profile_path),
            "encoded": ("Encoded", settings.immich_video_path),
        }
        result: dict[str, tuple[str, str]] = {}
        for key, (label, path) in configured.items():
            if path is None:
                continue
            if self.filesystem.is_child_path(library_root, path):
                result[key] = (label, path.as_posix())
        return result

    def _categorize_path(
        self,
        file_path: str,
        category_map: dict[str, tuple[str, str]],
    ) -> str | None:
        for key, (_, prefix) in category_map.items():
            normalized_prefix = prefix.rstrip("/") + "/"
            if file_path.startswith(normalized_prefix):
                return key
        return None

    def _running_storage_placeholder(self) -> BackupSizeScopeEstimate:
        return BackupSizeScopeEstimate(
            scope="storage",
            label="Storage backup estimate",
            state=BackgroundJobState.RUNNING,
            sourceScope="immich_library_root",
            representation="filesystem_usage",
        )

    def _emit(
        self,
        snapshot: BackupSizeEstimateSnapshot,
        progress_callback: ProgressCallback | None,
    ) -> None:
        if progress_callback is not None:
            progress_callback(snapshot)
