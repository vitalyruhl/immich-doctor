from pathlib import Path

from immich_doctor.catalog.paths import catalog_database_path
from immich_doctor.catalog.service import (
    CatalogInventoryScanService,
    CatalogRootRegistry,
    CatalogStatusService,
    CatalogZeroByteReportService,
)
from immich_doctor.catalog.store import CatalogStore
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckStatus


def _settings(tmp_path: Path, *, uploads: Path, catalog_scan_workers: int = 4) -> AppSettings:
    return AppSettings(
        _env_file=None,
        immich_uploads_path=uploads,
        reports_path=tmp_path / "reports",
        manifests_path=tmp_path / "manifests",
        quarantine_path=tmp_path / "quarantine",
        logs_path=tmp_path / "logs",
        tmp_path=tmp_path / "tmp",
        catalog_scan_workers=catalog_scan_workers,
    )


def test_catalog_scan_indexes_files_and_reports_zero_byte(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    nested = uploads / "nested"
    nested.mkdir(parents=True, exist_ok=True)
    (uploads / "empty.jpg").write_bytes(b"")
    (nested / "asset.txt").write_bytes(b"hello")

    settings = _settings(tmp_path, uploads=uploads)

    scan_report = CatalogInventoryScanService().run(
        settings,
        root_slug="uploads",
        resume_session_id=None,
        max_files=None,
    )

    assert scan_report.overall_status == CheckStatus.PASS
    assert catalog_database_path(settings).exists()

    snapshot_section = next(
        section for section in scan_report.sections if section.name == "SCAN_SNAPSHOT"
    )
    assert snapshot_section.rows[0]["status"] == "committed"
    assert snapshot_section.rows[0]["item_count"] == 2
    assert snapshot_section.rows[0]["zero_byte_count"] == 1

    status_report = CatalogStatusService().run(settings, root_slug="uploads")
    latest_snapshot_section = next(
        section for section in status_report.sections if section.name == "LATEST_SNAPSHOTS"
    )
    assert latest_snapshot_section.rows[0]["item_count"] == 2
    assert latest_snapshot_section.rows[0]["zero_byte_count"] == 1
    assert latest_snapshot_section.rows[0]["snapshot_current"] == 1

    zero_byte_report = CatalogZeroByteReportService().run(
        settings,
        root_slug="uploads",
        limit=10,
    )
    zero_byte_section = next(
        section for section in zero_byte_report.sections if section.name == "ZERO_BYTE_FILES"
    )
    assert zero_byte_section.status == CheckStatus.FAIL
    assert zero_byte_section.rows == [
        {
            "root_slug": "uploads",
            "relative_path": "empty.jpg",
            "file_name": "empty.jpg",
            "extension": ".jpg",
            "size_bytes": 0,
            "modified_at_fs": zero_byte_section.rows[0]["modified_at_fs"],
            "snapshot_id": snapshot_section.rows[0]["id"],
            "generation": 1,
        }
    ]


def test_catalog_scan_can_resume_paused_session(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    (uploads / "dir-a").mkdir(parents=True, exist_ok=True)
    (uploads / "dir-b").mkdir(parents=True, exist_ok=True)
    (uploads / "dir-a" / "asset-a.jpg").write_bytes(b"a")
    (uploads / "dir-b" / "asset-b.jpg").write_bytes(b"b")

    settings = _settings(tmp_path, uploads=uploads)

    paused_report = CatalogInventoryScanService().run(
        settings,
        root_slug="uploads",
        resume_session_id=None,
        max_files=1,
    )

    assert paused_report.overall_status == CheckStatus.WARN
    session_section = next(
        section for section in paused_report.sections if section.name == "SCAN_SESSION"
    )
    assert session_section.rows[0]["status"] == "paused"
    session_id = str(session_section.rows[0]["id"])

    resumed_report = CatalogInventoryScanService().run(
        settings,
        root_slug=None,
        resume_session_id=session_id,
        max_files=None,
    )

    assert resumed_report.overall_status == CheckStatus.PASS
    resumed_snapshot = next(
        section for section in resumed_report.sections if section.name == "SCAN_SNAPSHOT"
    )
    assert resumed_snapshot.rows[0]["status"] == "committed"
    assert resumed_snapshot.rows[0]["item_count"] == 2


def test_catalog_registry_scan_roots_skip_overlapping_parent_paths(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        immich_library_root=tmp_path / "storage",
        immich_uploads_path=tmp_path / "storage" / "upload",
        immich_thumbs_path=tmp_path / "storage" / "thumbs",
        immich_profile_path=tmp_path / "storage" / "profile",
        immich_video_path=tmp_path / "storage" / "encoded-video",
    )

    scan_roots = CatalogRootRegistry().scan_roots(settings)

    assert [root.slug for root in scan_roots] == ["uploads", "thumbs", "profile", "video"]


def test_catalog_scan_reports_prepare_phase_and_fixed_directory_total(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    (uploads / "a" / "b").mkdir(parents=True, exist_ok=True)
    (uploads / "a" / "asset-a.jpg").write_bytes(b"a")
    (uploads / "a" / "b" / "asset-b.jpg").write_bytes(b"b")

    settings = _settings(tmp_path, uploads=uploads)
    progress_payloads: list[dict[str, object]] = []

    CatalogInventoryScanService().run(
        settings,
        root_slug="uploads",
        resume_session_id=None,
        max_files=None,
        progress_callback=progress_payloads.append,
    )

    prepare_updates = [
        payload for payload in progress_payloads if payload.get("phase") == "prepare"
    ]
    scan_updates = [payload for payload in progress_payloads if payload.get("phase") == "scan"]

    assert prepare_updates
    assert scan_updates
    assert prepare_updates[-1]["directoriesTotal"] == 3
    assert {payload["directoriesTotal"] for payload in scan_updates} == {3}
    assert scan_updates[-1]["percent"] == 100.0


def test_catalog_status_reports_missing_effective_root_coverage(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    uploads = storage / "upload"
    thumbs = storage / "thumbs"
    profile = storage / "profile"
    video = storage / "encoded-video"
    uploads.mkdir(parents=True, exist_ok=True)
    thumbs.mkdir(parents=True, exist_ok=True)
    profile.mkdir(parents=True, exist_ok=True)
    video.mkdir(parents=True, exist_ok=True)
    (uploads / "asset.jpg").write_bytes(b"asset")

    settings = AppSettings(
        _env_file=None,
        immich_library_root=storage,
        immich_uploads_path=uploads,
        immich_thumbs_path=thumbs,
        immich_profile_path=profile,
        immich_video_path=video,
        reports_path=tmp_path / "reports",
        manifests_path=tmp_path / "manifests",
        quarantine_path=tmp_path / "quarantine",
        logs_path=tmp_path / "logs",
        tmp_path=tmp_path / "tmp",
    )

    CatalogInventoryScanService().run(
        settings,
        root_slug="uploads",
        resume_session_id=None,
        max_files=None,
    )

    status_report = CatalogStatusService().run(settings, root_slug=None)
    scan_coverage = status_report.metadata["scanCoverage"]

    assert scan_coverage["effectiveRootSlugs"] == ["uploads", "thumbs", "profile", "video"]
    assert scan_coverage["currentRootSlugs"] == ["uploads"]
    assert scan_coverage["staleRootSlugs"] == []
    assert scan_coverage["missingRootSlugs"] == ["thumbs", "profile", "video"]
    assert scan_coverage["requiresScan"] is True


def test_catalog_status_marks_snapshots_stale_after_root_path_change(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    (uploads / "asset.jpg").write_bytes(b"asset")
    settings = _settings(tmp_path, uploads=uploads)

    CatalogInventoryScanService().run(
        settings,
        root_slug="uploads",
        resume_session_id=None,
        max_files=None,
    )

    moved_uploads = tmp_path / "uploads-moved"
    moved_uploads.mkdir(parents=True, exist_ok=True)
    moved_settings = _settings(tmp_path, uploads=moved_uploads)

    status_report = CatalogStatusService().run(moved_settings, root_slug="uploads")
    latest_snapshot = next(
        section for section in status_report.sections if section.name == "LATEST_SNAPSHOTS"
    ).rows[0]
    scan_coverage = status_report.metadata["scanCoverage"]

    assert latest_snapshot["snapshot_id"] is not None
    assert latest_snapshot["snapshot_current"] == 0
    assert latest_snapshot["stale_reason"] == "root_configuration_changed"
    assert scan_coverage["currentRootSlugs"] == []
    assert scan_coverage["staleRootSlugs"] == ["uploads"]
    assert scan_coverage["requiresScan"] is True


def test_catalog_scan_worker_1_preserves_baseline_behavior(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    (uploads / "a").mkdir(parents=True, exist_ok=True)
    (uploads / "a" / "asset-a.jpg").write_bytes(b"a")
    (uploads / "asset-b.jpg").write_bytes(b"b")

    settings = _settings(tmp_path, uploads=uploads, catalog_scan_workers=1)

    report = CatalogInventoryScanService().run(
        settings,
        root_slug="uploads",
        resume_session_id=None,
        max_files=None,
    )

    assert report.overall_status == CheckStatus.PASS
    assert report.metadata["scan_workers"] == 1
    session_section = next(section for section in report.sections if section.name == "SCAN_SESSION")
    assert session_section.rows[0]["status"] == "completed"
    assert session_section.rows[0]["files_seen"] == 2


def test_catalog_scan_parallel_workers_no_duplicates_or_misses(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    expected_paths: set[str] = set()
    for directory in ["a", "a/b", "a/c", "d"]:
        (uploads / directory).mkdir(parents=True, exist_ok=True)
    for relative_path in [
        "root.txt",
        "a/asset-1.jpg",
        "a/b/asset-2.jpg",
        "a/b/asset-3.jpg",
        "a/c/asset-4.jpg",
        "d/asset-5.jpg",
    ]:
        (uploads / relative_path).write_bytes(relative_path.encode("utf-8"))
        expected_paths.add(relative_path)

    settings = _settings(tmp_path, uploads=uploads, catalog_scan_workers=4)

    report = CatalogInventoryScanService().run(
        settings,
        root_slug="uploads",
        resume_session_id=None,
        max_files=None,
    )

    assert report.overall_status == CheckStatus.PASS
    assert report.metadata["scan_workers"] == 4

    store = CatalogStore()
    files = store.list_latest_snapshot_files(settings, slug="uploads", limit=None)
    scanned_paths = [str(row["relative_path"]) for row in files]

    assert len(scanned_paths) == len(expected_paths)
    assert set(scanned_paths) == expected_paths
    assert len(scanned_paths) == len(set(scanned_paths))


def test_catalog_scan_progress_includes_worker_count(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    (uploads / "a" / "b").mkdir(parents=True, exist_ok=True)
    (uploads / "a" / "asset-a.jpg").write_bytes(b"a")
    (uploads / "a" / "b" / "asset-b.jpg").write_bytes(b"b")

    settings = _settings(tmp_path, uploads=uploads, catalog_scan_workers=3)
    progress_payloads: list[dict[str, object]] = []

    report = CatalogInventoryScanService().run(
        settings,
        root_slug="uploads",
        resume_session_id=None,
        max_files=None,
        progress_callback=progress_payloads.append,
    )

    assert report.metadata["scan_workers"] == 3
    prepare_updates = [
        payload for payload in progress_payloads if payload.get("phase") == "prepare"
    ]
    scan_updates = [payload for payload in progress_payloads if payload.get("phase") == "scan"]
    assert prepare_updates
    assert scan_updates
    assert {payload["configuredWorkerCount"] for payload in prepare_updates} == {3}
    assert {payload["configuredWorkerCount"] for payload in scan_updates} == {3}

    active_worker_counts = {payload["activeWorkerCount"] for payload in scan_updates}
    assert active_worker_counts
    assert all(isinstance(count, int) and count >= 0 for count in active_worker_counts)
