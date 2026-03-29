from __future__ import annotations

from fastapi.testclient import TestClient

from immich_doctor.api.app import create_api_app
from immich_doctor.api.routes import consistency as consistency_routes


class _Result:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def to_dict(self) -> dict[str, object]:
        return self.payload


class _ScanManager:
    def __init__(
        self,
        *,
        status_payload: dict[str, object] | None = None,
        findings_payload: dict[str, object] | None = None,
    ) -> None:
        self.status_payload = status_payload or {
            "domain": "consistency.missing_asset_references",
            "action": "scan_status",
            "status": "SKIP",
            "summary": "No completed missing asset reference scan is available yet.",
            "scan_state": "idle",
            "active_scan": None,
            "latest_completed": None,
            "checks": [],
            "metadata": {"has_completed_result": False},
            "recommendations": [],
        }
        self.findings_payload = findings_payload or {
            "domain": "consistency.missing_asset_references",
            "action": "scan",
            "status": "SKIP",
            "summary": "No completed missing asset reference scan is available yet.",
            "findings": [],
            "metadata": {"has_completed_result": False},
            "recommendations": [],
        }

    def get_status(self, settings):
        return _Result(self.status_payload)

    def start_scan(self, settings):
        return _Result(self.status_payload)

    def get_latest_findings(self, settings, **kwargs):
        return self.findings_payload


def test_missing_asset_scan_status_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        consistency_routes,
        "_missing_asset_scan_manager",
        lambda request: _ScanManager(
            status_payload={
                "domain": "consistency.missing_asset_references",
                "action": "scan_status",
                "status": "WARN",
                "summary": "Missing asset reference scan is running.",
                "scan_state": "running",
                "active_scan": {"scan_id": "scan-1", "state": "running"},
                "latest_completed": None,
                "checks": [],
                "metadata": {"has_completed_result": False},
                "recommendations": [],
            }
        ),
    )
    client = TestClient(create_api_app())

    response = client.get("/api/consistency/missing-asset-references/status")

    assert response.status_code == 200
    assert response.json()["data"]["scan_state"] == "running"


def test_missing_asset_trigger_scan_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        consistency_routes,
        "_missing_asset_scan_manager",
        lambda request: _ScanManager(
            status_payload={
                "domain": "consistency.missing_asset_references",
                "action": "scan_status",
                "status": "WARN",
                "summary": "Missing asset reference scan is queued.",
                "scan_state": "pending",
                "active_scan": {"scan_id": "scan-2", "state": "pending"},
                "latest_completed": {
                    "scan_id": "scan-1",
                    "completed_at": "2026-03-28T08:00:00+00:00",
                },
                "checks": [],
                "metadata": {"has_completed_result": True},
                "recommendations": [],
            }
        ),
    )
    client = TestClient(create_api_app())

    response = client.post("/api/consistency/missing-asset-references/scan")

    assert response.status_code == 200
    assert response.json()["data"]["scan_state"] == "pending"
    assert response.json()["data"]["active_scan"]["scan_id"] == "scan-2"


def test_missing_asset_scan_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        consistency_routes,
        "_missing_asset_scan_manager",
        lambda request: _ScanManager(
            findings_payload={
                "domain": "consistency.missing_asset_references",
                "action": "scan",
                "status": "FAIL",
                "summary": "1 missing asset reference found.",
                "findings": [{"asset_id": "asset-1", "status": "missing_on_disk"}],
                "metadata": {
                    "scan_state": "completed",
                    "has_completed_result": True,
                },
                "recommendations": [],
            }
        ),
    )
    client = TestClient(create_api_app())

    response = client.get("/api/consistency/missing-asset-references/findings")

    assert response.status_code == 200
    assert response.json()["data"]["findings"][0]["status"] == "missing_on_disk"


def test_missing_asset_preview_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        consistency_routes.MissingAssetReferenceService,
        "preview",
        lambda self, settings, **kwargs: _Result(
            {
                "domain": "consistency.missing_asset_references",
                "action": "preview",
                "status": "WARN",
                "summary": "Preview planned 1 removal.",
                "repair_run_id": "repair-run-1",
                "selected_findings": [{"asset_id": "asset-1"}],
            }
        ),
    )
    client = TestClient(create_api_app())

    response = client.post(
        "/api/consistency/missing-asset-references/preview",
        json={"asset_ids": ["asset-1"], "select_all": False},
    )

    assert response.status_code == 200
    assert response.json()["data"]["repair_run_id"] == "repair-run-1"


def test_missing_asset_apply_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        consistency_routes.MissingAssetReferenceService,
        "apply",
        lambda self, settings, **kwargs: _Result(
            {
                "domain": "consistency.missing_asset_references",
                "action": "apply",
                "status": "PASS",
                "summary": "Apply removed 1 asset.",
                "repair_run_id": "repair-run-1",
                "items": [{"asset_id": "asset-1", "status": "applied"}],
            }
        ),
    )
    client = TestClient(create_api_app())

    response = client.post(
        "/api/consistency/missing-asset-references/apply",
        json={"repair_run_id": "repair-run-1"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["status"] == "applied"


def test_missing_asset_restore_points_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        consistency_routes.MissingAssetReferenceService,
        "list_restore_points",
        lambda self, settings: _Result(
            {
                "domain": "consistency.missing_asset_references",
                "action": "restore_points",
                "status": "PASS",
                "summary": "1 restore point available.",
                "items": [{"restore_point_id": "rp-1", "status": "available"}],
            }
        ),
    )
    client = TestClient(create_api_app())

    response = client.get("/api/consistency/missing-asset-references/restore-points")

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["restore_point_id"] == "rp-1"


def test_missing_asset_restore_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        consistency_routes.MissingAssetReferenceService,
        "restore",
        lambda self, settings, **kwargs: _Result(
            {
                "domain": "consistency.missing_asset_references",
                "action": "restore",
                "status": "PASS",
                "summary": "Restored 1 point.",
                "repair_run_id": "restore-run-1",
                "items": [{"asset_id": "asset-1", "status": "restored"}],
            }
        ),
    )
    client = TestClient(create_api_app())

    response = client.post(
        "/api/consistency/missing-asset-references/restore-points/restore",
        json={"restore_point_ids": ["rp-1"], "select_all": False},
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["status"] == "restored"


def test_missing_asset_restore_point_delete_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        consistency_routes.MissingAssetReferenceService,
        "delete_restore_points",
        lambda self, settings, **kwargs: _Result(
            {
                "domain": "consistency.missing_asset_references",
                "action": "delete_restore_points",
                "status": "PASS",
                "summary": "Deleted 1 restore point.",
                "items": [{"restore_point_id": "rp-1", "status": "deleted"}],
            }
        ),
    )
    client = TestClient(create_api_app())

    response = client.post(
        "/api/consistency/missing-asset-references/restore-points/delete",
        json={"restore_point_ids": ["rp-1"], "select_all": False},
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["status"] == "deleted"
