from __future__ import annotations

from fastapi.testclient import TestClient

from immich_doctor.api.app import create_api_app
from immich_doctor.api.routes import repair as repair_routes


def test_repair_runs_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        repair_routes.RepairVisibilityService,
        "list_runs",
        lambda self, settings: {
            "generatedAt": "2026-03-15T10:00:00+00:00",
            "items": [
                {
                    "repairRunId": "repair-run-1",
                    "startedAt": "2026-03-15T10:00:00+00:00",
                    "endedAt": None,
                    "scope": {"domain": "runtime.metadata_failures"},
                    "status": "partial",
                    "preRepairSnapshotId": "snapshot-1",
                    "postRepairSnapshotId": None,
                    "hasJournalEntries": True,
                    "journalEntryCount": 1,
                    "undoAvailable": True,
                }
            ],
        },
    )
    client = TestClient(create_api_app())

    response = client.get("/api/repair/runs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["items"][0]["repairRunId"] == "repair-run-1"
    assert payload["data"]["items"][0]["undoAvailable"] is True


def test_repair_run_detail_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        repair_routes.RepairVisibilityService,
        "get_run_detail",
        lambda self, settings, repair_run_id: {
            "generatedAt": "2026-03-15T10:00:00+00:00",
            "repairRun": {
                "repairRunId": repair_run_id,
                "startedAt": "2026-03-15T10:00:00+00:00",
                "endedAt": "2026-03-15T10:01:00+00:00",
                "scope": {"domain": "runtime.metadata_failures"},
                "status": "completed",
                "liveStateFingerprint": "fingerprint",
                "planTokenId": "token-1",
                "preRepairSnapshotId": "snapshot-1",
                "postRepairSnapshotId": None,
                "journalEntryCount": 1,
                "undoAvailable": True,
                "journalAvailable": True,
            },
            "journalEntries": [
                {
                    "entryId": "entry-1",
                    "createdAt": "2026-03-15T10:00:10+00:00",
                    "operationType": "chmod",
                    "status": "applied",
                    "assetId": "asset-1",
                    "table": None,
                    "originalPath": "/library/asset.jpg",
                    "quarantinePath": None,
                    "undoType": "chmod_restore",
                    "undoPayload": {"old_mode": "0600", "new_mode": "0644"},
                    "errorDetails": None,
                }
            ],
            "limitations": [
                "Undo visibility exists through persisted journal data.",
                "Full restore orchestration is not implemented yet.",
            ],
        },
    )
    client = TestClient(create_api_app())

    response = client.get("/api/repair/runs/repair-run-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["repairRun"]["planTokenId"] == "token-1"
    assert payload["data"]["journalEntries"][0]["undoType"] == "chmod_restore"


def test_repair_run_detail_route_returns_404_for_missing_run(monkeypatch) -> None:
    monkeypatch.setattr(
        repair_routes.RepairVisibilityService,
        "get_run_detail",
        lambda self, settings, repair_run_id: (_ for _ in ()).throw(FileNotFoundError),
    )
    client = TestClient(create_api_app())

    response = client.get("/api/repair/runs/missing-run")

    assert response.status_code == 404
    assert response.json()["detail"] == "Repair run not found."


def test_quarantine_summary_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        repair_routes.RepairVisibilityService,
        "quarantine_summary",
        lambda self, settings: {
            "generatedAt": "2026-03-15T10:00:00+00:00",
            "path": "/data/quarantine",
            "foundationState": "ok",
            "pathSummary": "Quarantine path is ready.",
            "indexPresent": True,
            "itemCount": 0,
            "workflowImplemented": False,
            "message": (
                "Quarantine indexing exists, but move/restore workflow is not implemented yet."
            ),
        },
    )
    client = TestClient(create_api_app())

    response = client.get("/api/repair/quarantine/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["foundationState"] == "ok"
    assert payload["data"]["workflowImplemented"] is False
