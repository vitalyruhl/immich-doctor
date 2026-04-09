from __future__ import annotations

import time
from pathlib import Path
from threading import Event

from immich_doctor.catalog.workflow_service import (
    CATALOG_CONSISTENCY_JOB_TYPE,
    CatalogWorkflowService,
)
from immich_doctor.core.config import AppSettings
from immich_doctor.services.backup_job_service import BackgroundJobRuntime


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(_env_file=None, manifests_path=tmp_path / "manifests")


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
            "_has_required_catalog_snapshot",
            lambda self, settings: False,
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
