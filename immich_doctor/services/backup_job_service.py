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
    stop_event: Event
    pause_event: Event

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
                "cancel_requested": self.stop_event.is_set(),
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
                "cancel_requested": self.stop_event.is_set(),
            }
        )
        self.record = self.store.persist_job(self.settings, updated)
        return self.record

    def request_pause(self) -> BackgroundJobRecord:
        self.pause_event.set()
        updated = self.record.model_copy(
            update={
                "state": BackgroundJobState.PAUSING,
                "summary": "Pause requested.",
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        self.record = self.store.persist_job(self.settings, updated)
        return self.record

    def request_resume(self) -> BackgroundJobRecord:
        self.pause_event.clear()
        updated = self.record.model_copy(
            update={
                "state": BackgroundJobState.RESUMING,
                "summary": "Resume requested.",
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        self.record = self.store.persist_job(self.settings, updated)
        return self.record

    def request_stop(self) -> BackgroundJobRecord:
        self.stop_event.set()
        updated = self.record.model_copy(
            update={
                "state": BackgroundJobState.STOPPING,
                "summary": "Stop requested.",
                "updated_at": datetime.now(UTC).isoformat(),
                "cancel_requested": True,
            }
        )
        self.record = self.store.persist_job(self.settings, updated)
        return self.record

    def request_cancel(self) -> BackgroundJobRecord:
        return self.request_stop()

    def cancel_requested(self) -> bool:
        return self.stop_event.is_set()

    def stop_requested(self) -> bool:
        return self.stop_event.is_set()

    def pause_requested(self) -> bool:
        return self.pause_event.is_set()


@dataclass(slots=True)
class BackgroundJobRuntime:
    store: BackgroundJobStore = field(default_factory=BackgroundJobStore)
    max_workers: int = 3
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    _executor: ThreadPoolExecutor = field(init=False, repr=False)
    _lock: Lock = field(init=False, repr=False)
    _active_jobs: dict[str, tuple[ManagedJobHandle, Future[None]]] = field(
        init=False,
        repr=False,
    )
    _capability_snapshots: dict[str, dict[str, object]] = field(
        init=False,
        repr=False,
    )
    _job_attachments: dict[str, object] = field(
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
        self._capability_snapshots = {}
        self._job_attachments = {}

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
            stop_event=Event(),
            pause_event=Event(),
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
        return self.request_stop(job_type=job_type)

    def request_pause(self, *, job_type: str) -> BackgroundJobRecord | None:
        with self._lock:
            active = self._active_jobs.get(job_type)
        if active is None:
            return None
        handle, _ = active
        return handle.request_pause()

    def request_resume(self, *, job_type: str) -> BackgroundJobRecord | None:
        with self._lock:
            active = self._active_jobs.get(job_type)
        if active is None:
            return None
        handle, _ = active
        return handle.request_resume()

    def request_stop(self, *, job_type: str) -> BackgroundJobRecord | None:
        with self._lock:
            active = self._active_jobs.get(job_type)
        if active is None:
            return None
        handle, _ = active
        return handle.request_stop()

    def set_capability_snapshot(self, name: str, snapshot: dict[str, object]) -> None:
        with self._lock:
            self._capability_snapshots[name] = dict(snapshot)

    def get_capability_snapshot(self, name: str) -> dict[str, object] | None:
        with self._lock:
            snapshot = self._capability_snapshots.get(name)
            return dict(snapshot) if snapshot is not None else None

    def set_job_attachment(self, *, job_type: str, attachment: object | None) -> None:
        with self._lock:
            if attachment is None:
                self._job_attachments.pop(job_type, None)
                return
            self._job_attachments[job_type] = attachment

    def get_job_attachment(self, *, job_type: str) -> object | None:
        with self._lock:
            return self._job_attachments.get(job_type)

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
                self._job_attachments.pop(handle.record.job_type, None)
