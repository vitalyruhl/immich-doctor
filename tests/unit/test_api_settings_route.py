from __future__ import annotations

from fastapi.testclient import TestClient

from immich_doctor.api.app import create_api_app
from immich_doctor.services.testbed_dump_service import TestbedDumpImportResult


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
        "testbed",
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


def test_testbed_dump_overview_route_is_hidden_outside_dev_testbed(monkeypatch) -> None:
    monkeypatch.setenv("IMMICH_DOCTOR_ENVIRONMENT", "development")
    client = TestClient(create_api_app())

    response = client.get("/api/settings/testbed/dump")

    assert response.status_code == 404


def test_testbed_dump_routes_return_backend_contract(monkeypatch) -> None:
    monkeypatch.setenv("IMMICH_DOCTOR_ENVIRONMENT", "dev-testbed")
    monkeypatch.setenv("TESTBED_DUMP_PATH", r"C:\Temp\immich.sql")
    monkeypatch.setenv("TESTBED_AUTO_IMPORT_ON_EMPTY", "false")

    imported: list[tuple[str | None, str, bool]] = []

    def fake_import_dump(self, settings, *, requested_path=None, dump_format=None, force=False):
        del self, settings
        imported.append((requested_path, dump_format or "auto", force))
        return TestbedDumpImportResult(
            state="completed",
            classification="success",
            summary="Testbed dump import completed successfully.",
            requestedPath=requested_path or r"C:\Temp\immich.sql",
            effectivePath="/mnt/testbed/dumps/immich.sql",
            dumpFormat=dump_format or "auto",
            generatedAt="2026-04-09T10:00:00+00:00",
            dbWasEmpty=False,
            expectedSkippedStatements=0,
            structuralErrorCount=0,
            meaningfulErrorCount=0,
            warnings=[],
        )

    monkeypatch.setattr(
        "immich_doctor.api.routes.settings.TestbedDumpImportService.import_dump",
        fake_import_dump,
    )

    client = TestClient(create_api_app())

    overview = client.get("/api/settings/testbed/dump")
    assert overview.status_code == 200
    assert overview.json()["data"]["enabled"] is True
    assert overview.json()["data"]["defaultPath"] == r"C:\Temp\immich.sql"

    response = client.post(
        "/api/settings/testbed/dump/import",
        json={"path": r"C:\Temp\override.sql", "format": "plain", "force": True},
    )

    assert response.status_code == 200
    assert response.json()["data"]["classification"] == "success"
    assert imported == [(r"C:\Temp\override.sql", "plain", True)]
