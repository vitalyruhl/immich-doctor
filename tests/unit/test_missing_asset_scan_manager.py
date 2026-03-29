from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

from immich_doctor.consistency.missing_asset_models import (
    MissingAssetReferenceFinding,
    MissingAssetReferenceScanResult,
    MissingAssetReferenceStatus,
    MissingAssetScanJob,
    MissingAssetScanState,
    RepairReadinessStatus,
)
from immich_doctor.consistency.missing_asset_scan_manager import MissingAssetScanManager
from immich_doctor.consistency.missing_asset_scan_store import MissingAssetScanStore
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        _env_file=None,
        MANIFESTS_PATH=tmp_path / "manifests",
        QUARANTINE_PATH=tmp_path / "quarantine",
    )


def _finding(asset_id: str) -> MissingAssetReferenceFinding:
    timestamp = datetime.now(UTC).isoformat()
    return MissingAssetReferenceFinding(
        finding_id=f"missing_asset_reference:{asset_id}",
        asset_id=asset_id,
        asset_type="image",
        status=MissingAssetReferenceStatus.MISSING_ON_DISK,
        logical_path=f"/usr/src/app/upload/upload/{asset_id}.jpg",
        resolved_physical_path=f"/mnt/immich/storage/upload/{asset_id}.jpg",
        owner_id="user-1",
        created_at=timestamp,
        updated_at=timestamp,
        scan_timestamp=timestamp,
        repair_readiness=RepairReadinessStatus.READY,
        message="Missing file on disk.",
    )


def _scan_result(*asset_ids: str) -> MissingAssetReferenceScanResult:
    findings = [_finding(asset_id) for asset_id in asset_ids]
    return MissingAssetReferenceScanResult(
        summary=(
            f"Scanned {len(findings)} asset rows. "
            f"{len(findings)} missing-on-disk references are ready for preview/apply."
        ),
        checks=[
            CheckResult(
                name="postgres_connection",
                status=CheckStatus.PASS,
                message="PostgreSQL connection established.",
            )
        ],
        findings=findings,
        metadata={
            "supportedScope": {"scanTables": ["public.asset"]},
            "scannedAssetCount": len(findings),
            "totalAssetCount": len(findings),
            "findingCount": len(findings),
        },
    )


@dataclass
class _ScriptedScanner:
    runs: list[object]
    calls: int = 0

    def scan_all(self, settings, *, batch_limit=None, progress_callback=None):
        run = self.runs[self.calls]
        self.calls += 1
        return run(progress_callback)


def _success_run(result: MissingAssetReferenceScanResult):
    def runner(progress_callback):
        if progress_callback is not None:
            progress_callback(
                {
                    "scanned_asset_count": int(result.metadata.get("scannedAssetCount") or 0),
                    "finding_count": int(result.metadata.get("findingCount") or 0),
                    "total_asset_count": int(result.metadata.get("totalAssetCount") or 0),
                }
            )
        return result

    return runner


def _blocking_run(
    result: MissingAssetReferenceScanResult,
    *,
    started: Event,
    release: Event,
):
    def runner(progress_callback):
        started.set()
        if progress_callback is not None:
            progress_callback(
                {"scanned_asset_count": 1, "finding_count": 0, "total_asset_count": 2}
            )
        release.wait(timeout=5)
        return result

    return runner


def _failing_run(message: str):
    def runner(progress_callback):
        if progress_callback is not None:
            progress_callback(
                {"scanned_asset_count": 1, "finding_count": 0, "total_asset_count": 2}
            )
        raise RuntimeError(message)

    return runner


