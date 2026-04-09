from __future__ import annotations

from fastapi.testclient import TestClient

from immich_doctor.api.app import create_api_app
from immich_doctor.api.routes import health as health_routes
from immich_doctor.services.dashboard_health import (
    DashboardHealthItem,
    DashboardHealthOverview,
    DashboardHealthStatus,
)


def test_health_overview_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        health_routes.DashboardHealthService,
        "run",
        lambda self, settings: DashboardHealthOverview(
            generatedAt="2026-04-09T10:00:00+00:00",
            overallStatus=DashboardHealthStatus.UNKNOWN,
            items=[
                DashboardHealthItem(
                    id=item_id,
                    title=item_id,
                    status=DashboardHealthStatus.UNKNOWN,
                    summary="not loaded",
                    details="not loaded",
                    updatedAt="2026-04-09T10:00:00+00:00",
                    blocking=False,
                    source="test",
                )
                for item_id in (
                    "immich-configured",
                    "immich-reachable",
                    "db-reachability",
                    "storage-reachability",
                    "consistency-readiness",
                    "path-readiness",
                    "backup-readiness",
                    "scheduler-runtime-readiness",
                )
            ],
        ),
    )

    client = TestClient(create_api_app())

    response = client.get("/api/health/overview")

    assert response.status_code == 200
    payload = response.json()

    assert payload["source"] == "backend"
    assert payload["mocked"] is False
    assert payload["data"]["overallStatus"] == "unknown"
    assert payload["data"]["generatedAt"]
    assert len(payload["data"]["items"]) == 8
    assert {item["id"] for item in payload["data"]["items"]} == {
        "immich-configured",
        "immich-reachable",
        "db-reachability",
        "storage-reachability",
        "consistency-readiness",
        "path-readiness",
        "backup-readiness",
        "scheduler-runtime-readiness",
    }


def test_database_overview_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        health_routes.DatabaseOverviewService,
        "run",
        lambda self, settings: {
            "generatedAt": "2026-04-09T10:00:00+00:00",
            "connectivity": {
                "status": "ok",
                "summary": "Database access works.",
                "details": "Round-trip query passed.",
                "host": "postgres",
                "port": 5432,
                "databaseName": "immich",
                "accessWorks": True,
                "error": None,
                "engine": "PostgreSQL",
                "serverVersion": "14.10",
                "serverVersionNum": "140010",
                "serverVersionRaw": "PostgreSQL 14.10",
                "serverVersionError": None,
            },
            "immich": {
                "status": "ok",
                "summary": "Detected Immich 2.5.6.",
                "details": "Version history is available.",
                "productVersionCurrent": "2.5.6",
                "productVersionConfidence": "high",
                "productVersionSource": "version_history",
                "supportStatus": "supported",
                "schemaGenerationKey": "immich_schema:key",
                "riskFlags": [],
                "notes": [],
            },
            "compatibility": {
                "status": "ok",
                "summary": "Detected Immich 2.5.6 matches the tested target.",
                "details": "Schema support is modeled.",
                "testedAgainstImmichVersion": "2.5.6",
            },
            "relatedFindings": {
                "status": "warning",
                "summary": "Consistency findings are waiting for a current storage index.",
                "details": "Open the Consistency page for details.",
                "route": "/consistency",
            },
            "testedAgainstImmichVersion": "2.5.6",
        },
    )

    client = TestClient(create_api_app())
    response = client.get("/api/health/database")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["connectivity"]["serverVersion"] == "14.10"
    assert payload["data"]["immich"]["productVersionCurrent"] == "2.5.6"
    assert payload["data"]["relatedFindings"]["route"] == "/consistency"
