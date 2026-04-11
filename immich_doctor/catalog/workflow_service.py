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
from immich_doctor.catalog.service import (
    CatalogInventoryScanService,
    CatalogRootRegistry,
    ScanRuntimeController,
)
from immich_doctor.catalog.store import CatalogStore
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckStatus, ValidationReport
from immich_doctor.services.backup_job_service import BackgroundJobRuntime, ManagedJobHandle

logger = logging.getLogger(__name__)

CATALOG_SCAN_JOB_TYPE = "catalog_inventory_scan"
CATALOG_CONSISTENCY_JOB_TYPE = "catalog_consistency_validation"
_ACTIVE_SCAN_STATES = {
    BackgroundJobState.PENDING.value,
    BackgroundJobState.RUNNING.value,
    BackgroundJobState.PAUSING.value,
    BackgroundJobState.RESUMING.value,
    BackgroundJobState.STOPPING.value,
}


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
            return self._with_scan_runtime_details(settings, _record_to_payload(active))
        recovered = self._recover_scan_job_if_needed(settings)
        if recovered is not None:
            return self._with_scan_runtime_details(settings, _record_to_payload(recovered))
        latest = self.runtime.store.find_latest_job(
            settings,
            job_type=CATALOG_SCAN_JOB_TYPE,
            states=set(TERMINAL_BACKGROUND_JOB_STATES),
        )
        if latest is not None:
            return self._with_scan_runtime_details(settings, _record_to_payload(latest))
        return self._with_scan_runtime_details(
            settings,
            self._pending_snapshot(
                job_type=CATALOG_SCAN_JOB_TYPE,
                summary="No catalog scan has been started yet.",
            ),
        )

    def start_scan(self, settings: AppSettings, *, force: bool) -> dict[str, object]:
        active_consistency = self.runtime.active_job(job_type=CATALOG_CONSISTENCY_JOB_TYPE)
        if active_consistency is not None:
            return self._with_scan_runtime_details(
                settings,
                self._blocked_snapshot(
                    job_type=CATALOG_SCAN_JOB_TYPE,
                    summary=(
                        "Catalog scan is blocked while catalog consistency validation is running."
                    ),
                    blocked_by=active_consistency,
                ),
            )

        active_scan = self.runtime.active_job(job_type=CATALOG_SCAN_JOB_TYPE)
        if active_scan is not None:
            return self._with_scan_runtime_details(settings, _record_to_payload(active_scan))

        recovered = self._recover_scan_job_if_needed(settings)
        if recovered is not None:
            return self._with_scan_runtime_details(settings, _record_to_payload(recovered))

        latest_scan = self.runtime.store.find_latest_job(
            settings,
            job_type=CATALOG_SCAN_JOB_TYPE,
            states=set(TERMINAL_BACKGROUND_JOB_STATES),
        )
        if latest_scan is not None and not force and self._has_complete_scan_coverage(settings):
            return self._with_scan_runtime_details(settings, _record_to_payload(latest_scan))

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
        return self._with_scan_runtime_details(settings, _record_to_payload(record))

    def pause_scan(self, settings: AppSettings) -> dict[str, object]:
        active_scan = self.runtime.active_job(job_type=CATALOG_SCAN_JOB_TYPE)
        if active_scan is None:
            return self._with_scan_runtime_details(
                settings,
                self._pending_snapshot(
                    job_type=CATALOG_SCAN_JOB_TYPE,
                    summary="No active catalog scan is running to pause.",
                ),
            )
        paused = self.runtime.request_pause(job_type=CATALOG_SCAN_JOB_TYPE)
        if paused is None:
            return self._with_scan_runtime_details(settings, _record_to_payload(active_scan))
        return self._with_scan_runtime_details(settings, _record_to_payload(paused))

    def resume_scan(self, settings: AppSettings) -> dict[str, object]:
        active_scan = self.runtime.active_job(job_type=CATALOG_SCAN_JOB_TYPE)
        if active_scan is not None:
            resumed = self.runtime.request_resume(job_type=CATALOG_SCAN_JOB_TYPE)
            payload = _record_to_payload(resumed if resumed is not None else active_scan)
            return self._with_scan_runtime_details(settings, payload)

        session = self.store.find_latest_incomplete_scan_session(settings)
        if session is None or str(session.get("status")) not in {"paused", "stopped"}:
            return self._with_scan_runtime_details(
                settings,
                self._pending_snapshot(
                    job_type=CATALOG_SCAN_JOB_TYPE,
                    summary="No paused catalog scan is available to resume.",
                ),
            )

        root_slug = str(session["root_slug"])
        session_id = str(session["id"])
        self.store.reopen_scan_session(settings, session_id)
        initial_result = {
            "state": BackgroundJobState.RESUMING.value,
            "summary": f"Catalog scan resume queued for root `{root_slug}`.",
            "progress": {
                "phase": "resuming",
                "current": 0,
                "total": 0,
                "percent": None,
                "message": f"Resuming paused catalog scan session `{session_id}`.",
                "rootSlug": root_slug,
                "resumeSessionId": session_id,
            },
        }
        record = self.runtime.start_job(
            settings,
            job_type=CATALOG_SCAN_JOB_TYPE,
            initial_result=initial_result,
            summary=f"Catalog scan resume queued for root `{root_slug}`.",
            runner=lambda handle: self._run_resumed_scan_job(
                handle,
                root_slug=root_slug,
                resume_session_id=session_id,
            ),
        )
        return self._with_scan_runtime_details(settings, _record_to_payload(record))

    def stop_scan(self, settings: AppSettings) -> dict[str, object]:
        active_scan = self.runtime.active_job(job_type=CATALOG_SCAN_JOB_TYPE)
        if active_scan is None:
            return self._with_scan_runtime_details(
                settings,
                self._pending_snapshot(
                    job_type=CATALOG_SCAN_JOB_TYPE,
                    summary="No active catalog scan is running to stop.",
                ),
            )
        stopped = self.runtime.request_stop(job_type=CATALOG_SCAN_JOB_TYPE)
        if stopped is None:
            return self._with_scan_runtime_details(settings, _record_to_payload(active_scan))
        return self._with_scan_runtime_details(settings, _record_to_payload(stopped))

    def pause_scan_actor(self, settings: AppSettings, *, actor_id: str) -> dict[str, object]:
        payload = self.get_scan_job(settings)
        controller = self.runtime.get_job_attachment(job_type=CATALOG_SCAN_JOB_TYPE)
        if not isinstance(controller, ScanRuntimeController):
            payload["summary"] = "No active catalog scan actor is available to pause."
            return self._with_scan_runtime_details(settings, payload)
        if not controller.request_pause(actor_id):
            payload["summary"] = f"Catalog scan actor `{actor_id}` was not found."
            return self._with_scan_runtime_details(settings, payload)
        payload["summary"] = f"Pause requested for catalog scan actor `{actor_id}`."
        return self._with_scan_runtime_details(settings, payload)

    def resume_scan_actor(self, settings: AppSettings, *, actor_id: str) -> dict[str, object]:
        payload = self.get_scan_job(settings)
        controller = self.runtime.get_job_attachment(job_type=CATALOG_SCAN_JOB_TYPE)
        if not isinstance(controller, ScanRuntimeController):
            payload["summary"] = "No active catalog scan actor is available to resume."
            return self._with_scan_runtime_details(settings, payload)
        if not controller.request_resume(actor_id):
            payload["summary"] = f"Catalog scan actor `{actor_id}` cannot be resumed."
            return self._with_scan_runtime_details(settings, payload)
        payload["summary"] = f"Resume requested for catalog scan actor `{actor_id}`."
        return self._with_scan_runtime_details(settings, payload)

    def stop_scan_actor(self, settings: AppSettings, *, actor_id: str) -> dict[str, object]:
        payload = self.get_scan_job(settings)
        controller = self.runtime.get_job_attachment(job_type=CATALOG_SCAN_JOB_TYPE)
        if not isinstance(controller, ScanRuntimeController):
            payload["summary"] = "No active catalog scan actor is available to stop."
            return self._with_scan_runtime_details(settings, payload)
        if not controller.request_stop(actor_id):
            payload["summary"] = f"Catalog scan actor `{actor_id}` was not found."
            return self._with_scan_runtime_details(settings, payload)
        payload["summary"] = f"Stop requested for catalog scan actor `{actor_id}`."
        return self._with_scan_runtime_details(settings, payload)

    def request_scan_worker_resize(
        self,
        settings: AppSettings,
        *,
        workers: int,
    ) -> dict[str, object]:
        payload = self.get_scan_job(settings)
        result = payload.setdefault("result", {})
        if not isinstance(result, dict):
            payload["result"] = {}
            result = payload["result"]
        result["workerResize"] = {
            "supported": False,
            "requestedWorkerCount": workers,
            "configuredWorkerCount": settings.catalog_scan_workers,
            "appliedImmediately": False,
            "semantics": "next_run_only",
            "message": (
                "Runtime worker resizing is not supported safely in the current architecture. "
                "Update configuration and start a new run to change worker count."
            ),
        }
        payload["summary"] = str(result["workerResize"]["message"])
        return self._with_scan_runtime_details(settings, payload)

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
        controller = ScanRuntimeController(worker_count=handle.settings.catalog_scan_workers)
        self.runtime.set_job_attachment(job_type=CATALOG_SCAN_JOB_TYPE, attachment=controller)
        for index, root in enumerate(roots, start=1):
            if handle.stop_requested():
                return {
                    "state": BackgroundJobState.STOPPED.value,
                    "summary": "Catalog scan stopped cooperatively before processing a new root.",
                    "progress": {
                        "phase": "stopped",
                        "current": index - 1,
                        "total": root_count,
                        "percent": round(((index - 1) / max(root_count, 1)) * 100, 2),
                        "message": "Stop requested by operator.",
                    },
                    "reports": reports,
                }
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
                control_state_provider=lambda: {
                    "pauseRequested": handle.pause_requested(),
                    "stopRequested": handle.stop_requested(),
                },
                runtime_controller=controller,
            )
            report_dict = report.to_dict()
            reports.append({"rootSlug": root.slug, "report": report_dict})
            session_status = self._scan_session_status(report)
            if session_status in {"paused", "stopped"}:
                return {
                    "state": (
                        BackgroundJobState.STOPPED.value
                        if session_status == "stopped"
                        else BackgroundJobState.PAUSED.value
                    ),
                    "summary": report.summary,
                    "progress": {
                        "phase": session_status,
                        "current": index,
                        "total": root_count,
                        "percent": round((index / max(root_count, 1)) * 100, 2),
                        "message": report.summary,
                        "rootSlug": root.slug,
                    },
                    "reports": reports,
                }
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
        controller = ScanRuntimeController(worker_count=handle.settings.catalog_scan_workers)
        self.runtime.set_job_attachment(job_type=CATALOG_SCAN_JOB_TYPE, attachment=controller)
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
            control_state_provider=lambda: {
                "pauseRequested": handle.pause_requested(),
                "stopRequested": handle.stop_requested(),
            },
            runtime_controller=controller,
        )
        session_status = self._scan_session_status(report)
        if session_status == "stopped":
            state = BackgroundJobState.STOPPED
            summary = f"Catalog scan stopped for root `{root_slug}`."
            phase = "stopped"
        elif session_status == "paused":
            state = BackgroundJobState.PAUSED
            summary = f"Catalog scan paused for root `{root_slug}`."
            phase = "paused"
        else:
            state = self._scan_report_state(report.overall_status)
            summary = f"Catalog scan resumed and completed for root `{root_slug}`."
            phase = "completed"
        return {
            "state": state.value,
            "summary": summary,
            "progress": {
                "phase": phase,
                "current": 1,
                "total": 1,
                "percent": 100.0 if phase == "completed" else None,
                "message": summary,
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
        job_state = self._scan_job_state_from_handle(handle)
        phase_label = "scan" if phase == "scan" else "prepare"
        if job_state == BackgroundJobState.PAUSING:
            phase_label = "pausing"
        elif job_state == BackgroundJobState.STOPPING:
            phase_label = "stopping"
        elif job_state == BackgroundJobState.RESUMING:
            phase_label = "resuming"
        result = {
            "state": job_state.value,
            "summary": (
                f"Catalog scan running for root `{root_slug}` ({root_index}/{total_roots})."
                if phase_label == "scan"
                else f"Catalog scan pausing for root `{root_slug}` ({root_index}/{total_roots})."
                if phase_label == "pausing"
                else f"Catalog scan stopping for root `{root_slug}` ({root_index}/{total_roots})."
                if phase_label == "stopping"
                else f"Catalog scan preparing root `{root_slug}` ({root_index}/{total_roots})."
            ),
            "progress": {
                "phase": phase_label,
                "current": root_index,
                "total": total_roots,
                "percent": overall_percent,
                "message": (
                    f"Scanning root `{root_slug}`."
                    if phase_label == "scan"
                    else f"Pausing scan work for root `{root_slug}` at a safe boundary."
                    if phase_label == "pausing"
                    else f"Stopping scan work for root `{root_slug}` at a safe boundary."
                    if phase_label == "stopping"
                    else f"Preparing directory inventory for root `{root_slug}`."
                ),
                "rootSlug": root_slug,
                "configuredWorkerCount": handle.settings.catalog_scan_workers,
                "activeWorkerCount": int(payload.get("activeWorkerCount") or 0),
                "scanState": self._scan_state_from_background_state(
                    job_state,
                    has_job_id=True,
                ),
                "rootsCompleted": completed_roots,
                **payload,
            },
        }
        handle.update(
            state=job_state,
            summary=str(result["summary"]),
            result=result,
        )

    def _scan_job_state_from_handle(self, handle: ManagedJobHandle) -> BackgroundJobState:
        if handle.stop_requested():
            return BackgroundJobState.STOPPING
        if handle.pause_requested():
            return BackgroundJobState.PAUSING
        if handle.record.state == BackgroundJobState.RESUMING:
            return BackgroundJobState.RESUMING
        return BackgroundJobState.RUNNING

    def _scan_session_status(self, report: ValidationReport) -> str | None:
        session_section = next(
            (section for section in report.sections if section.name == "SCAN_SESSION"),
            None,
        )
        if session_section is None or not session_section.rows:
            return None
        first_row = session_section.rows[0]
        if not isinstance(first_row, dict):
            return None
        status = first_row.get("status")
        return str(status) if status is not None else None

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

    def _with_scan_runtime_details(
        self,
        settings: AppSettings,
        payload: dict[str, object],
    ) -> dict[str, object]:
        result = payload.get("result")
        if not isinstance(result, dict):
            result = {}
            payload["result"] = result

        progress = result.get("progress")
        active_worker_count = 0
        actors: list[dict[str, object]] = []
        if isinstance(progress, dict):
            candidate = progress.get("activeWorkerCount")
            if isinstance(candidate, int):
                active_worker_count = max(candidate, 0)
            actor_candidate = progress.get("actors")
            if isinstance(actor_candidate, list):
                actors = [item for item in actor_candidate if isinstance(item, dict)]

        controller = self.runtime.get_job_attachment(job_type=CATALOG_SCAN_JOB_TYPE)
        if isinstance(controller, ScanRuntimeController):
            actors = controller.snapshot()
            active_worker_count = controller.active_worker_count()

        state_value = str(payload.get("state") or BackgroundJobState.PENDING.value)
        has_job_id = payload.get("jobId") is not None
        scan_state = self._scan_state_from_background_state(
            state_value,
            has_job_id=has_job_id,
        )
        runtime_details = {
            "scanState": scan_state,
            "configuredWorkerCount": settings.catalog_scan_workers,
            "activeWorkerCount": active_worker_count,
            "actors": actors,
            "workerResize": {
                "supported": False,
                "semantics": "next_run_only",
                "message": (
                    "Runtime worker resizing is not supported safely in the current architecture. "
                    "Use configured workers for the next run."
                ),
            },
        }
        result["runtime"] = runtime_details
        return payload

    def _scan_state_from_background_state(
        self,
        state: BackgroundJobState | str,
        *,
        has_job_id: bool,
    ) -> str:
        normalized = state.value if isinstance(state, BackgroundJobState) else str(state)
        if not has_job_id:
            return "idle"
        if normalized in {BackgroundJobState.RUNNING.value, BackgroundJobState.PENDING.value}:
            return "running"
        if normalized == BackgroundJobState.PAUSING.value:
            return "pausing"
        if normalized == BackgroundJobState.PAUSED.value:
            return "paused"
        if normalized == BackgroundJobState.RESUMING.value:
            return "resuming"
        if normalized in {
            BackgroundJobState.STOPPING.value,
            BackgroundJobState.CANCEL_REQUESTED.value,
        }:
            return "stopping"
        if normalized in {BackgroundJobState.STOPPED.value, BackgroundJobState.CANCELED.value}:
            return "stopped"
        if normalized in {BackgroundJobState.COMPLETED.value, BackgroundJobState.PARTIAL.value}:
            return "completed"
        if normalized == BackgroundJobState.FAILED.value:
            return "failed"
        return "idle"

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
