from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from immich_doctor.backup.core.job_models import (
    TERMINAL_BACKGROUND_JOB_STATES,
    BackgroundJobRecord,
    BackgroundJobState,
)
from immich_doctor.catalog.consistency_service import CatalogConsistencyValidationService
from immich_doctor.catalog.service import CatalogInventoryScanService, CatalogRootRegistry
from immich_doctor.catalog.store import CatalogStore
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckStatus
from immich_doctor.services.backup_job_service import BackgroundJobRuntime, ManagedJobHandle

logger = logging.getLogger(__name__)

CATALOG_SCAN_JOB_TYPE = "catalog_inventory_scan"
CATALOG_CONSISTENCY_JOB_TYPE = "catalog_consistency_validation"
_REQUIRED_CONSISTENCY_ROOT = "uploads"


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _record_to_payload(record: BackgroundJobRecord) -> dict[str, object]:
    return record.model_dump(by_alias=True, mode="json")


@dataclass(slots=True)
class CatalogWorkflowService:
    runtime: BackgroundJobRuntime
    registry: CatalogRootRegistry = field(default_factory=CatalogRootRegistry)
    store: CatalogStore = field(default_factory=CatalogStore)
    scan_service: CatalogInventoryScanService = field(default_factory=CatalogInventoryScanService)
    consistency_service: CatalogConsistencyValidationService = field(
        default_factory=CatalogConsistencyValidationService
    )

    def get_scan_job(self, settings: AppSettings) -> dict[str, object]:
        active = self.runtime.active_job(job_type=CATALOG_SCAN_JOB_TYPE)
        if active is not None:
            return _record_to_payload(active)
        latest = self.runtime.store.find_latest_job(
            settings,
            job_type=CATALOG_SCAN_JOB_TYPE,
            states=set(TERMINAL_BACKGROUND_JOB_STATES),
        )
        if latest is not None:
            return _record_to_payload(latest)
        return self._pending_snapshot(
            job_type=CATALOG_SCAN_JOB_TYPE,
            summary="No catalog scan has been started yet.",
        )

    def start_scan(self, settings: AppSettings, *, force: bool) -> dict[str, object]:
        active_consistency = self.runtime.active_job(job_type=CATALOG_CONSISTENCY_JOB_TYPE)
        if active_consistency is not None:
            return self._blocked_snapshot(
                job_type=CATALOG_SCAN_JOB_TYPE,
                summary="Catalog scan is blocked while catalog consistency validation is running.",
                blocked_by=active_consistency,
            )

        active_scan = self.runtime.active_job(job_type=CATALOG_SCAN_JOB_TYPE)
        if active_scan is not None:
            return _record_to_payload(active_scan)

        latest_scan = self.runtime.store.find_latest_job(
            settings,
            job_type=CATALOG_SCAN_JOB_TYPE,
            states=set(TERMINAL_BACKGROUND_JOB_STATES),
        )
        if latest_scan is not None and not force and self._has_required_catalog_snapshot(settings):
            return _record_to_payload(latest_scan)

        initial_result = {
            "state": BackgroundJobState.PENDING.value,
            "summary": "Catalog scan queued.",
            "progress": {
                "phase": "queued",
                "current": 0,
                "total": 0,
                "percent": 0.0,
                "message": "Waiting for the catalog scan worker to start.",
            },
        }
        record = self.runtime.start_job(
            settings,
            job_type=CATALOG_SCAN_JOB_TYPE,
            initial_result=initial_result,
            summary="Catalog scan queued.",
            runner=self._run_scan_job,
        )
        logger.info("Catalog scan job queued: job_id=%s", record.job_id)
        return _record_to_payload(record)

    def get_consistency_job(self, settings: AppSettings) -> dict[str, object]:
        active = self.runtime.active_job(job_type=CATALOG_CONSISTENCY_JOB_TYPE)
        if active is not None:
            return _record_to_payload(active)
        active_scan = self.runtime.active_job(job_type=CATALOG_SCAN_JOB_TYPE)
        if active_scan is not None:
            return self._blocked_snapshot(
                job_type=CATALOG_CONSISTENCY_JOB_TYPE,
                summary="Catalog consistency validation is waiting for the catalog scan to finish.",
                blocked_by=active_scan,
            )
        latest = self.runtime.store.find_latest_job(
            settings,
            job_type=CATALOG_CONSISTENCY_JOB_TYPE,
            states=set(TERMINAL_BACKGROUND_JOB_STATES),
        )
        if latest is not None:
            return _record_to_payload(latest)
        if not self._has_required_catalog_snapshot(settings):
            return self._pending_snapshot(
                job_type=CATALOG_CONSISTENCY_JOB_TYPE,
                summary="Catalog consistency is waiting for a committed catalog scan.",
                result={"requiresScan": True},
            )
        return self._pending_snapshot(
            job_type=CATALOG_CONSISTENCY_JOB_TYPE,
            summary="No catalog consistency validation has been started yet.",
        )

    def start_consistency(self, settings: AppSettings, *, force: bool) -> dict[str, object]:
        active_scan = self.runtime.active_job(job_type=CATALOG_SCAN_JOB_TYPE)
        if active_scan is not None:
            return self._blocked_snapshot(
                job_type=CATALOG_CONSISTENCY_JOB_TYPE,
                summary=(
                    "Catalog consistency validation is blocked while the catalog scan is running."
                ),
                blocked_by=active_scan,
            )

        active_consistency = self.runtime.active_job(job_type=CATALOG_CONSISTENCY_JOB_TYPE)
        if active_consistency is not None:
            return _record_to_payload(active_consistency)

        if not self._has_required_catalog_snapshot(settings):
            scan_snapshot = self.start_scan(settings, force=True)
            return self._pending_snapshot(
                job_type=CATALOG_CONSISTENCY_JOB_TYPE,
                summary=(
                    "Catalog consistency validation is waiting for the first "
                    "committed catalog scan."
                ),
                result={"requiresScan": True, "blockedBy": scan_snapshot},
            )

        latest_consistency = self.runtime.store.find_latest_job(
            settings,
            job_type=CATALOG_CONSISTENCY_JOB_TYPE,
            states=set(TERMINAL_BACKGROUND_JOB_STATES),
        )
        if latest_consistency is not None and not force:
            return _record_to_payload(latest_consistency)

        initial_result = {
            "state": BackgroundJobState.PENDING.value,
            "summary": "Catalog consistency validation queued.",
            "progress": {
                "phase": "queued",
                "current": 0,
                "total": 0,
                "percent": 0.0,
                "message": "Waiting for the catalog consistency worker to start.",
            },
        }
        record = self.runtime.start_job(
            settings,
            job_type=CATALOG_CONSISTENCY_JOB_TYPE,
            initial_result=initial_result,
            summary="Catalog consistency validation queued.",
            runner=self._run_consistency_job,
        )
        logger.info("Catalog consistency job queued: job_id=%s", record.job_id)
        return _record_to_payload(record)

    def _run_scan_job(self, handle: ManagedJobHandle) -> dict[str, object]:
        roots = self.registry.scan_roots(handle.settings)
        if not roots:
            return {
                "state": BackgroundJobState.FAILED.value,
                "summary": "Catalog scan failed because no storage roots are configured.",
                "progress": {"phase": "failed", "current": 0, "total": 0, "percent": 0.0},
            }

        reports: list[dict[str, object]] = []
        root_count = len(roots)
        worst_state = BackgroundJobState.COMPLETED
        for index, root in enumerate(roots, start=1):
            logger.info(
                "Catalog scan job %s starting root %s (%s/%s)",
                handle.record.job_id,
                root.slug,
                index,
                root_count,
            )
            report = self.scan_service.run(
                handle.settings,
                root_slug=root.slug,
                resume_session_id=None,
                max_files=None,
                progress_callback=(
                    lambda payload, root_index=index, total_roots=root_count, slug=root.slug: (
                        self._update_scan_progress(
                            handle,
                            payload=payload,
                            root_slug=slug,
                            root_index=root_index,
                            total_roots=total_roots,
                            completed_roots=[item["rootSlug"] for item in reports],
                        )
                    )
                ),
            )
            report_dict = report.to_dict()
            reports.append({"rootSlug": root.slug, "report": report_dict})
            logger.info(
                "Catalog scan job %s finished root %s with status %s",
                handle.record.job_id,
                root.slug,
                report.overall_status.value,
            )
            if report.overall_status == CheckStatus.FAIL:
                worst_state = BackgroundJobState.PARTIAL
            elif (
                report.overall_status == CheckStatus.WARN
                and worst_state == BackgroundJobState.COMPLETED
            ):
                worst_state = BackgroundJobState.PARTIAL

        logger.info(
            "Catalog scan job %s completed across %s roots",
            handle.record.job_id,
            root_count,
        )
        return {
            "state": worst_state.value,
            "summary": f"Catalog scan completed across {root_count} configured roots.",
            "progress": {
                "phase": "completed",
                "current": root_count,
                "total": root_count,
                "percent": 100.0,
                "message": "Catalog scan completed.",
            },
            "reports": reports,
        }

    def _update_scan_progress(
        self,
        handle: ManagedJobHandle,
        *,
        payload: dict[str, object],
        root_slug: str,
        root_index: int,
        total_roots: int,
        completed_roots: list[str],
    ) -> None:
        local_percent = float(payload.get("percent") or 0.0)
        overall_percent = round(
            (((root_index - 1) + (local_percent / 100.0)) / total_roots) * 100,
            2,
        )
        result = {
            "state": BackgroundJobState.RUNNING.value,
            "summary": (
                f"Catalog scan running for root `{root_slug}` ({root_index}/{total_roots})."
            ),
            "progress": {
                "phase": "scan",
                "current": root_index,
                "total": total_roots,
                "percent": overall_percent,
                "message": f"Scanning root `{root_slug}`.",
                "rootSlug": root_slug,
                "rootsCompleted": completed_roots,
                **payload,
            },
        }
        handle.update(
            state=BackgroundJobState.RUNNING,
            summary=str(result["summary"]),
            result=result,
        )

    def _run_consistency_job(self, handle: ManagedJobHandle) -> dict[str, object]:
        logger.info("Catalog consistency job %s started", handle.record.job_id)
        report = self.consistency_service.run(
            handle.settings,
            progress_callback=lambda payload: handle.update(
                state=BackgroundJobState.RUNNING,
                summary=str(payload.get("message") or "Catalog consistency validation is running."),
                result={
                    "state": BackgroundJobState.RUNNING.value,
                    "summary": str(
                        payload.get("message") or "Catalog consistency validation is running."
                    ),
                    "progress": payload,
                },
            ),
        )
        state = (
            BackgroundJobState.FAILED
            if report.overall_status == CheckStatus.FAIL
            else BackgroundJobState.PARTIAL
            if report.overall_status == CheckStatus.WARN
            else BackgroundJobState.COMPLETED
        )
        logger.info(
            "Catalog consistency job %s completed with status %s",
            handle.record.job_id,
            report.overall_status.value,
        )
        return {
            "state": state.value,
            "summary": report.summary,
            "progress": {
                "phase": "completed",
                "current": 1,
                "total": 1,
                "percent": 100.0,
                "message": "Catalog consistency validation completed.",
            },
            "report": report.to_dict(),
        }

    def _has_required_catalog_snapshot(self, settings: AppSettings) -> bool:
        latest = self.store.list_latest_snapshots(settings)
        uploads_snapshot = next(
            (row for row in latest if row.get("root_slug") == _REQUIRED_CONSISTENCY_ROOT),
            None,
        )
        return bool(uploads_snapshot and uploads_snapshot.get("snapshot_id") is not None)

    def _pending_snapshot(
        self,
        *,
        job_type: str,
        summary: str,
        result: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return {
            "jobId": None,
            "jobType": job_type,
            "state": BackgroundJobState.PENDING.value,
            "summary": summary,
            "createdAt": _iso_now(),
            "updatedAt": _iso_now(),
            "startedAt": None,
            "completedAt": None,
            "cancelRequested": False,
            "error": None,
            "result": result or {},
        }

    def _blocked_snapshot(
        self,
        *,
        job_type: str,
        summary: str,
        blocked_by: BackgroundJobRecord,
    ) -> dict[str, object]:
        return self._pending_snapshot(
            job_type=job_type,
            summary=summary,
            result={"blockedBy": _record_to_payload(blocked_by)},
        )
