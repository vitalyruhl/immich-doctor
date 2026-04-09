from __future__ import annotations

from fastapi.testclient import TestClient

from immich_doctor.api.app import create_api_app
from immich_doctor.api.routes import analyze as analyze_routes
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport, ValidationSection


def _report(action: str, section_name: str, rows: list[dict[str, object]]) -> ValidationReport:
    return ValidationReport(
        domain="analyze.catalog",
        action=action,
        summary=f"{action} completed.",
        checks=[
            CheckResult(
                name="catalog_path",
                status=CheckStatus.PASS,
                message="Catalog path is writable.",
            )
        ],
        sections=[
            ValidationSection(
                name=section_name,
                status=CheckStatus.PASS,
                rows=rows,
            )
        ],
        metadata={"catalog_path": "/data/manifests/catalog/file-catalog.sqlite3"},
    )


def test_catalog_scan_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        analyze_routes.CatalogInventoryScanService,
        "run",
        lambda self, settings, **kwargs: _report(
            "scan",
            "SCAN_SESSION",
            [
                {
                    "id": "session-1",
                    "root_slug": "uploads",
                    "status": "completed",
                    "files_seen": 2,
                }
            ],
        ),
    )
    client = TestClient(create_api_app())

    response = client.post("/api/analyze/catalog/scan", json={"root": "uploads"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "backend"
    assert payload["data"]["domain"] == "analyze.catalog"
    assert payload["data"]["action"] == "scan"
    assert payload["data"]["sections"][0]["rows"][0]["root_slug"] == "uploads"


def test_catalog_status_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        analyze_routes.CatalogStatusService,
        "run",
        lambda self, settings, **kwargs: _report(
            "status",
            "LATEST_SNAPSHOTS",
            [
                {
                    "root_slug": "uploads",
                    "snapshot_id": 7,
                    "generation": 2,
                    "status": "committed",
                }
            ],
        ),
    )
    client = TestClient(create_api_app())

    response = client.get("/api/analyze/catalog/status?root=uploads")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["action"] == "status"
    assert payload["data"]["sections"][0]["rows"][0]["generation"] == 2


def test_catalog_zero_byte_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        analyze_routes.CatalogZeroByteReportService,
        "run",
        lambda self, settings, **kwargs: _report(
            "zero-byte",
            "ZERO_BYTE_FILES",
            [
                {
                    "root_slug": "uploads",
                    "relative_path": "nested/empty.jpg",
                    "size_bytes": 0,
                }
            ],
        ),
    )
    client = TestClient(create_api_app())

    response = client.get("/api/analyze/catalog/zero-byte?root=uploads&limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["action"] == "zero-byte"
    assert payload["data"]["sections"][0]["rows"][0]["relative_path"] == "nested/empty.jpg"


def test_catalog_scan_job_routes_return_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        analyze_routes.CatalogWorkflowService,
        "get_scan_job",
        lambda self, settings: {
            "jobId": "catalog-scan-1",
            "jobType": "catalog_inventory_scan",
            "state": "running",
            "summary": "Catalog scan is running.",
            "result": {"progress": {"percent": 42.5}},
        },
    )
    monkeypatch.setattr(
        analyze_routes.CatalogWorkflowService,
        "start_scan",
        lambda self, settings, *, force: {
            "jobId": "catalog-scan-2",
            "jobType": "catalog_inventory_scan",
            "state": "pending",
            "summary": "Catalog scan queued.",
            "result": {"force": force},
        },
    )
    client = TestClient(create_api_app())

    current_response = client.get("/api/analyze/catalog/scan-job")
    start_response = client.post("/api/analyze/catalog/scan-job/start", json={"force": True})

    assert current_response.status_code == 200
    assert current_response.json()["data"]["result"]["progress"]["percent"] == 42.5
    assert start_response.status_code == 200
    assert start_response.json()["data"]["result"]["force"] is True