def _wait_until(predicate, *, timeout_seconds: float = 3.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for condition.")


def test_start_scan_returns_pending_or_running_without_waiting_for_completion(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    started = Event()
    release = Event()
    manager = MissingAssetScanManager(
        scanner=_ScriptedScanner(
            [_blocking_run(_scan_result("asset-1"), started=started, release=release)]
        )
    )
    try:
        status = manager.start_scan(settings)

        assert status.scan_state in {MissingAssetScanState.PENDING, MissingAssetScanState.RUNNING}
        assert started.wait(timeout=1)
        running_status = manager.get_status(settings)
        assert running_status.scan_state == MissingAssetScanState.RUNNING
        assert running_status.active_scan is not None
        assert running_status.active_scan.scanned_asset_count == 1
        assert running_status.active_scan.result_count == 0
        assert running_status.active_scan.total_asset_count == 2
    finally:
        release.set()
        _wait_until(
            lambda: manager.get_status(settings).scan_state == MissingAssetScanState.COMPLETED
        )
        manager.shutdown()


def test_completed_scan_persists_latest_snapshot_across_manager_restart(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    manager = MissingAssetScanManager(
        scanner=_ScriptedScanner([_success_run(_scan_result("asset-1"))])
    )
    try:
        manager.start_scan(settings)
        _wait_until(
            lambda: manager.get_status(settings).scan_state == MissingAssetScanState.COMPLETED
        )
    finally:
        manager.shutdown()

    restarted = MissingAssetScanManager(scanner=_ScriptedScanner([]))
    try:
        status = restarted.get_status(settings)
        findings = restarted.get_latest_findings(settings)

        assert status.scan_state == MissingAssetScanState.COMPLETED
        assert status.latest_completed is not None
        assert status.latest_completed.finding_count == 1
        assert status.latest_completed.total_asset_count == 1
        assert findings["findings"][0]["asset_id"] == "asset-1"
        assert findings["metadata"]["has_completed_result"] is True
    finally:
        restarted.shutdown()


def test_previous_completed_results_remain_visible_during_rescan(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    started = Event()
    release = Event()
    scanner = _ScriptedScanner(
        [
            _success_run(_scan_result("asset-1")),
            _blocking_run(_scan_result("asset-2"), started=started, release=release),
        ]
    )
    manager = MissingAssetScanManager(scanner=scanner)
    try:
        manager.start_scan(settings)
        _wait_until(
            lambda: manager.get_status(settings).scan_state == MissingAssetScanState.COMPLETED
        )

        manager.start_scan(settings)
        assert started.wait(timeout=1)
        _wait_until(
            lambda: (
                (job := manager.get_status(settings).active_scan) is not None
                and job.total_asset_count == 2
            )
        )

        status = manager.get_status(settings)
        findings = manager.get_latest_findings(settings)

        assert status.scan_state == MissingAssetScanState.RUNNING
        assert status.latest_completed is not None
        assert status.latest_completed.scan_id != status.active_scan.scan_id
        assert status.active_scan.total_asset_count == 2
        assert findings["findings"][0]["asset_id"] == "asset-1"
    finally:
        release.set()
        _wait_until(
            lambda: manager.get_status(settings).scan_state == MissingAssetScanState.COMPLETED
        )
        manager.shutdown()


def test_failed_scan_keeps_last_successful_result(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    scanner = _ScriptedScanner(
        [
            _success_run(_scan_result("asset-1")),
            _failing_run("share temporarily unavailable"),
        ]
    )
    manager = MissingAssetScanManager(scanner=scanner)
    try:
        manager.start_scan(settings)
        _wait_until(
            lambda: manager.get_status(settings).scan_state == MissingAssetScanState.COMPLETED
        )

        manager.start_scan(settings)
        _wait_until(lambda: manager.get_status(settings).scan_state == MissingAssetScanState.FAILED)
        _wait_until(
            lambda: (
                (job := manager.get_status(settings).active_scan) is not None
                and job.total_asset_count == 2
            )
        )

        status = manager.get_status(settings)
        findings = manager.get_latest_findings(settings)

        assert status.scan_state == MissingAssetScanState.FAILED
        assert status.active_scan is not None
        assert status.active_scan.error_message == "share temporarily unavailable"
        assert status.active_scan.total_asset_count == 2
        assert status.latest_completed is not None
        assert findings["findings"][0]["asset_id"] == "asset-1"
    finally:
        manager.shutdown()


def test_reconcile_marks_stale_running_state_as_failed(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = MissingAssetScanStore()
    store.save_state(
        settings,
        MissingAssetScanJob(
            scan_id="stale-scan",
            state=MissingAssetScanState.RUNNING,
            requested_at="2026-03-29T10:00:00+00:00",
            updated_at="2026-03-29T10:01:00+00:00",
            started_at="2026-03-29T10:00:10+00:00",
            summary="Missing asset reference scan is running.",
            scanned_asset_count=10,
            result_count=3,
            total_asset_count=100,
        ),
    )

    manager = MissingAssetScanManager(scanner=_ScriptedScanner([]), store=store)
    try:
        reconciled = manager.reconcile(settings)

        assert reconciled is not None
        assert reconciled.state == MissingAssetScanState.FAILED
        assert reconciled.failure_kind is not None
        assert reconciled.failure_kind.value == "interrupted"
        assert reconciled.total_asset_count == 100
    finally:
        manager.shutdown()


def test_duplicate_concurrent_scan_triggers_reuse_existing_active_job(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    started = Event()
    release = Event()
    scanner = _ScriptedScanner(
        [_blocking_run(_scan_result("asset-1"), started=started, release=release)]
    )
    manager = MissingAssetScanManager(scanner=scanner)
    try:
        first = manager.start_scan(settings)
        assert started.wait(timeout=1)

        second = manager.start_scan(settings)

        assert first.active_scan is not None
        assert second.active_scan is not None
        assert first.active_scan.scan_id == second.active_scan.scan_id
        assert scanner.calls == 1
    finally:
        release.set()
        _wait_until(
            lambda: manager.get_status(settings).scan_state == MissingAssetScanState.COMPLETED
        )
        manager.shutdown()
