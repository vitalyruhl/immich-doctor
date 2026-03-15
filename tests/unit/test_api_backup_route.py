from __future__ import annotations

from fastapi.testclient import TestClient

from immich_doctor.api.app import create_api_app
from immich_doctor.api.routes import backup as backup_routes


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
