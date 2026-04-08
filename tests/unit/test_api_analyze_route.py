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
