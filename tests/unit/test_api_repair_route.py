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


def test_repair_undo_plan_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        repair_routes.RepairUndoService,
        "plan",
        lambda self, settings, repair_run_id, entry_ids=(): {
            "domain": "repair.undo",
            "action": "plan",
            "status": "PASS",
            "summary": "Undo planning classified 1 journal entry as reversible_now.",
            "generated_at": "2026-03-15T10:00:00+00:00",
            "metadata": {"selected_entry_ids": ["entry-1"]},
            "repair_run_id": repair_run_id,
            "target_repair_run_status": "completed",
            "eligibility": "reversible_now",
            "apply_allowed": True,
            "checks": [],
            "blockers": [],
            "entry_assessments": [
                {
                    "entry_id": "entry-1",
                    "operation_type": "fix_permissions",
                    "eligibility": "reversible_now",
                    "asset_id": "asset-1",
                    "original_path": "/library/asset.jpg",
                    "undo_type": "restore_permissions",
                    "blockers": [],
                    "details": {"old_mode": 384, "new_mode": 416},
                }
            ],
            "recommendations": [],
        },
    )
    client = TestClient(create_api_app())

    response = client.get("/api/repair/runs/repair-run-1/undo-plan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["eligibility"] == "reversible_now"
    assert payload["data"]["entry_assessments"][0]["entry_id"] == "entry-1"


def test_repair_undo_execute_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        repair_routes.RepairUndoService,
        "execute",
        lambda self, settings, repair_run_id, entry_ids=(), apply=False: {
            "domain": "repair.undo",
            "action": "apply",
            "status": "PASS",
            "summary": "Targeted undo restored 1 journal entries and failed 0.",
            "generated_at": "2026-03-15T10:00:00+00:00",
            "metadata": {"undo_repair_run_id": "undo-run-1"},
            "repair_run_id": "undo-run-1",
            "target_repair_run_id": repair_run_id,
            "eligibility": "reversible_now",
            "checks": [],
            "blockers": [],
            "execution_items": [
                {
                    "entry_id": "entry-1",
                    "operation_type": "fix_permissions",
                    "status": "applied",
                    "message": "Permission mode was restored from journal data.",
                    "original_path": "/library/asset.jpg",
                    "details": {"restored_mode": 384},
                }
            ],
            "recommendations": [],
        },
    )
    client = TestClient(create_api_app())

    response = client.post(
        "/api/repair/runs/repair-run-1/undo",
        json={"apply": True, "entry_ids": ["entry-1"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["repair_run_id"] == "undo-run-1"
    assert payload["data"]["execution_items"][0]["status"] == "applied"
