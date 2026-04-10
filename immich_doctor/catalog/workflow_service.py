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
        recovered = self._recover_scan_job_if_needed(settings)
        if recovered is not None:
            return _record_to_payload(recovered)
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

        recovered = self._recover_scan_job_if_needed(settings)
        if recovered is not None:
            return _record_to_payload(recovered)

        latest_scan = self.runtime.store.find_latest_job(
            settings,
            job_type=CATALOG_SCAN_JOB_TYPE,
            states=set(TERMINAL_BACKGROUND_JOB_STATES),
        )
        if latest_scan is not None and not force and self._has_complete_scan_coverage(settings):
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

    def _recover_scan_job_if_needed(self, settings: AppSettings) -> BackgroundJobRecord | None:
        session = self.store.find_latest_incomplete_scan_session(settings)
        if session is None:
            return None

        effective_root_slugs = {root.slug for root in self.registry.scan_roots(settings)}
        root_slug = str(session["root_slug"])
        session_id = str(session["id"])

        if root_slug not in effective_root_slugs:
            self.store.mark_session_failed(settings, session_id)
            logger.warning(
                "Retired incomplete catalog scan session %s for obsolete root %s",
                session_id,
                root_slug,
            )
            return None

        self.store.reopen_scan_session(settings, session_id)
        initial_result = {
            "state": BackgroundJobState.PENDING.value,
            "summary": f"Catalog scan recovery queued for root `{root_slug}`.",
            "progress": {
                "phase": "recovery",
                "current": 0,
                "total": 0,
                "percent": None,
                "message": f"Resuming persisted catalog scan session `{session_id}`.",
                "rootSlug": root_slug,
                "resumeSessionId": session_id,
            },
        }
        record = self.runtime.start_job(
            settings,
            job_type=CATALOG_SCAN_JOB_TYPE,
            initial_result=initial_result,
            summary=f"Catalog scan recovery queued for root `{root_slug}`.",
            runner=lambda handle: self._run_resumed_scan_job(
                handle,
                root_slug=root_slug,
                resume_session_id=session_id,
            ),
        )
        logger.info(
            "Recovered catalog scan session %s into background job %s",
            session_id,
            record.job_id,
        )
        return record

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
        coverage = self._scan_coverage(settings)
        latest = self.runtime.store.find_latest_job(
            settings,
            job_type=CATALOG_CONSISTENCY_JOB_TYPE,
            states=set(TERMINAL_BACKGROUND_JOB_STATES),
        )
        if latest is not None and self._consistency_report_is_current(
            latest,
            coverage=coverage,
        ):
            return _record_to_payload(latest)
        if latest is not None:
            return self._stale_consistency_snapshot(
                coverage=coverage,
                latest_consistency=latest,
            )
        if not coverage["hasCompleteCoverage"]:
            return self._pending_snapshot(
                job_type=CATALOG_CONSISTENCY_JOB_TYPE,
                summary="Catalog consistency is waiting for a current committed catalog scan.",
                result={
                    "requiresScan": True,
                    "stale": bool(coverage["staleRootSlugs"]),
                    "staleRootSlugs": coverage["staleRootSlugs"],
                    "missingRootSlugs": coverage["missingRootSlugs"],
                    "latestScanCommittedAt": coverage["latestScanCommittedAt"],
                },
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

        coverage = self._scan_coverage(settings)
        if not coverage["hasCompleteCoverage"]:
            scan_snapshot = self.start_scan(settings, force=True)
            return self._pending_snapshot(
                job_type=CATALOG_CONSISTENCY_JOB_TYPE,
                summary=(
                    "Catalog consistency validation is waiting for a current "
                    "committed catalog scan."
                ),
                result={
                    "requiresScan": True,
                    "blockedBy": scan_snapshot,
                    "stale": bool(coverage["staleRootSlugs"]),
                    "staleRootSlugs": coverage["staleRootSlugs"],
                    "missingRootSlugs": coverage["missingRootSlugs"],
                    "latestScanCommittedAt": coverage["latestScanCommittedAt"],
                },
            )

        latest_consistency = self.runtime.store.find_latest_job(
            settings,
            job_type=CATALOG_CONSISTENCY_JOB_TYPE,
            states=set(TERMINAL_BACKGROUND_JOB_STATES),
        )
        if (
            latest_consistency is not None
            and not force
            and self._consistency_report_is_current(latest_consistency, coverage=coverage)
        ):
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
                "Catalog scan job %s starting root %s (%s/%s) with %s workers",
                handle.record.job_id,
                root.slug,
                index,
                root_count,
                handle.settings.catalog_scan_workers,
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

    def _run_resumed_scan_job(
        self,
        handle: ManagedJobHandle,
        *,
        root_slug: str,
        resume_session_id: str,
    ) -> dict[str, object]:
        logger.info(
            "Catalog scan job %s resuming session %s for root %s",
            handle.record.job_id,
            resume_session_id,
            root_slug,
        )
        report = self.scan_service.run(
            handle.settings,
            root_slug=None,
            resume_session_id=resume_session_id,
            max_files=None,
            progress_callback=lambda payload: self._update_scan_progress(
                handle,
                payload=payload,
                root_slug=root_slug,
                root_index=1,
                total_roots=1,
                completed_roots=[],
            ),
        )
        state = self._scan_report_state(report.overall_status)
        return {
            "state": state.value,
            "summary": f"Catalog scan resumed and completed for root `{root_slug}`.",
            "progress": {
                "phase": "completed",
                "current": 1,
                "total": 1,
                "percent": 100.0,
                "message": f"Catalog scan completed for root `{root_slug}`.",
                "rootSlug": root_slug,
            },
            "reports": [{"rootSlug": root_slug, "report": report.to_dict()}],
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
        phase = str(payload.get("phase") or "scan")
        local_percent = payload.get("percent")
        overall_percent: float | None = None
        if isinstance(local_percent, int | float) and phase == "scan":
            overall_percent = round(
                (((root_index - 1) + (float(local_percent) / 100.0)) / total_roots) * 100,
                2,
            )
        result = {
            "state": BackgroundJobState.RUNNING.value,
            "summary": (
                f"Catalog scan running for root `{root_slug}` ({root_index}/{total_roots})."
                if phase == "scan"
                else f"Catalog scan preparing root `{root_slug}` ({root_index}/{total_roots})."
            ),
            "progress": {
                "phase": phase,
                "current": root_index,
                "total": total_roots,
                "percent": overall_percent,
                "message": (
                    f"Scanning root `{root_slug}`."
                    if phase == "scan"
                    else f"Preparing directory inventory for root `{root_slug}`."
                ),
                "rootSlug": root_slug,
                "scanWorkers": handle.settings.catalog_scan_workers,
                "rootsCompleted": completed_roots,
                **payload,
            },
        }
        handle.update(
            state=BackgroundJobState.RUNNING,
            summary=str(result["summary"]),
            result=result,
        )

    def _has_complete_scan_coverage(self, settings: AppSettings) -> bool:
        coverage = self._scan_coverage(settings)
        return bool(coverage["hasCompleteCoverage"])

    def _scan_report_state(self, status: CheckStatus) -> BackgroundJobState:
        if status == CheckStatus.FAIL:
            return BackgroundJobState.FAILED
        if status == CheckStatus.WARN:
            return BackgroundJobState.PARTIAL
        return BackgroundJobState.COMPLETED

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

    def _scan_coverage(self, settings: AppSettings) -> dict[str, object]:
        self.registry.sync(settings)
        latest = self.store.list_latest_snapshots(settings)
        effective_root_slugs = [root.slug for root in self.registry.scan_roots(settings)]
        current_rows = [
            row
            for row in latest
            if row.get("snapshot_id") is not None
            and bool(row.get("snapshot_current"))
            and str(row["root_slug"]) in effective_root_slugs
        ]
        current_by_slug = {str(row["root_slug"]): row for row in current_rows}
        stale_root_slugs = sorted(
            [
                str(row["root_slug"])
                for row in latest
                if row.get("snapshot_id") is not None
                and not bool(row.get("snapshot_current"))
                and str(row["root_slug"]) in effective_root_slugs
            ]
        )
        missing_root_slugs = [
            slug
            for slug in effective_root_slugs
            if slug not in current_by_slug and slug not in stale_root_slugs
        ]
        latest_scan_committed_at = max(
            (
                str(row["committed_at"])
                for row in current_rows
                if row.get("committed_at") is not None
            ),
            default=None,
        )
        return {
            "effectiveRootSlugs": effective_root_slugs,
            "currentRows": current_rows,
            "currentBySlug": current_by_slug,
            "staleRootSlugs": stale_root_slugs,
            "missingRootSlugs": missing_root_slugs,
            "latestScanCommittedAt": latest_scan_committed_at,
            "hasCompleteCoverage": bool(effective_root_slugs)
            and not stale_root_slugs
            and not missing_root_slugs,
        }

    def _snapshot_basis_signature(
        self,
        snapshot_basis: object,
    ) -> tuple[tuple[str, str, str, str], ...]:
        if not isinstance(snapshot_basis, list):
            return ()
        signature: list[tuple[str, str, str, str]] = []
        for item in snapshot_basis:
            if not isinstance(item, dict):
                continue
            signature.append(
                (
                    str(item.get("rootSlug") or ""),
                    str(item.get("snapshotId") or ""),
                    str(item.get("generation") or ""),
                    str(item.get("committedAt") or ""),
                )
            )
        signature.sort()
        return tuple(signature)

    def _current_snapshot_basis_signature(
        self,
        coverage: dict[str, object],
    ) -> tuple[tuple[str, str, str, str], ...]:
        rows = coverage.get("currentRows")
        if not isinstance(rows, list):
            return ()
        signature = [
            (
                str(row.get("root_slug") or ""),
                str(row.get("snapshot_id") or ""),
                str(row.get("generation") or ""),
                str(row.get("committed_at") or ""),
            )
            for row in rows
        ]
        signature.sort()
        return tuple(signature)

    def _consistency_report_is_current(
        self,
        record: BackgroundJobRecord,
        *,
        coverage: dict[str, object],
    ) -> bool:
        if not coverage["hasCompleteCoverage"]:
            return False
        report = record.result.get("report")
        if not isinstance(report, dict):
            return False
        metadata = report.get("metadata")
        if not isinstance(metadata, dict):
            return False
        return self._snapshot_basis_signature(
            metadata.get("snapshotBasis")
        ) == self._current_snapshot_basis_signature(coverage)

    def _stale_consistency_snapshot(
        self,
        *,
        coverage: dict[str, object],
        latest_consistency: BackgroundJobRecord,
    ) -> dict[str, object]:
        report = latest_consistency.result.get("report")
        previous_compare_generated_at = (
            str(report.get("generated_at"))
            if isinstance(report, dict) and report.get("generated_at") is not None
            else latest_consistency.completed_at
        )
        requires_scan = not bool(coverage["hasCompleteCoverage"])
        return self._pending_snapshot(
            job_type=CATALOG_CONSISTENCY_JOB_TYPE,
            summary=(
                "Catalog consistency needs a rebuild because the storage index changed."
                if not requires_scan
                else "Catalog consistency is waiting for a current committed catalog scan."
            ),
            result={
                "requiresScan": requires_scan,
                "stale": True,
                "staleReason": "catalog_scan_updated",
                "previousCompareGeneratedAt": previous_compare_generated_at,
                "latestScanCommittedAt": coverage["latestScanCommittedAt"],
                "staleRootSlugs": coverage["staleRootSlugs"],
                "missingRootSlugs": coverage["missingRootSlugs"],
            },
        )

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
