from __future__ import annotations

import time
from pathlib import Path
from threading import Event
from typing import Any

from immich_doctor.backup.core.job_models import BackgroundJobRecord, BackgroundJobState
from immich_doctor.catalog.service import CatalogRootRegistry
from immich_doctor.catalog.store import CatalogStore
from immich_doctor.catalog.workflow_service import (
    CATALOG_CONSISTENCY_JOB_TYPE,
    CATALOG_SCAN_JOB_TYPE,
    CatalogWorkflowService,
)
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckStatus, ValidationReport, ValidationSection
from immich_doctor.services.backup_job_service import BackgroundJobRuntime


def _settings(
    tmp_path: Path,
    *,
    library_root: Path | None = None,
    uploads_path: Path | None = None,
    catalog_scan_workers: int = 4,
) -> AppSettings:
    return AppSettings(
        _env_file=None,
        manifests_path=tmp_path / "manifests",
        immich_library_root=library_root,
        immich_uploads_path=uploads_path,
        catalog_scan_workers=catalog_scan_workers,
    )


def _wait_for_runtime(runtime: BackgroundJobRuntime, *, job_type: str) -> None:
    deadline = time.monotonic() + 5
    while runtime.active_job(job_type=job_type) is not None:
        assert time.monotonic() < deadline
        time.sleep(0.05)


def _waiting_runner(release: Event):  # type: ignore[no-untyped-def]
    def runner(handle):  # type: ignore[no-untyped-def]
        del handle
        release.wait(5)
        return {
            "state": "completed",
            "summary": "Catalog consistency validation completed.",
        }

    return runner


