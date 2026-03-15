from __future__ import annotations

from fastapi.testclient import TestClient

from immich_doctor.api.app import create_api_app


def test_health_overview_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    monkeypatch.delenv("IMMICH_DOCTOR_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("BACKUP_TARGET_PATH", raising=False)
    monkeypatch.delenv("IMMICH_STORAGE_PATH", raising=False)

    client = TestClient(create_api_app())

    response = client.get("/api/health/overview")

    assert response.status_code == 200
    payload = response.json()

    assert payload["source"] == "backend"
    assert payload["mocked"] is False
    assert payload["data"]["overallStatus"] == "unknown"
    assert payload["data"]["generatedAt"]
    assert len(payload["data"]["items"]) == 7
    assert {item["id"] for item in payload["data"]["items"]} == {
        "immich-configured",
        "immich-reachable",
        "db-reachability",
        "storage-reachability",
        "path-readiness",
        "backup-readiness",
        "scheduler-runtime-readiness",
    }
