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
    monkeypatch.setattr(
        analyze_routes.CatalogWorkflowService,
        "pause_scan",
        lambda self, settings: {
            "jobId": "catalog-scan-2",
            "jobType": "catalog_inventory_scan",
            "state": "pausing",
            "summary": "Pause requested.",
            "result": {"runtime": {"scanState": "pausing"}},
        },
    )
    monkeypatch.setattr(
        analyze_routes.CatalogWorkflowService,
        "resume_scan",
        lambda self, settings: {
            "jobId": "catalog-scan-2",
            "jobType": "catalog_inventory_scan",
            "state": "resuming",
            "summary": "Resume requested.",
            "result": {"runtime": {"scanState": "resuming"}},
        },
    )
    monkeypatch.setattr(
        analyze_routes.CatalogWorkflowService,
        "stop_scan",
        lambda self, settings: {
            "jobId": "catalog-scan-2",
            "jobType": "catalog_inventory_scan",
            "state": "stopping",
            "summary": "Stop requested.",
            "result": {"runtime": {"scanState": "stopping"}},
        },
    )
    monkeypatch.setattr(
        analyze_routes.CatalogWorkflowService,
        "pause_scan_actor",
        lambda self, settings, *, actor_id: {
            "jobId": "catalog-scan-2",
            "jobType": "catalog_inventory_scan",
            "state": "running",
            "summary": f"Pause requested for {actor_id}.",
            "result": {"runtime": {"scanState": "running", "actors": [{"actorId": actor_id}]}},
        },
    )
    monkeypatch.setattr(
        analyze_routes.CatalogWorkflowService,
        "resume_scan_actor",
        lambda self, settings, *, actor_id: {
            "jobId": "catalog-scan-2",
            "jobType": "catalog_inventory_scan",
            "state": "running",
            "summary": f"Resume requested for {actor_id}.",
            "result": {"runtime": {"scanState": "running", "actors": [{"actorId": actor_id}]}},
        },
    )
    monkeypatch.setattr(
        analyze_routes.CatalogWorkflowService,
        "stop_scan_actor",
        lambda self, settings, *, actor_id: {
            "jobId": "catalog-scan-2",
            "jobType": "catalog_inventory_scan",
            "state": "running",
            "summary": f"Stop requested for {actor_id}.",
            "result": {"runtime": {"scanState": "running", "actors": [{"actorId": actor_id}]}},
        },
    )
    monkeypatch.setattr(
        analyze_routes.CatalogWorkflowService,
        "request_scan_worker_resize",
        lambda self, settings, *, workers: {
            "jobId": "catalog-scan-2",
            "jobType": "catalog_inventory_scan",
            "state": "running",
            "summary": (
                "Runtime worker resizing is not supported safely in the current architecture."
            ),
            "result": {
                "workerResize": {
                    "supported": False,
                    "semantics": "next_run_only",
                    "requestedWorkerCount": workers,
                }
            },
        },
    )
    client = TestClient(create_api_app())

    current_response = client.get("/api/analyze/catalog/scan-job")
    start_response = client.post("/api/analyze/catalog/scan-job/start", json={"force": True})
    pause_response = client.post("/api/analyze/catalog/scan-job/pause")
    resume_response = client.post("/api/analyze/catalog/scan-job/resume")
    stop_response = client.post("/api/analyze/catalog/scan-job/stop")
    actor_pause_response = client.post("/api/analyze/catalog/scan-job/actors/worker-1/pause")
    actor_resume_response = client.post("/api/analyze/catalog/scan-job/actors/worker-1/resume")
    actor_stop_response = client.post("/api/analyze/catalog/scan-job/actors/worker-1/stop")
    workers_response = client.post("/api/analyze/catalog/scan-job/workers", json={"workers": 8})

    assert current_response.status_code == 200
    assert current_response.json()["data"]["result"]["progress"]["percent"] == 42.5
    assert start_response.status_code == 200
    assert start_response.json()["data"]["result"]["force"] is True
    assert pause_response.status_code == 200
    assert pause_response.json()["data"]["state"] == "pausing"
    assert resume_response.status_code == 200
    assert resume_response.json()["data"]["state"] == "resuming"
    assert stop_response.status_code == 200
    assert stop_response.json()["data"]["state"] == "stopping"
    assert actor_pause_response.status_code == 200
    assert (
        actor_pause_response.json()["data"]["result"]["runtime"]["actors"][0]["actorId"]
        == "worker-1"
    )
    assert actor_resume_response.status_code == 200
    assert actor_stop_response.status_code == 200
    assert workers_response.status_code == 200
    assert workers_response.json()["data"]["result"]["workerResize"]["semantics"] == "next_run_only"


