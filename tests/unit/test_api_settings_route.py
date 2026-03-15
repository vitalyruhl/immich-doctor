from __future__ import annotations

from fastapi.testclient import TestClient

from immich_doctor.api.app import create_api_app


def test_settings_overview_route_returns_canonical_contract(monkeypatch) -> None:
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    monkeypatch.delenv("IMMICH_DOCTOR_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("IMMICH_STORAGE_PATH", raising=False)
    monkeypatch.delenv("BACKUP_TARGET_PATH", raising=False)

    client = TestClient(create_api_app())

    response = client.get("/api/settings")

    assert response.status_code == 200
    payload = response.json()

    assert payload["source"] == "backend"
    assert payload["mocked"] is False
    assert payload["data"]["schemaVersion"] == "v1"
    assert payload["data"]["capabilityState"] == "PARTIAL"
    assert {item["id"] for item in payload["data"]["capabilities"]} == {
        "read_settings",
        "settings_schema",
        "update_settings",
    }
    assert {section["id"] for section in payload["data"]["sections"]} == {
        "immich",
        "database",
        "storage",
        "backup",
        "scheduler-runtime",
    }


def test_settings_schema_route_returns_versioned_schema() -> None:
    client = TestClient(create_api_app())

    response = client.get("/api/settings/schema")

    assert response.status_code == 200
    payload = response.json()

    assert payload["data"]["schemaVersion"] == "v1"
    assert payload["data"]["sections"]
    assert payload["data"]["sections"][0]["fields"]


def test_settings_update_route_is_safe_and_non_persistent() -> None:
    client = TestClient(create_api_app())

    response = client.put(
        "/api/settings",
        json={"sections": {"database": {"db_host": "postgres"}}},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["data"]["capabilityState"] == "NOT_IMPLEMENTED"
    assert payload["data"]["applied"] is False
    assert payload["data"]["acceptedSections"] == ["database"]
