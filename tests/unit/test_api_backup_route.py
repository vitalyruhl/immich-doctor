from __future__ import annotations

from fastapi.testclient import TestClient

from immich_doctor.api.app import create_api_app
from immich_doctor.api.routes import backup as backup_routes
from immich_doctor.backup.core.job_models import BackgroundJobState
from immich_doctor.backup.estimation.models import (
    BackupSizeEstimateSnapshot,
    BackupSizeScopeEstimate,
)


def test_backup_snapshots_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        backup_routes.BackupSnapshotVisibilityService,
        "list_snapshots",
        lambda self, settings: {
            "generatedAt": "2026-03-15T10:00:00+00:00",
            "items": [
                {
                    "snapshotId": "snapshot-1",
                    "createdAt": "2026-03-15T10:00:00+00:00",
                    "kind": "pre_repair",
                    "coverage": "files_only",
                    "repairRunId": "repair-run-1",
                    "verified": True,
                    "manifestPath": "/data/manifests/backup/snapshots/snapshot-1.json",
                    "fileArtifactCount": 1,
                    "hasDbArtifact": False,
                    "basicValidity": "valid",
                    "validityMessage": "Snapshot metadata is structurally valid.",
                }
            ],
            "limitations": [
                "Current executable snapshot creation is files-only.",
                "Restore orchestration is not implemented yet.",
            ],
        },
    )
    client = TestClient(create_api_app())

    response = client.get("/api/backup/snapshots")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["items"][0]["snapshotId"] == "snapshot-1"
    assert payload["data"]["items"][0]["coverage"] == "files_only"


def test_backup_files_route_returns_execution_result(monkeypatch) -> None:
    monkeypatch.setattr(
        backup_routes.BackupExecutionService,
        "run_files_backup",
        lambda self, settings, *, snapshot_kind: {
            "generatedAt": "2026-03-15T11:30:00+00:00",
            "requestedKind": snapshot_kind.value,
            "result": {
                "domain": "backup.files",
                "action": "run",
                "status": "SUCCESS",
                "summary": "File backup execution completed.",
                "warnings": [],
                "details": {},
            },
            "snapshot": {
                "snapshotId": "snapshot-new",
                "createdAt": "2026-03-15T11:30:00+00:00",
                "kind": snapshot_kind.value,
                "coverage": "files_only",
                "repairRunId": None,
                "verified": False,
                "manifestPath": "/data/manifests/backup/snapshots/snapshot-new.json",
                "fileArtifactCount": 1,
                "hasDbArtifact": False,
                "basicValidity": "valid",
                "validityMessage": "Snapshot metadata is structurally valid.",
            },
            "limitations": [
                "Current executable snapshot creation is files-only.",
                "Restore orchestration is not implemented yet.",
            ],
        },
    )
    client = TestClient(create_api_app())

    response = client.post("/api/backup/files", json={"kind": "pre_repair"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["requestedKind"] == "pre_repair"
    assert payload["data"]["snapshot"]["snapshotId"] == "snapshot-new"


def test_backup_size_estimate_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        backup_routes.BackupSizeEstimationService,
        "get_snapshot",
        lambda self, settings: BackupSizeEstimateSnapshot(
            generatedAt="2026-03-18T20:00:00+00:00",
            jobId="job-1",
            state=BackgroundJobState.PARTIAL,
            summary="Partial backup size data is available.",
            sourceScope="backup.files",
            collectedAt="2026-03-18T20:00:00+00:00",
            durationSeconds=2.5,
            cacheAgeSeconds=10.0,
            stale=False,
            scopes=[
                BackupSizeScopeEstimate(
                    scope="database",
                    label="Database backup estimate",
                    state=BackgroundJobState.COMPLETED,
                    sourceScope="immich",
                    representation="physical_db_size_proxy",
                    bytes=1234,
                )
            ],
            warnings=[],
            limitations=[],
        ),
    )
    client = TestClient(create_api_app())

    response = client.get("/api/backup/size-estimate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["jobId"] == "job-1"
    assert payload["data"]["state"] == "partial"


def test_backup_size_collect_route_returns_pending_job(monkeypatch) -> None:
    monkeypatch.setattr(
        backup_routes.BackupSizeEstimationService,
        "collect",
        lambda self, settings, *, force: BackupSizeEstimateSnapshot(
            generatedAt="2026-03-18T20:00:00+00:00",
            jobId="job-2",
            state=BackgroundJobState.PENDING,
            summary="Collecting backup size data has not started yet.",
            sourceScope="backup.files",
            scopes=[],
            warnings=[],
            limitations=[],
        ),
    )
    client = TestClient(create_api_app())

    response = client.post("/api/backup/size-estimate/collect", json={"force": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["jobId"] == "job-2"
    assert payload["data"]["state"] == "pending"
