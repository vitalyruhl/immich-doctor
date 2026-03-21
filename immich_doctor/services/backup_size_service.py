from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.backup.core.job_models import (
    TERMINAL_BACKGROUND_JOB_STATES,
    BackgroundJobState,
)
from immich_doctor.backup.estimation.models import BackupSizeEstimateSnapshot
from immich_doctor.backup.estimation.service import BackupSizeCollector
from immich_doctor.core.config import AppSettings
from immich_doctor.services.backup_job_service import BackgroundJobRuntime, ManagedJobHandle

BACKUP_SIZE_JOB_TYPE = "backup_size_collection"


@dataclass(slots=True)
class BackupSizeEstimationService:
    runtime: BackgroundJobRuntime
    collector: BackupSizeCollector = field(default_factory=BackupSizeCollector)

    def get_snapshot(self, settings: AppSettings) -> BackupSizeEstimateSnapshot:
        active = self.runtime.active_job(job_type=BACKUP_SIZE_JOB_TYPE)
        if active is not None:
            snapshot = BackupSizeEstimateSnapshot.model_validate(active.result)
            if snapshot.job_id is None:
                snapshot = snapshot.model_copy(update={"job_id": active.job_id})
            return self.collector.apply_freshness(
                snapshot,
                runtime_started_at=self.runtime.started_at,
            )

        latest = self.runtime.store.find_latest_job(
            settings,
            job_type=BACKUP_SIZE_JOB_TYPE,
            states=set(TERMINAL_BACKGROUND_JOB_STATES),
        )
        if latest is None:
            return self.collector.pending_snapshot()

        return self.collector.apply_freshness(
            BackupSizeEstimateSnapshot.model_validate(latest.result),
            runtime_started_at=self.runtime.started_at,
        )

    def collect(
        self,
        settings: AppSettings,
        *,
        force: bool = False,
    ) -> BackupSizeEstimateSnapshot:
        active = self.runtime.active_job(job_type=BACKUP_SIZE_JOB_TYPE)
        if active is not None:
            snapshot = BackupSizeEstimateSnapshot.model_validate(active.result)
            if snapshot.job_id is None:
                snapshot = snapshot.model_copy(update={"job_id": active.job_id})
            return self.collector.apply_freshness(
                snapshot,
                runtime_started_at=self.runtime.started_at,
            )

        latest = self.runtime.store.find_latest_job(
            settings,
            job_type=BACKUP_SIZE_JOB_TYPE,
            states={
                BackgroundJobState.PARTIAL,
                BackgroundJobState.COMPLETED,
                BackgroundJobState.UNSUPPORTED,
            },
        )
        latest_snapshot: BackupSizeEstimateSnapshot | None = None
        if latest is not None and not force:
            latest_snapshot = self.collector.apply_freshness(
                BackupSizeEstimateSnapshot.model_validate(latest.result),
                runtime_started_at=self.runtime.started_at,
            )
            if not latest_snapshot.stale:
                return latest_snapshot
        elif latest is not None:
            latest_snapshot = self.collector.apply_freshness(
                BackupSizeEstimateSnapshot.model_validate(latest.result),
                runtime_started_at=self.runtime.started_at,
            )

        stale_reason = (
            latest_snapshot.stale_reason
            if latest_snapshot is not None and latest_snapshot.stale_reason is not None
            else "refresh_requested"
        )
        initial_snapshot = self.collector.queued_snapshot(
            previous_snapshot=latest_snapshot,
            stale_reason=stale_reason,
        )
        record = self.runtime.start_job(
            settings,
            job_type=BACKUP_SIZE_JOB_TYPE,
            initial_result=initial_snapshot.model_dump(by_alias=True, mode="json"),
            summary=initial_snapshot.summary,
            runner=lambda handle: self._run_collection(handle, previous_snapshot=latest_snapshot),
        )
        return initial_snapshot.model_copy(update={"job_id": record.job_id})

    def trigger_startup_refresh(self, settings: AppSettings) -> BackupSizeEstimateSnapshot:
        return self.collect(settings, force=False)

    def request_cancel(self) -> BackupSizeEstimateSnapshot | None:
        record = self.runtime.request_cancel(job_type=BACKUP_SIZE_JOB_TYPE)
        if record is None:
            return None
        return BackupSizeEstimateSnapshot.model_validate(record.result)

    def _run_collection(
        self,
        handle: ManagedJobHandle,
        *,
        previous_snapshot: BackupSizeEstimateSnapshot | None,
    ) -> dict[str, object]:
        result = self.collector.collect(
            handle.settings,
            job_id=handle.record.job_id,
            previous_snapshot=previous_snapshot,
            progress_callback=lambda snapshot: handle.update(
                state=snapshot.state,
                summary=snapshot.summary,
                result=snapshot.model_dump(by_alias=True, mode="json"),
            ),
            cancel_requested=handle.cancel_requested,
        )
        return result.model_dump(by_alias=True, mode="json")
