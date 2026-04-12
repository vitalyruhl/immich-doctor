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


def test_catalog_remediation_routes_return_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        consistency_routes.CatalogRemediationService,
        "load_cached_findings",
        lambda self, settings: {
            "domain": "consistency.catalog_remediation",
            "action": "scan",
            "status": "WARN",
            "summary": "Catalog remediation findings loaded.",
            "broken_db_originals": [
                {"asset_id": "asset-1", "classification": "missing_confirmed"}
            ],
            "zero_byte_findings": [
                {"finding_id": "zero-1", "classification": "zero_byte_upload_orphan"}
            ],
            "fuse_hidden_orphans": [
                {"finding_id": "fuse-1", "classification": "deletable_orphan"}
            ],
        },
    )
    monkeypatch.setattr(
        consistency_routes.CatalogRemediationService,
        "preview_broken_db_cleanup",
        lambda self, settings, **kwargs: _Result(
            {
                "domain": "consistency.catalog_remediation",
                "action": "preview",
                "status": "WARN",
                "finding_kind": "broken_db_original",
                "action_kind": "broken_db_cleanup",
                "summary": "Preview selected 1 broken DB original.",
                "repair_run_id": "repair-run-broken",
                "selected_items": [{"asset_id": "asset-1"}],
            }
        ),
    )
    monkeypatch.setattr(
        consistency_routes.CatalogRemediationService,
        "preview_broken_db_path_fix",
        lambda self, settings, **kwargs: _Result(
            {
                "domain": "consistency.catalog_remediation",
                "action": "preview",
                "status": "WARN",
                "finding_kind": "broken_db_original",
                "action_kind": "broken_db_path_fix",
                "summary": "Preview selected 1 path-fix item.",
                "repair_run_id": "repair-run-fix",
                "selected_items": [{"asset_id": "asset-2"}],
            }
        ),
    )
    monkeypatch.setattr(
        consistency_routes.CatalogRemediationService,
        "preview_zero_byte_files",
        lambda self, settings, **kwargs: _Result(
            {
                "domain": "consistency.catalog_remediation",
                "action": "preview",
                "status": "WARN",
                "finding_kind": "zero_byte_file",
                "action_kind": "zero_byte_delete",
                "summary": "Preview selected 1 zero-byte item.",
                "repair_run_id": "repair-run-zero",
                "selected_items": [{"finding_id": "zero-1"}],
            }
        ),
    )
    monkeypatch.setattr(
        consistency_routes.CatalogRemediationService,
        "preview_fuse_hidden_orphans",
        lambda self, settings, **kwargs: _Result(
            {
                "domain": "consistency.catalog_remediation",
                "action": "preview",
                "status": "WARN",
                "finding_kind": "fuse_hidden_orphan",
                "action_kind": "fuse_hidden_delete",
                "summary": "Preview selected 1 fuse-hidden orphan.",
                "repair_run_id": "repair-run-fuse",
                "selected_items": [{"finding_id": "fuse-1"}],
            }
        ),
    )
    monkeypatch.setattr(
        consistency_routes.CatalogRemediationService,
        "apply",
        lambda self, settings, **kwargs: _Result(
            {
                "domain": "consistency.catalog_remediation",
                "action": "apply",
                "status": "PASS",
                "finding_kind": "fuse_hidden_orphan",
                "action_kind": "fuse_hidden_delete",
                "summary": "Applied 1 remediation item.",
                "repair_run_id": "repair-run-fuse",
                "items": [{"finding_id": "fuse-1", "status": "applied"}],
            }
        ),
    )
    client = TestClient(create_api_app())

    scan_response = client.get("/api/consistency/catalog-remediation/findings")
    broken_preview_response = client.post(
        "/api/consistency/catalog-remediation/broken-db-originals/preview",
        json={"asset_ids": ["asset-1"], "select_all": False},
    )
    path_fix_preview_response = client.post(
        "/api/consistency/catalog-remediation/broken-db-originals/path-fix/preview",
        json={"asset_ids": ["asset-2"], "select_all": False},
    )
    zero_byte_preview_response = client.post(
        "/api/consistency/catalog-remediation/zero-byte-files/preview",
        json={"finding_ids": ["zero-1"], "select_all": False},
    )
    fuse_preview_response = client.post(
        "/api/consistency/catalog-remediation/fuse-hidden-orphans/preview",
        json={"finding_ids": ["fuse-1"], "select_all": False},
    )
    apply_response = client.post(
        "/api/consistency/catalog-remediation/apply",
        json={"repair_run_id": "repair-run-fuse"},
    )
    monkeypatch.setattr(
        consistency_routes.CatalogRemediationService,
        "execute_storage_finding_action",
        lambda self, settings, **kwargs: {
            "domain": "consistency.catalog_remediation",
            "action": "apply",
            "status": "PASS",
            "finding_kind": "fuse_hidden_orphan",
            "action_kind": "fuse_hidden_delete",
            "summary": "Applied 1 direct remediation item.",
            "items": [{"finding_id": "fuse-1", "status": "applied"}],
        },
    )
    direct_apply_response = client.post(
        "/api/consistency/catalog-remediation/findings/apply-direct",
        json={"finding_ids": ["fuse-1"], "action_kind": "fuse_hidden_delete"},
    )

    assert scan_response.status_code == 200
    assert (
        scan_response.json()["data"]["broken_db_originals"][0]["classification"]
        == "missing_confirmed"
    )
    assert (
        scan_response.json()["data"]["zero_byte_findings"][0]["classification"]
        == "zero_byte_upload_orphan"
    )
    assert broken_preview_response.status_code == 200
    assert broken_preview_response.json()["data"]["repair_run_id"] == "repair-run-broken"
    assert path_fix_preview_response.status_code == 200
    assert path_fix_preview_response.json()["data"]["action_kind"] == "broken_db_path_fix"
    assert zero_byte_preview_response.status_code == 200
    assert zero_byte_preview_response.json()["data"]["repair_run_id"] == "repair-run-zero"
    assert fuse_preview_response.status_code == 200
    assert fuse_preview_response.json()["data"]["repair_run_id"] == "repair-run-fuse"
    assert apply_response.status_code == 200
    assert apply_response.json()["data"]["items"][0]["status"] == "applied"
    assert direct_apply_response.status_code == 200
    assert direct_apply_response.json()["data"]["items"][0]["status"] == "applied"


