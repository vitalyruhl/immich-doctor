from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Event, Lock
from uuid import uuid4

from immich_doctor.backup.core.job_models import BackgroundJobRecord, BackgroundJobState
from immich_doctor.backup.core.job_store import BackgroundJobStore
from immich_doctor.core.config import AppSettings


@dataclass(slots=True)
class ManagedJobHandle:
    settings: AppSettings
    store: BackgroundJobStore
    record: BackgroundJobRecord
    cancel_event: Event

    def update(
        self,
        *,
        state: BackgroundJobState,
        summary: str,
        result: dict[str, object],
        error: str | None = None,
    ) -> BackgroundJobRecord:
        updated = self.record.model_copy(
            update={
                "state": state,
                "summary": summary,
                "updated_at": datetime.now(UTC).isoformat(),
                "result": result,
                "error": error,
                "cancel_requested": self.cancel_event.is_set(),
            }
        )
        self.record = self.store.persist_job(self.settings, updated)
        return self.record

    def mark_started(self) -> BackgroundJobRecord:
        started_at = datetime.now(UTC).isoformat()
        updated = self.record.model_copy(
            update={
                "state": BackgroundJobState.RUNNING,
                "started_at": started_at,
                "updated_at": started_at,
            }
        )
        self.record = self.store.persist_job(self.settings, updated)
        return self.record

    def mark_finished(
        self,
        *,
        state: BackgroundJobState,
        summary: str,
        result: dict[str, object],
        error: str | None = None,
    ) -> BackgroundJobRecord:
        completed_at = datetime.now(UTC).isoformat()
        updated = self.record.model_copy(
            update={
                "state": state,
                "summary": summary,
                "updated_at": completed_at,
                "completed_at": completed_at,
                "result": result,
                "error": error,
                "cancel_requested": self.cancel_event.is_set(),
            }
        )
        self.record = self.store.persist_job(self.settings, updated)
        return self.record

    def request_cancel(self) -> BackgroundJobRecord:
        self.cancel_event.set()
        updated = self.record.model_copy(
            update={
                "state": BackgroundJobState.CANCEL_REQUESTED,
                "summary": "Cancellation requested.",
                "updated_at": datetime.now(UTC).isoformat(),
                "cancel_requested": True,
            }
        )
        self.record = self.store.persist_job(self.settings, updated)
        return self.record

    def cancel_requested(self) -> bool:
        return self.cancel_event.is_set()


@dataclass(slots=True)
class BackgroundJobRuntime:
    store: BackgroundJobStore = field(default_factory=BackgroundJobStore)
    max_workers: int = 3
    _executor: ThreadPoolExecutor = field(init=False, repr=False)
    _lock: Lock = field(init=False, repr=False)
    _active_jobs: dict[str, tuple[ManagedJobHandle, Future[None]]] = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="backup-job",
        )
        self._lock = Lock()
        self._active_jobs: dict[str, tuple[ManagedJobHandle, Future[None]]] = {}

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)

    def start_job(
        self,
        settings: AppSettings,
        *,
        job_type: str,
        initial_result: dict[str, object],
        summary: str,
        runner: Callable[[ManagedJobHandle], dict[str, object]],
    ) -> BackgroundJobRecord:
        job_id = uuid4().hex
        record = BackgroundJobRecord(
            jobId=job_id,
            jobType=job_type,
            state=BackgroundJobState.PENDING,
            summary=summary,
            result=initial_result,
        )
        persisted_record = self.store.persist_job(settings, record)
        handle = ManagedJobHandle(
            settings=settings,
            store=self.store,
            record=persisted_record,
            cancel_event=Event(),
        )
        future = self._executor.submit(self._run_job, handle, runner)
        with self._lock:
            self._active_jobs[job_type] = (handle, future)
        return persisted_record

    def active_job(self, *, job_type: str) -> BackgroundJobRecord | None:
        with self._lock:
            active = self._active_jobs.get(job_type)
            if active is None:
                return None
            handle, future = active
            if future.done():
                self._active_jobs.pop(job_type, None)
            return handle.record

    def request_cancel(self, *, job_type: str) -> BackgroundJobRecord | None:
        with self._lock:
            active = self._active_jobs.get(job_type)
        if active is None:
            return None
        handle, _ = active
        return handle.request_cancel()

    def _run_job(
        self,
        handle: ManagedJobHandle,
        runner: Callable[[ManagedJobHandle], dict[str, object]],
    ) -> None:
        handle.mark_started()
        try:
            result = runner(handle)
            handle.mark_finished(
                state=BackgroundJobState(result["state"]),
                summary=str(result["summary"]),
                result=result,
            )
        except Exception as exc:
            failed_result = dict(handle.record.result)
            failed_result["state"] = BackgroundJobState.FAILED.value
            failed_result["summary"] = "Background job failed."
            failed_result["error"] = str(exc)
            handle.mark_finished(
                state=BackgroundJobState.FAILED,
                summary="Background job failed.",
                result=failed_result,
                error=str(exc),
            )
        finally:
            with self._lock:
                active = self._active_jobs.get(handle.record.job_type)
                if active is not None and active[0].record.job_id == handle.record.job_id:
                    self._active_jobs.pop(handle.record.job_type, None)
