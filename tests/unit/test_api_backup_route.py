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
                    "manifestPath": "/data/manifests/backup/snapshots/snapshot-1.json",
                    "fileArtifactCount": 1,
                    "hasDbArtifact": False,
                    "basicValidity": "valid",
                    "validityMessage": (
                        "Snapshot manifest structure is valid. "
                        "Artifact content is not verified here."
                    ),
                }
            ],
            "limitations": [
                "Current executable snapshot coverage is files-only.",
                (
                    "Snapshot visibility currently reports manifest structure only, "
                    "not artifact-content integrity."
                ),
                "Restore execution is not implemented.",
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
                "manifestPath": "/data/manifests/backup/snapshots/snapshot-new.json",
                "fileArtifactCount": 1,
                "hasDbArtifact": False,
                "basicValidity": "valid",
                "validityMessage": (
                    "Snapshot manifest structure is valid. Artifact content is not verified here."
                ),
            },
            "limitations": [
                "Current executable snapshot coverage is files-only.",
                (
                    "Snapshot visibility currently reports manifest structure only, "
                    "not artifact-content integrity."
                ),
                "Restore execution is not implemented.",
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
            summary="Backup size collection completed with partial data.",
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
            summary="Backup size collection is pending.",
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


def test_backup_targets_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        backup_routes.BackupTargetSettingsService,
        "list_targets",
        lambda self, settings: {
            "generatedAt": "2026-03-18T20:00:00+00:00",
            "configPath": "/config/backup/targets.json",
            "configRoot": "/config/backup",
            "items": [
                {
                    "targetId": "target-1",
                    "targetName": "Local Backup",
                    "targetType": "local",
                    "enabled": True,
                    "transport": {"path": "/backup", "passwordSecretRef": None},
                    "verificationStatus": "unknown",
                    "lastTestResult": None,
                    "lastSuccessfulBackup": None,
                    "retentionPolicy": {
                        "mode": "keep_all",
                        "maxVersions": None,
                        "pruneAutomatically": False,
                    },
                    "restoreReadiness": "not_implemented",
                    "sourceScope": "files_only",
                    "schedulingCompatible": True,
                    "warnings": [],
                    "createdAt": "2026-03-18T20:00:00+00:00",
                    "updatedAt": "2026-03-18T20:00:00+00:00",
                }
            ],
            "limitations": [],
        },
    )
    client = TestClient(create_api_app())

    response = client.get("/api/backup/targets")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["items"][0]["targetId"] == "target-1"
    assert payload["data"]["items"][0]["targetType"] == "local"


def test_backup_target_validation_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        backup_routes.BackupTargetValidationService,
        "get_validation",
        lambda self, settings, *, target_id: {
            "generatedAt": "2026-03-18T20:00:00+00:00",
            "jobId": "validation-1",
            "targetId": target_id,
            "state": "completed",
            "summary": "Target validation completed for currently implemented checks.",
            "checks": [],
            "warnings": [],
        },
    )
    client = TestClient(create_api_app())

    response = client.get("/api/backup/targets/target-1/validation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["jobId"] == "validation-1"


def test_backup_execution_current_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        backup_routes.ManualBackupExecutionService,
        "get_current",
        lambda self, settings: {
            "generatedAt": "2026-03-18T20:00:00+00:00",
            "jobId": "execution-1",
            "state": "running",
            "summary": "Manual files-only backup is running.",
            "report": None,
            "snapshot": None,
            "warnings": [],
        },
    )
    client = TestClient(create_api_app())

    response = client.get("/api/backup/executions/current")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["state"] == "running"