def test_catalog_remediation_group_routes_return_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        consistency_routes.CatalogRemediationService,
        "load_group_overview",
        lambda self, settings: {
            "summary": "Catalog remediation findings loaded.",
            "groups": [
                {
                    "key": "broken-db",
                    "title": "DB originals missing in storage",
                    "description": "Broken original references.",
                    "count": 12,
                }
            ],
        },
    )
    monkeypatch.setattr(
        consistency_routes.CatalogRemediationService,
        "list_group_findings",
        lambda self, settings, **kwargs: {
            "group_key": kwargs["group_key"],
            "offset": kwargs["offset"],
            "limit": kwargs["limit"],
            "total": 12,
            "items": [
                {
                    "finding_id": "broken-1",
                    "group_key": "broken-db",
                    "title": "missing.jpg",
                }
            ],
        },
    )
    monkeypatch.setattr(
        consistency_routes.CatalogRemediationService,
        "get_finding_detail",
        lambda self, settings, **kwargs: {
            "group_key": kwargs["group_key"],
            "finding_id": kwargs["finding_id"],
            "title": "missing.jpg",
            "details": [{"label": "Expected DB path", "value": "/upload/missing.jpg"}],
        },
    )
    client = TestClient(create_api_app())

    overview_response = client.get("/api/consistency/catalog-remediation/groups")
    list_response = client.get(
        "/api/consistency/catalog-remediation/groups/broken-db?limit=20&offset=0"
    )
    detail_response = client.get(
        "/api/consistency/catalog-remediation/groups/broken-db/items/broken-1"
    )

    assert overview_response.status_code == 200
    assert overview_response.json()["data"]["groups"][0]["count"] == 12
    assert list_response.status_code == 200
    assert list_response.json()["data"]["items"][0]["finding_id"] == "broken-1"
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["details"][0]["label"] == "Expected DB path"
