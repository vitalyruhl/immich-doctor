from __future__ import annotations

from fastapi.testclient import TestClient

from immich_doctor.api.app import create_api_app
from immich_doctor.api.routes import restore as restore_routes


def test_restore_simulation_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        restore_routes.BackupRestoreSimulationService,
        "simulate",
        lambda self, settings, snapshot_id=None, repair_run_id=None: {
            "domain": "backup.restore",
            "action": "simulate",
            "status": "WARN",
            "summary": "Full restore simulation generated deterministic manual steps.",
            "generated_at": "2026-03-15T10:00:00+00:00",
            "metadata": {"instruction_profile": "docker-unraid"},
            "readiness": "simulation_only",
            "checks": [],
            "selected_snapshot": {
                "snapshot_id": "snapshot-1",
                "coverage": "paired",
                "selection_source": "manual",
            },
            "blockers": [],
            "instructions": [
                {
                    "step_id": "stop-services",
                    "phase": "prepare",
                    "description": "Stop Immich services before overwriting live state.",
                    "command": "docker compose stop immich-server",
                    "manual": True,
                }
            ],
            "recommendations": [],
        },
    )
    client = TestClient(create_api_app())

    response = client.get("/api/restore/simulate?snapshot_id=snapshot-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["readiness"] == "simulation_only"
    assert payload["data"]["selected_snapshot"]["snapshot_id"] == "snapshot-1"