def test_empty_folder_scan_route_returns_expected_shape(tmp_path, monkeypatch) -> None:
    storage = tmp_path / "storage"
    uploads = storage / "upload"
    thumbs = storage / "thumbs"
    profile = storage / "profile"
    video = storage / "encoded-video"
    quarantine = tmp_path / "quarantine"
    manifests = tmp_path / "manifests"
    reports = tmp_path / "reports"
    logs = tmp_path / "logs"
    tmp_dir = tmp_path / "tmp"
    for path in [
        storage,
        uploads,
        thumbs,
        profile,
        video,
        quarantine,
        manifests,
        reports,
        logs,
        tmp_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)
    (uploads / "empty-dir").mkdir()

    monkeypatch.setenv("IMMICH_STORAGE_PATH", str(storage))
    monkeypatch.setenv("IMMICH_UPLOADS_PATH", str(uploads))
    monkeypatch.setenv("IMMICH_THUMBS_PATH", str(thumbs))
    monkeypatch.setenv("IMMICH_PROFILE_PATH", str(profile))
    monkeypatch.setenv("IMMICH_VIDEO_PATH", str(video))
    monkeypatch.setenv("QUARANTINE_PATH", str(quarantine))
    monkeypatch.setenv("MANIFESTS_PATH", str(manifests))
    monkeypatch.setenv("REPORTS_PATH", str(reports))
    monkeypatch.setenv("LOG_PATH", str(logs))
    monkeypatch.setenv("TMP_PATH", str(tmp_dir))

    client = TestClient(create_api_app())

    response = client.post("/api/analyze/storage/empty-folders/scan", json={"root": "uploads"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["domain"] == "storage.empty-folders"
    assert payload["data"]["total_empty_dirs"] == 1
    assert payload["data"]["findings"][0]["relative_path"] == "empty-dir"


def test_empty_folder_quarantine_routes_round_trip(tmp_path, monkeypatch) -> None:
    storage = tmp_path / "storage"
    uploads = storage / "upload"
    thumbs = storage / "thumbs"
    profile = storage / "profile"
    video = storage / "encoded-video"
    quarantine = tmp_path / "quarantine"
    manifests = tmp_path / "manifests"
    reports = tmp_path / "reports"
    logs = tmp_path / "logs"
    tmp_dir = tmp_path / "tmp"
    for path in [
        storage,
        uploads,
        thumbs,
        profile,
        video,
        quarantine,
        manifests,
        reports,
        logs,
        tmp_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)
    (uploads / "empty-dir").mkdir()

    monkeypatch.setenv("IMMICH_STORAGE_PATH", str(storage))
    monkeypatch.setenv("IMMICH_UPLOADS_PATH", str(uploads))
    monkeypatch.setenv("IMMICH_THUMBS_PATH", str(thumbs))
    monkeypatch.setenv("IMMICH_PROFILE_PATH", str(profile))
    monkeypatch.setenv("IMMICH_VIDEO_PATH", str(video))
    monkeypatch.setenv("QUARANTINE_PATH", str(quarantine))
    monkeypatch.setenv("MANIFESTS_PATH", str(manifests))
    monkeypatch.setenv("REPORTS_PATH", str(reports))
    monkeypatch.setenv("LOG_PATH", str(logs))
    monkeypatch.setenv("TMP_PATH", str(tmp_dir))

    client = TestClient(create_api_app())

    quarantine_response = client.post(
        "/api/analyze/storage/empty-folders/quarantine",
        json={"paths": ["empty-dir"], "quarantine_all": False, "dry_run": False},
    )
    assert quarantine_response.status_code == 200
    session_id = quarantine_response.json()["data"]["session_id"]
    assert quarantine_response.json()["data"]["quarantined_count"] == 1

    list_response = client.get("/api/analyze/storage/empty-folders/quarantine-list")
    assert list_response.status_code == 200
    assert list_response.json()["data"]["count"] == 1

    restore_response = client.post(
        f"/api/analyze/storage/empty-folders/quarantine/{session_id}/restore",
        json={"restore_all": True, "paths": []},
    )
    assert restore_response.status_code == 200
    assert restore_response.json()["data"]["restored_count"] == 1


def test_db_corruption_scan_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        analyze_routes.DbCorruptionScanService,
        "run",
        lambda self, settings: ValidationReport(
            domain="db.corruption",
            action="scan",
            summary="Database corruption scan detected 1 invalid user indexes.",
            checks=[
                CheckResult(
                    name="postgres_connection",
                    status=CheckStatus.PASS,
                    message="PostgreSQL connection established.",
                )
            ],
            sections=[
                ValidationSection(
                    name="INVALID_USER_INDEXES",
                    status=CheckStatus.FAIL,
                    rows=[
                        {
                            "schema_name": "public",
                            "index_name": "memory_asset_pkey",
                            "table_name": "memory_asset",
                            "indisvalid": False,
                            "indisready": False,
                        }
                    ],
                )
            ],
        ),
    )
    client = TestClient(create_api_app())

    response = client.post("/api/analyze/db/corruption/scan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["domain"] == "db.corruption"
    assert payload["data"]["sections"][0]["rows"][0]["index_name"] == "memory_asset_pkey"
