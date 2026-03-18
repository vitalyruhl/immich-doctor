from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from immich_doctor.backup.core.job_models import BackgroundJobRecord, BackgroundJobState
from immich_doctor.backup.estimation.models import (
    BackupSizeEstimateSnapshot,
    BackupSizeProgress,
    BackupSizeScopeEstimate,
)
from immich_doctor.backup.estimation.service import BackupSizeCollector
from immich_doctor.core.config import AppSettings
from immich_doctor.services.backup_job_service import BackgroundJobRuntime
from immich_doctor.services.backup_size_service import (
    BACKUP_SIZE_JOB_TYPE,
    BackupSizeEstimationService,
)


def test_backup_size_collector_reports_partial_results_when_db_is_unsupported(
    tmp_path: Path,
) -> None:
    library_root = tmp_path / "library"
    uploads = library_root / "uploads"
    thumbs = library_root / "thumbs"
    uploads.mkdir(parents=True)
    thumbs.mkdir(parents=True)
    (uploads / "asset-1.jpg").write_bytes(b"a" * 10)
    (thumbs / "asset-1.webp").write_bytes(b"b" * 5)

    settings = AppSettings(
        _env_file=None,
        immich_library_root=library_root,
        immich_uploads_path=uploads,
        immich_thumbs_path=thumbs,
    )

    snapshot = BackupSizeCollector().collect(settings, job_id="job-1")

    assert snapshot.state == BackgroundJobState.PARTIAL
    assert snapshot.scopes[0].scope == "database"
    assert snapshot.scopes[0].state == BackgroundJobState.UNSUPPORTED
    assert snapshot.scopes[1].scope == "storage"
    assert snapshot.scopes[1].state == BackgroundJobState.COMPLETED
    assert snapshot.scopes[1].bytes == 15
    categories = {item.name: item.bytes for item in snapshot.scopes[1].categories}
    assert categories["originals"] == 10
    assert categories["thumbs"] == 5


def test_backup_size_service_reuses_fresh_cached_snapshot(tmp_path: Path) -> None:
    runtime = BackgroundJobRuntime()
    try:
        settings = AppSettings(_env_file=None, manifests_path=tmp_path / "manifests")
        cached_snapshot = BackupSizeEstimateSnapshot(
            generatedAt=datetime(2026, 3, 18, 12, 0, tzinfo=UTC).isoformat(),
            jobId="cached-job",
            state=BackgroundJobState.COMPLETED,
            summary="Backup size collection completed.",
            sourceScope="backup.files",
            collectedAt=datetime(2026, 3, 18, 12, 0, tzinfo=UTC).isoformat(),
            scopes=[
                BackupSizeScopeEstimate(
                    scope="database",
                    label="Database backup estimate",
                    state=BackgroundJobState.COMPLETED,
                    sourceScope="immich",
                    representation="physical_db_size_proxy",
                    bytes=123,
                )
            ],
        )
        runtime.store.persist_job(
            settings,
            BackgroundJobRecord(
                jobId="cached-job",
                jobType=BACKUP_SIZE_JOB_TYPE,
                state=BackgroundJobState.COMPLETED,
                summary=cached_snapshot.summary,
                createdAt=cached_snapshot.generated_at,
                updatedAt=cached_snapshot.generated_at,
                completedAt=cached_snapshot.generated_at,
                result=cached_snapshot.model_dump(by_alias=True, mode="json"),
            ),
        )

        service = BackupSizeEstimationService(
            runtime=runtime,
            collector=BackupSizeCollector(
                clock=lambda: datetime(2026, 3, 18, 12, 30, tzinfo=UTC)
            ),
        )
        result = service.collect(settings)

        assert result.job_id == "cached-job"
        assert runtime.active_job(job_type=BACKUP_SIZE_JOB_TYPE) is None
    finally:
        runtime.shutdown()


def test_backup_size_service_persists_background_progress(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, manifests_path=tmp_path / "manifests")

    class FakeCollector:
        def pending_snapshot(self, *, job_id: str | None = None) -> BackupSizeEstimateSnapshot:
            return BackupSizeEstimateSnapshot(
                generatedAt=datetime.now(UTC).isoformat(),
                jobId=job_id,
                state=BackgroundJobState.PENDING,
                summary="Backup size collection is pending.",
                sourceScope="backup.files",
            )

        def apply_freshness(
            self,
            snapshot: BackupSizeEstimateSnapshot,
        ) -> BackupSizeEstimateSnapshot:
            return snapshot

        def collect(
            self,
            _settings: AppSettings,
            *,
            job_id: str,
            progress_callback,
            cancel_requested,
        ) -> BackupSizeEstimateSnapshot:
            del _settings, cancel_requested
            progress_callback(
                BackupSizeEstimateSnapshot(
                    generatedAt=datetime.now(UTC).isoformat(),
                    jobId=job_id,
                    state=BackgroundJobState.RUNNING,
                    summary="Backup size collection is running.",
                    sourceScope="backup.files",
                    progress=BackupSizeProgress(
                        scope="storage",
                        message="Backup size collection is running.",
                        current=1,
                        unit="files",
                    ),
                )
            )
            return BackupSizeEstimateSnapshot(
                generatedAt=datetime.now(UTC).isoformat(),
                jobId=job_id,
                state=BackgroundJobState.COMPLETED,
                summary="Backup size collection completed.",
                sourceScope="backup.files",
                collectedAt=datetime.now(UTC).isoformat(),
            )

    runtime = BackgroundJobRuntime()
    try:
        service = BackupSizeEstimationService(runtime=runtime, collector=FakeCollector())
        started = service.collect(settings, force=True)

        assert started.state == BackgroundJobState.PENDING
        deadline = time.monotonic() + 5
        while runtime.active_job(job_type=BACKUP_SIZE_JOB_TYPE) is not None:
            assert time.monotonic() < deadline
            time.sleep(0.05)

        latest = service.get_snapshot(settings)
        assert latest.state == BackgroundJobState.COMPLETED
        assert latest.summary == "Backup size collection completed."
    finally:
        runtime.shutdown()


def test_backup_size_collector_marks_stale_snapshots() -> None:
    collector = BackupSizeCollector(clock=lambda: datetime(2026, 3, 18, 13, 30, tzinfo=UTC))
    snapshot = BackupSizeEstimateSnapshot(
        generatedAt=datetime(2026, 3, 18, 12, 0, tzinfo=UTC).isoformat(),
        jobId="job-1",
        state=BackgroundJobState.COMPLETED,
        summary="Backup size collection completed.",
        sourceScope="backup.files",
        collectedAt=(datetime(2026, 3, 18, 12, 0, tzinfo=UTC) - timedelta(hours=2)).isoformat(),
    )

    freshened = collector.apply_freshness(snapshot)

    assert freshened.stale is True
    assert freshened.cache_age_seconds is not None
