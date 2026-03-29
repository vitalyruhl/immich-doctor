from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any
from uuid import uuid4

from immich_doctor.consistency.missing_asset_models import (
    MissingAssetCompletedScanSummary,
    MissingAssetReferenceStatus,
    MissingAssetScanFailureKind,
    MissingAssetScanJob,
    MissingAssetScanState,
    MissingAssetScanStatusResult,
    RepairReadinessStatus,
)
from immich_doctor.consistency.missing_asset_scan_store import MissingAssetScanStore
from immich_doctor.consistency.missing_asset_service import MissingAssetReferenceService
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus


@dataclass(slots=True)
class MissingAssetScanManager:
    scanner: MissingAssetReferenceService = field(default_factory=MissingAssetReferenceService)
    store: MissingAssetScanStore = field(default_factory=MissingAssetScanStore)
    max_workers: int = 1
    _executor: ThreadPoolExecutor = field(init=False, repr=False)
    _lock: Lock = field(init=False, repr=False)
    _active_scan_id: str | None = field(init=False, default=None, repr=False)
    _active_future: Future[None] | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="missing-asset-scan",
        )
        self._lock = Lock()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)

    def reconcile(self, settings: AppSettings) -> MissingAssetScanJob | None:
        current = self.store.load_state(settings)
        if current is None:
            return None

        latest_completed = self.store.load_latest_completed_summary(settings)
        active_running = self._is_active_running(current.scan_id)

        if (
            current.state in {MissingAssetScanState.PENDING, MissingAssetScanState.RUNNING}
            and latest_completed is not None
            and latest_completed.scan_id == current.scan_id
        ):
            completed = self._job_copy(
                current,
                state=MissingAssetScanState.COMPLETED,
                summary=latest_completed.summary,
                updated_at=latest_completed.completed_at,
                finished_at=latest_completed.completed_at,
                result_count=latest_completed.finding_count,
                error_message=None,
                failure_kind=None,
            )
            return self.store.save_state(settings, completed)

        if (
            current.state in {MissingAssetScanState.PENDING, MissingAssetScanState.RUNNING}
            and not active_running
        ):
            failed = self._job_copy(
                current,
                state=MissingAssetScanState.FAILED,
                summary="Missing asset reference scan was interrupted before completion.",
                updated_at=self._now(),
                finished_at=self._now(),
                error_message="Scan was interrupted before completion.",
                failure_kind=MissingAssetScanFailureKind.INTERRUPTED,
            )
            return self.store.save_state(settings, failed)

        if current.state == MissingAssetScanState.COMPLETED and (
            latest_completed is None or latest_completed.scan_id != current.scan_id
        ):
            failed = self._job_copy(
                current,
                state=MissingAssetScanState.FAILED,
                summary="Missing asset reference scan completed without a durable result snapshot.",
                updated_at=self._now(),
                finished_at=self._now(),
                error_message="Completed scan snapshot is missing or incomplete.",
                failure_kind=MissingAssetScanFailureKind.INTERRUPTED,
            )
            return self.store.save_state(settings, failed)

        return current

    def get_status(self, settings: AppSettings) -> MissingAssetScanStatusResult:
        current = self.reconcile(settings)
        latest_completed = self.store.load_latest_completed_summary(settings)
        active_scan = (
            current
            if current is not None
            and current.state in {MissingAssetScanState.PENDING, MissingAssetScanState.RUNNING}
            else None
        )

        if active_scan is not None:
            summary = (
                "Missing asset reference scan is running. "
                f"Last completed scan from {latest_completed.completed_at} remains available."
                if latest_completed is not None
                else "Missing asset reference scan is running."
            )
            return MissingAssetScanStatusResult(
                summary=summary,
                scan_state=active_scan.state,
                active_scan=active_scan,
                latest_completed=latest_completed,
                metadata={
                    "has_completed_result": latest_completed is not None,
                },
                recommendations=[
                    "Refresh findings after the active scan completes to load the next result set."
                ],
            )

        if current is not None and current.state == MissingAssetScanState.FAILED:
            summary = (
                "Missing asset reference scan failed. "
                f"Last completed scan from {latest_completed.completed_at} remains available."
                if latest_completed is not None
                else "Missing asset reference scan failed."
            )
            return MissingAssetScanStatusResult(
                summary=summary,
                scan_state=MissingAssetScanState.FAILED,
                active_scan=current,
                latest_completed=latest_completed,
                checks=[
                    CheckResult(
                        name="missing_asset_scan_job",
                        status=CheckStatus.FAIL,
                        message=current.error_message or current.summary,
                        details={
                            "failure_kind": (
                                current.failure_kind.value
                                if current.failure_kind is not None
                                else None
                            ),
                        },
                    )
                ],
                metadata={"has_completed_result": latest_completed is not None},
                recommendations=["Inspect the failure details before retrying the scan."],
            )

        if latest_completed is not None:
            return MissingAssetScanStatusResult(
                summary=latest_completed.summary,
                scan_state=MissingAssetScanState.COMPLETED,
                latest_completed=latest_completed,
                metadata={"has_completed_result": True},
            )

        return MissingAssetScanStatusResult(
            summary="No completed missing asset reference scan is available yet.",
            scan_state=MissingAssetScanState.IDLE,
            metadata={"has_completed_result": False},
            recommendations=["Trigger an initial scan to populate findings."],
        )

    def start_scan(self, settings: AppSettings) -> MissingAssetScanStatusResult:
        self.reconcile(settings)
        already_running = False
        with self._lock:
            if self._active_future is not None and not self._active_future.done():
                already_running = True
            else:
                requested_at = self._now()
                job = MissingAssetScanJob(
                    scan_id=uuid4().hex,
                    state=MissingAssetScanState.PENDING,
                    requested_at=requested_at,
                    updated_at=requested_at,
                    summary="Missing asset reference scan is queued.",
                )
                self.store.save_state(settings, job)
                self._active_scan_id = job.scan_id
                self._active_future = self._executor.submit(self._run_scan, settings, job)

        if already_running:
            return self.get_status(settings)

        return self.get_status(settings)

    def get_latest_findings(
        self,
        settings: AppSettings,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict[str, Any]:
        status = self.get_status(settings)
        snapshot = self.store.load_latest_completed_snapshot(settings)
        latest_completed = self.store.load_latest_completed_summary(settings)
        if snapshot is None or latest_completed is None:
            return {
                "domain": "consistency.missing_asset_references",
                "action": "scan",
                "status": "SKIP",
                "summary": "No completed missing asset reference scan is available yet.",
                "generated_at": self._now(),
                "checks": [],
                "findings": [],
                "metadata": {
                    "scan_state": status.scan_state.value,
                    "active_scan": (
                        status.active_scan.to_dict() if status.active_scan is not None else None
                    ),
                    "latest_completed": None,
                    "has_completed_result": False,
                    "limit": limit,
                    "offset": offset,
                    "total_findings": 0,
                },
                "recommendations": ["Trigger an initial scan to populate findings."],
            }

        payload = deepcopy(snapshot)
        findings = list(payload.get("findings", []))
        total_findings = len(findings)
        sliced_findings = findings[offset:] if limit is None else findings[offset : offset + limit]
        metadata = dict(payload.get("metadata", {}))
        metadata.update(
            {
                "scan_state": status.scan_state.value,
                "active_scan": (
                    status.active_scan.to_dict() if status.active_scan is not None else None
                ),
                "latest_completed": latest_completed.to_dict(),
                "has_completed_result": True,
                "limit": limit,
                "offset": offset,
                "total_findings": total_findings,
                "returned_findings": len(sliced_findings),
            }
        )
        payload["findings"] = sliced_findings
        payload["metadata"] = metadata
        return payload

    def _run_scan(self, settings: AppSettings, job: MissingAssetScanJob) -> None:
        running = self._job_copy(
            job,
            state=MissingAssetScanState.RUNNING,
            summary="Missing asset reference scan is running.",
            updated_at=self._now(),
            started_at=self._now(),
        )
        self.store.save_state(settings, running)

        try:
            result = self.scanner.scan_all(
                settings,
                progress_callback=lambda progress: self._handle_progress(
                    settings,
                    scan_id=running.scan_id,
                    progress=progress,
                ),
            )
            completed_at = self._now()
            snapshot = result.to_dict()
            completed_summary = self._build_completed_summary(
                scan_id=running.scan_id,
                completed_at=completed_at,
                snapshot=snapshot,
            )
            self.store.save_latest_completed(
                settings,
                summary=completed_summary,
                snapshot=snapshot,
            )
            self.store.save_state(
                settings,
                self._job_copy(
                    running,
                    state=MissingAssetScanState.COMPLETED,
                    summary=completed_summary.summary,
                    updated_at=completed_at,
                    finished_at=completed_at,
                    result_count=completed_summary.finding_count,
                    scanned_asset_count=int(
                        snapshot.get("metadata", {}).get("scannedAssetCount")
                        or completed_summary.finding_count
                    ),
                    error_message=None,
                    failure_kind=None,
                ),
            )
        except Exception as exc:
            finished_at = self._now()
            self.store.save_state(
                settings,
                self._job_copy(
                    running,
                    state=MissingAssetScanState.FAILED,
                    summary="Missing asset reference scan failed.",
                    updated_at=finished_at,
                    finished_at=finished_at,
                    error_message=str(exc),
                    failure_kind=MissingAssetScanFailureKind.EXCEPTION,
                ),
            )
        finally:
            with self._lock:
                if self._active_scan_id == job.scan_id:
                    self._active_scan_id = None
                    self._active_future = None

    def _handle_progress(
        self,
        settings: AppSettings,
        *,
        scan_id: str,
        progress: dict[str, Any],
    ) -> None:
        current = self.store.load_state(settings)
        if current is None or current.scan_id != scan_id:
            return
        if current.state not in {MissingAssetScanState.PENDING, MissingAssetScanState.RUNNING}:
            return

        scanned_asset_count = int(progress.get("scanned_asset_count") or 0)
        result_count = int(progress.get("finding_count") or 0)
        summary = (
            f"Missing asset reference scan is running. "
            f"{scanned_asset_count} assets checked, {result_count} findings captured so far."
        )
        updated = self._job_copy(
            current,
            state=MissingAssetScanState.RUNNING,
            summary=summary,
            updated_at=self._now(),
            scanned_asset_count=scanned_asset_count,
            result_count=result_count,
        )
        self.store.save_state(settings, updated)

    def _build_completed_summary(
        self,
        *,
        scan_id: str,
        completed_at: str,
        snapshot: dict[str, Any],
    ) -> MissingAssetCompletedScanSummary:
        findings = list(snapshot.get("findings", []))
        missing_on_disk_count = sum(
            1
            for finding in findings
            if finding.get("status") == MissingAssetReferenceStatus.MISSING_ON_DISK.value
        )
        ready_count = sum(
            1
            for finding in findings
            if finding.get("repair_readiness") == RepairReadinessStatus.READY.value
        )
        blocked_count = sum(
            1
            for finding in findings
            if finding.get("repair_readiness") == RepairReadinessStatus.BLOCKED.value
        )
        return MissingAssetCompletedScanSummary(
            scan_id=scan_id,
            status=str(snapshot.get("status") or "PASS"),
            summary=str(snapshot.get("summary") or "Missing asset reference scan completed."),
            generated_at=str(snapshot.get("generated_at") or completed_at),
            completed_at=completed_at,
            finding_count=len(findings),
            missing_on_disk_count=missing_on_disk_count,
            ready_count=ready_count,
            blocked_count=blocked_count,
        )

    def _is_active_running(self, scan_id: str) -> bool:
        with self._lock:
            if self._active_scan_id != scan_id or self._active_future is None:
                return False
            return not self._active_future.done()

    def _job_copy(
        self,
        job: MissingAssetScanJob,
        *,
        state: MissingAssetScanState,
        summary: str,
        updated_at: str,
        started_at: str | None | None = None,
        finished_at: str | None | None = None,
        result_count: int | None = None,
        scanned_asset_count: int | None = None,
        error_message: str | None = None,
        failure_kind: MissingAssetScanFailureKind | None = None,
    ) -> MissingAssetScanJob:
        return MissingAssetScanJob(
            scan_id=job.scan_id,
            state=state,
            requested_at=job.requested_at,
            updated_at=updated_at,
            started_at=job.started_at if started_at is None else started_at,
            finished_at=job.finished_at if finished_at is None else finished_at,
            summary=summary,
            result_count=job.result_count if result_count is None else result_count,
            scanned_asset_count=(
                job.scanned_asset_count if scanned_asset_count is None else scanned_asset_count
            ),
            error_message=error_message,
            failure_kind=failure_kind,
        )

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()