def test_catalog_scan_is_blocked_while_consistency_job_is_running(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    release = Event()
    runtime = BackgroundJobRuntime()
    try:
        runtime.start_job(
            settings,
            job_type=CATALOG_CONSISTENCY_JOB_TYPE,
            initial_result={"state": "pending"},
            summary="Catalog consistency validation queued.",
            runner=_waiting_runner(release),
        )
        service = CatalogWorkflowService(runtime=runtime)

        result = service.start_scan(settings, force=True)

        assert result["jobId"] is None
        assert result["result"]["blockedBy"]["jobType"] == CATALOG_CONSISTENCY_JOB_TYPE
    finally:
        release.set()
        _wait_for_runtime(runtime, job_type=CATALOG_CONSISTENCY_JOB_TYPE)
        runtime.shutdown()


def test_catalog_consistency_queues_scan_when_required_snapshot_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = _settings(tmp_path)
    runtime = BackgroundJobRuntime()
    try:
        service = CatalogWorkflowService(runtime=runtime)
        monkeypatch.setattr(
            CatalogWorkflowService,
            "_scan_coverage",
            lambda self, settings: {
                "effectiveRootSlugs": ["uploads"],
                "currentRows": [],
                "currentBySlug": {},
                "staleRootSlugs": [],
                "missingRootSlugs": ["uploads"],
                "latestScanCommittedAt": None,
                "hasCompleteCoverage": False,
            },
        )
        monkeypatch.setattr(
            CatalogWorkflowService,
            "start_scan",
            lambda self, settings, *, force: {
                "jobId": "catalog-scan-1",
                "jobType": "catalog_inventory_scan",
                "state": "pending",
                "summary": "Catalog scan queued.",
                "result": {"force": force},
            },
        )

        result = service.start_consistency(settings, force=False)

        assert result["jobId"] is None
        assert result["result"]["requiresScan"] is True
        assert result["result"]["blockedBy"]["jobId"] == "catalog-scan-1"
    finally:
        runtime.shutdown()


def test_catalog_consistency_job_returns_stale_snapshot_after_scan_basis_changes(
    tmp_path: Path,
) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    settings = _settings(tmp_path, uploads_path=uploads)
    store = CatalogStore()
    runtime = BackgroundJobRuntime()

    try:
        synced_roots = CatalogRootRegistry(store=store).sync(settings)
        uploads_root = next(root for root in synced_roots if root["slug"] == "uploads")
        session = store.create_scan_session(
            settings,
            storage_root_id=int(uploads_root["id"]),
            max_files=None,
        )
        committed = store.commit_scan_session(settings, str(session["id"]))
        assert committed is not None
        snapshot = store.get_snapshot(settings, int(committed["snapshot_id"]))
        assert snapshot is not None

        latest_record = BackgroundJobRecord(
            jobId="catalog-consistency-1",
            jobType=CATALOG_CONSISTENCY_JOB_TYPE,
            state=BackgroundJobState.COMPLETED,
            summary="Catalog consistency completed.",
            startedAt=snapshot["committed_at"],
            completedAt=snapshot["committed_at"],
            result={
                "state": BackgroundJobState.COMPLETED.value,
                "summary": "Catalog consistency completed.",
                "report": {
                    "domain": "consistency.catalog",
                    "action": "validate",
                    "status": "PASS",
                    "summary": "Catalog consistency completed.",
                    "generated_at": snapshot["committed_at"],
                    "metadata": {
                        "snapshotBasis": [
                            {
                                "rootSlug": "uploads",
                                "snapshotId": snapshot["id"],
                                "generation": snapshot["generation"],
                                "committedAt": snapshot["committed_at"],
                                "absolutePath": str(uploads),
                            }
                        ],
                        "latestScanCommittedAt": snapshot["committed_at"],
                    },
                    "checks": [],
                    "sections": [],
                    "metrics": [],
                    "recommendations": [],
                },
            },
        )
        runtime.store.persist_job(settings, latest_record)

        moved_uploads = tmp_path / "uploads-moved"
        moved_uploads.mkdir(parents=True, exist_ok=True)
        moved_settings = _settings(tmp_path, uploads_path=moved_uploads)

        service = CatalogWorkflowService(runtime=runtime, store=store)
        result = service.get_consistency_job(moved_settings)

        assert result["jobId"] is None
        assert result["result"]["stale"] is True
        assert result["result"]["requiresScan"] is True
        assert result["result"]["staleRootSlugs"] == ["uploads"]
    finally:
        runtime.shutdown()


def test_catalog_scan_job_recovers_incomplete_session_for_effective_root(
    tmp_path: Path,
) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    settings = _settings(tmp_path, uploads_path=uploads)
    store = CatalogStore()
    runtime = BackgroundJobRuntime()
    release = Event()
    resume_calls: list[tuple[str | None, str | None]] = []

    try:
        synced_roots = CatalogRootRegistry(store=store).sync(settings)
        uploads_root = next(root for root in synced_roots if root["slug"] == "uploads")
        session = store.create_scan_session(
            settings,
            storage_root_id=int(uploads_root["id"]),
            max_files=None,
        )
        paused = store.mark_session_paused(settings, str(session["id"]))
        assert paused is not None

        service = CatalogWorkflowService(runtime=runtime, store=store)

        class _FakeScanService:
            def run(
                self,
                settings_arg: Any,
                *,
                root_slug: str | None,
                resume_session_id: str | None,
                max_files: int | None,
                progress_callback: Any,
                control_state_provider: Any,
                runtime_controller: Any,
            ) -> ValidationReport:
                del settings_arg, max_files, progress_callback, control_state_provider, runtime_controller
                resume_calls.append((root_slug, resume_session_id))
                release.wait(5)
                return ValidationReport(
                    domain="analyze.catalog",
                    action="scan",
                    summary="Recovered catalog scan completed.",
                    checks=[],
                    sections=[],
                    metadata={},
                )

        object.__setattr__(service, "scan_service", _FakeScanService())

        result = service.get_scan_job(settings)

        assert result["jobId"] is not None
        assert result["summary"] == "Catalog scan recovery queued for root `uploads`."
        active = runtime.active_job(job_type=CATALOG_SCAN_JOB_TYPE)
        assert active is not None
        deadline = time.monotonic() + 5
        while not resume_calls:
            assert time.monotonic() < deadline
            time.sleep(0.05)
        assert resume_calls == [(None, str(session["id"]))]
    finally:
        release.set()
        _wait_for_runtime(runtime, job_type=CATALOG_SCAN_JOB_TYPE)
        runtime.shutdown()


def test_catalog_scan_job_retires_incomplete_session_for_obsolete_root(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    uploads = storage / "upload"
    uploads.mkdir(parents=True, exist_ok=True)
    settings = _settings(tmp_path, library_root=storage, uploads_path=uploads)
    store = CatalogStore()
    runtime = BackgroundJobRuntime()

    try:
        synced_roots = CatalogRootRegistry(store=store).sync(settings)
        library_root = next(root for root in synced_roots if root["slug"] == "library")
        session = store.create_scan_session(
            settings,
            storage_root_id=int(library_root["id"]),
            max_files=None,
        )

        service = CatalogWorkflowService(runtime=runtime, store=store)

        result = service.get_scan_job(settings)

        assert result["jobId"] is None
        assert result["summary"] == "No catalog scan has been started yet."
        latest_session = store.get_scan_session(settings, str(session["id"]))
        assert latest_session is not None
        assert latest_session["status"] == "failed"
        assert runtime.active_job(job_type=CATALOG_SCAN_JOB_TYPE) is None
    finally:
        runtime.shutdown()


def test_catalog_scan_progress_payload_contains_worker_count(tmp_path: Path) -> None:
    settings = _settings(tmp_path, uploads_path=tmp_path / "uploads", catalog_scan_workers=7)
    service = CatalogWorkflowService(runtime=BackgroundJobRuntime())
    updates: list[dict[str, object]] = []

    class _FakeHandle:
        def __init__(self) -> None:
            self.settings = settings
            self.record = type("_Record", (), {"job_id": "job-1", "state": "running"})()

        def stop_requested(self) -> bool:
            return False

        def pause_requested(self) -> bool:
            return False

        def update(self, *, state, summary: str, result: dict[str, object]) -> None:  # type: ignore[no-untyped-def]
            del state, summary
            updates.append(result)

    try:
        service._update_scan_progress(
            _FakeHandle(),
            payload={"phase": "scan", "percent": 50.0},
            root_slug="uploads",
            root_index=1,
            total_roots=2,
            completed_roots=[],
        )
        assert updates
        assert updates[-1]["progress"]["configuredWorkerCount"] == 7
    finally:
        service.runtime.shutdown()


def test_catalog_scan_pause_and_resume_transitions(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    settings = _settings(tmp_path, uploads_path=uploads)
    runtime = BackgroundJobRuntime()
    service = CatalogWorkflowService(runtime=runtime)

    pause_observed = Event()

    class _FakeScanService:
        def run(
            self,
            settings_arg: Any,
            *,
            root_slug: str | None,
            resume_session_id: str | None,
            max_files: int | None,
            progress_callback: Any,
            control_state_provider: Any,
            runtime_controller: Any,
        ) -> ValidationReport:
            del settings_arg, root_slug, resume_session_id, max_files, progress_callback, runtime_controller
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                state = control_state_provider()
                if state.get("pauseRequested"):
                    pause_observed.set()
                    break
                time.sleep(0.02)
            return ValidationReport(
                domain="analyze.catalog",
                action="scan",
                summary="Catalog scan paused cooperatively.",
                checks=[],
                sections=[
                    ValidationSection(
                        name="SCAN_SESSION",
                        status=CheckStatus.WARN,
                        rows=[{"status": "paused"}],
                    )
                ],
                metadata={},
            )

    object.__setattr__(service, "scan_service", _FakeScanService())
    try:
        started = service.start_scan(settings, force=True)
        assert started["state"] == "pending"

        pause_result = service.pause_scan(settings)
        assert pause_result["state"] == "pausing"

        deadline = time.monotonic() + 5
        while runtime.active_job(job_type=CATALOG_SCAN_JOB_TYPE) is not None:
            assert time.monotonic() < deadline
            time.sleep(0.05)

        assert pause_observed.is_set()

        resumed = service.resume_scan(settings)
        assert resumed["state"] in {"pending", "resuming", "running"}
    finally:
        _wait_for_runtime(runtime, job_type=CATALOG_SCAN_JOB_TYPE)
        runtime.shutdown()


def test_catalog_scan_worker_resize_reports_next_run_only(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = BackgroundJobRuntime()
    try:
        service = CatalogWorkflowService(runtime=runtime)
        result = service.request_scan_worker_resize(settings, workers=16)
        runtime_details = result["result"]["runtime"]
        assert runtime_details["configuredWorkerCount"] == settings.catalog_scan_workers
        assert runtime_details["workerResize"]["supported"] is False
        assert runtime_details["workerResize"]["semantics"] == "next_run_only"
        assert result["result"]["workerResize"]["requestedWorkerCount"] == 16
    finally:
        runtime.shutdown()
