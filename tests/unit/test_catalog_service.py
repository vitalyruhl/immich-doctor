from pathlib import Path

from immich_doctor.catalog.paths import catalog_database_path
from immich_doctor.catalog.service import (
    CatalogInventoryScanService,
    CatalogStatusService,
    CatalogZeroByteReportService,
)
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckStatus


def _settings(tmp_path: Path, *, uploads: Path) -> AppSettings:
    return AppSettings(
        _env_file=None,
        immich_uploads_path=uploads,
        reports_path=tmp_path / "reports",
        manifests_path=tmp_path / "manifests",
        quarantine_path=tmp_path / "quarantine",
        logs_path=tmp_path / "logs",
        tmp_path=tmp_path / "tmp",
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
