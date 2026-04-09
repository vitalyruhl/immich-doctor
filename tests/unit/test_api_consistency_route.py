from __future__ import annotations

from fastapi.testclient import TestClient

from immich_doctor.api.app import create_api_app
from immich_doctor.api.routes import consistency as consistency_routes


class _Result:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def to_dict(self) -> dict[str, object]:
        return self.payload


def test_missing_asset_scan_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        consistency_routes.MissingAssetReferenceService,
        "scan",
        lambda self, settings, **kwargs: _Result(
            {
                "domain": "consistency.missing_asset_references",
                "action": "scan",
                "status": "FAIL",
                "summary": "1 missing asset reference found.",
                "findings": [{"asset_id": "asset-1", "status": "missing_on_disk"}],
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


def test_catalog_consistency_job_routes_return_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        consistency_routes.CatalogWorkflowService,
        "get_consistency_job",
        lambda self, settings: {
            "jobId": "catalog-consistency-1",
            "jobType": "catalog_consistency_validation",
            "state": "running",
            "summary": "Catalog consistency validation is running.",
            "result": {"progress": {"percent": 66.7}},
        },
    )
    monkeypatch.setattr(
        consistency_routes.CatalogWorkflowService,
        "start_consistency",
        lambda self, settings, *, force: {
            "jobId": "catalog-consistency-2",
            "jobType": "catalog_consistency_validation",
            "state": "pending",
            "summary": "Catalog consistency validation queued.",
            "result": {"force": force},
        },
    )
    client = TestClient(create_api_app())

    current_response = client.get("/api/consistency/catalog")
    start_response = client.post("/api/consistency/catalog/start", json={"force": True})

    assert current_response.status_code == 200
    assert current_response.json()["data"]["result"]["progress"]["percent"] == 66.7
    assert start_response.status_code == 200
    assert start_response.json()["data"]["result"]["force"] is True
