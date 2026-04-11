from pathlib import Path

from immich_doctor.catalog.consistency_service import CatalogConsistencyValidationService
from immich_doctor.catalog.service import CatalogInventoryScanService
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus


class _FakePostgres:
    def validate_connection(self, dsn: str, timeout_seconds: int) -> CheckResult:
        del dsn, timeout_seconds
        return CheckResult(
            name="postgres_connection",
            status=CheckStatus.PASS,
            message="PostgreSQL connection established.",
        )

    def list_all_assets_for_catalog_consistency(
        self,
        dsn: str,
        timeout_seconds: int,
    ) -> list[dict[str, object]]:
        del dsn, timeout_seconds
        return [
            {
                "id": "asset-keep",
                "type": "image",
                "ownerId": "user-1",
                "createdAt": "2026-04-09T09:00:00+00:00",
                "updatedAt": "2026-04-09T09:00:00+00:00",
                "originalFileName": "keep.jpg",
                "originalPath": "/usr/src/app/upload/upload/user-a/keep.jpg",
                "encodedVideoPath": "",
                "livePhotoVideoId": None,
            },
            {
                "id": "asset-missing",
                "type": "image",
                "ownerId": "user-1",
                "createdAt": "2026-04-09T09:01:00+00:00",
                "updatedAt": "2026-04-09T09:01:00+00:00",
                "originalFileName": "missing.jpg",
                "originalPath": "/usr/src/app/upload/upload/user-a/missing.jpg",
                "encodedVideoPath": "/usr/src/app/upload/encoded-video/user-a/missing.mp4",
                "livePhotoVideoId": None,
            },
        ]

    def list_all_asset_files_for_catalog_consistency(
        self,
        dsn: str,
        timeout_seconds: int,
    ) -> list[dict[str, object]]:
        del dsn, timeout_seconds
        return [
            {
                "id": "file-preview",
                "assetId": "asset-missing",
                "type": "preview",
                "path": "/usr/src/app/upload/thumbs/user-a/missing_preview.webp",
            },
            {
                "id": "file-thumbnail",
                "assetId": "asset-missing",
                "type": "thumbnail",
                "path": "/usr/src/app/upload/thumbs/user-a/missing_thumbnail.webp",
            },
            {
                "id": "file-sidecar",
                "assetId": "asset-missing",
                "type": "sidecar",
                "path": "/usr/src/app/upload/upload/user-a/missing.jpg.xmp",
            },
        ]


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        _env_file=None,
        immich_uploads_path=tmp_path / "upload",
        immich_thumbs_path=tmp_path / "thumbs",
        immich_profile_path=tmp_path / "profile",
        immich_video_path=tmp_path / "encoded-video",
        manifests_path=tmp_path / "manifests",
        reports_path=tmp_path / "reports",
        quarantine_path=tmp_path / "quarantine",
        logs_path=tmp_path / "logs",
        tmp_path=tmp_path / "tmp",
        db_host="postgres",
        db_name="immich",
        db_user="postgres",
        db_password="secret",
    )


def test_catalog_consistency_reports_db_storage_and_orphan_findings(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    for path in [
        settings.immich_uploads_path,
        settings.immich_thumbs_path,
        settings.immich_profile_path,
        settings.immich_video_path,
    ]:
        assert path is not None
        path.mkdir(parents=True, exist_ok=True)

    (settings.immich_uploads_path / "user-a").mkdir(parents=True, exist_ok=True)
    (settings.immich_thumbs_path / "user-a").mkdir(parents=True, exist_ok=True)
    (settings.immich_video_path / "user-a").mkdir(parents=True, exist_ok=True)

    (settings.immich_uploads_path / "user-a" / "keep.jpg").write_bytes(b"ok")
    (settings.immich_uploads_path / "user-a" / "lonely.jpg").write_bytes(b"lonely")
    (settings.immich_uploads_path / "user-a" / "missing.jpg.xmp").write_bytes(b"<xmp />")
    (settings.immich_uploads_path / "user-a" / "zero.jpg").write_bytes(b"")
    (settings.immich_thumbs_path / "user-a" / "missing_preview.webp").write_bytes(b"preview")
    (settings.immich_thumbs_path / "user-a" / "missing_thumbnail.webp").write_bytes(b"thumb")
    (settings.immich_video_path / "user-a" / "missing.mp4").write_bytes(b"video")

    for root_slug in ["uploads", "thumbs", "profile", "video"]:
        CatalogInventoryScanService().run(
            settings,
            root_slug=root_slug,
            resume_session_id=None,
            max_files=None,
        )

    service = CatalogConsistencyValidationService(postgres=_FakePostgres(), sample_limit=20)
    report = service.run(settings)

    totals = report.metadata["totals"]
    assert totals["dbOriginalsMissingOnStorage"] == 1
    assert totals["storageOriginalsMissingInDb"] == 2
    assert totals["orphanDerivativesWithoutOriginal"] == 4
    assert totals["zeroByteFiles"] == 1
    assert totals["filteredNoiseRemoved"] == 0
    assert totals["validMotionVideoComponents"] == 0
    assert totals["totalAssetsScanned"] == 2

    db_missing = next(
        section for section in report.sections if section.name == "DB_ORIGINALS_MISSING_ON_STORAGE"
    )
    assert db_missing.rows[0]["asset_id"] == "asset-missing"
    assert db_missing.rows[0]["asset_name"] == "missing.jpg"
    assert db_missing.rows[0]["relative_path"] == "user-a/missing.jpg"

    storage_missing = next(
        section for section in report.sections if section.name == "STORAGE_ORIGINALS_MISSING_IN_DB"
    )
    assert {row["relative_path"] for row in storage_missing.rows} == {
        "user-a/lonely.jpg",
        "user-a/zero.jpg",
    }

    orphan_rows = next(
        section
        for section in report.sections
        if section.name == "ORPHAN_DERIVATIVES_WITHOUT_ORIGINAL"
    ).rows
    assert {row["derivative_type"] for row in orphan_rows} == {
        "preview",
        "thumbnail",
        "encoded_video",
        "sidecar",
    }
    assert {row["relative_path"] for row in orphan_rows} == {
        "user-a/missing_preview.webp",
        "user-a/missing_thumbnail.webp",
        "user-a/missing.mp4",
        "user-a/missing.jpg.xmp",
    }

    zero_byte_rows = next(
        section for section in report.sections if section.name == "ZERO_BYTE_FILES"
    ).rows
    assert zero_byte_rows[0]["relative_path"] == "user-a/zero.jpg"
    assert report.metadata["latestScanCommittedAt"] is not None
    assert len(report.metadata["snapshotBasis"]) == 4


def test_catalog_consistency_waits_for_current_snapshots_after_root_change(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    for path in [
        settings.immich_uploads_path,
        settings.immich_thumbs_path,
        settings.immich_profile_path,
        settings.immich_video_path,
    ]:
        assert path is not None
        path.mkdir(parents=True, exist_ok=True)

    (settings.immich_uploads_path / "user-a").mkdir(parents=True, exist_ok=True)
    (settings.immich_uploads_path / "user-a" / "keep.jpg").write_bytes(b"ok")

    for root_slug in ["uploads", "thumbs", "profile", "video"]:
        CatalogInventoryScanService().run(
            settings,
            root_slug=root_slug,
            resume_session_id=None,
            max_files=None,
        )

    moved_settings = AppSettings(
        _env_file=None,
        immich_uploads_path=tmp_path / "upload-moved",
        immich_thumbs_path=settings.immich_thumbs_path,
        immich_profile_path=settings.immich_profile_path,
        immich_video_path=settings.immich_video_path,
        manifests_path=tmp_path / "manifests",
        reports_path=tmp_path / "reports",
        quarantine_path=tmp_path / "quarantine",
        logs_path=tmp_path / "logs",
        tmp_path=tmp_path / "tmp",
        db_host="postgres",
        db_name="immich",
        db_user="postgres",
        db_password="secret",
    )
    assert moved_settings.immich_uploads_path is not None
    moved_settings.immich_uploads_path.mkdir(parents=True, exist_ok=True)

    report = CatalogConsistencyValidationService(postgres=_FakePostgres(), sample_limit=20).run(
        moved_settings
    )

    assert report.overall_status == CheckStatus.FAIL
    assert report.metadata["requiresCurrentScan"] is True
    assert report.metadata["staleRootSlugs"] == ["uploads"]
    assert report.sections == []


class _FakeMotionPostgres:
    def validate_connection(self, dsn: str, timeout_seconds: int) -> CheckResult:
        del dsn, timeout_seconds
        return CheckResult(
            name="postgres_connection",
            status=CheckStatus.PASS,
            message="PostgreSQL connection established.",
        )

    def list_all_assets_for_catalog_consistency(
        self,
        dsn: str,
        timeout_seconds: int,
    ) -> list[dict[str, object]]:
        del dsn, timeout_seconds
        return [
            {
                "id": "image-1",
                "type": "image",
                "ownerId": "user-1",
                "createdAt": "2026-04-09T09:00:00+00:00",
                "updatedAt": "2026-04-09T09:00:00+00:00",
                "originalFileName": "live.jpg",
                "originalPath": "/usr/src/app/upload/upload/user-a/live.jpg",
                "encodedVideoPath": "",
                "livePhotoVideoId": "video-1",
            },
            {
                "id": "video-1",
                "type": "video",
                "ownerId": "user-1",
                "createdAt": "2026-04-09T09:00:01+00:00",
                "updatedAt": "2026-04-09T09:00:01+00:00",
                "originalFileName": "live-motion.mp4",
                "originalPath": "/usr/src/app/upload/encoded-video/user-a/live-motion-MP.mp4",
                "encodedVideoPath": "",
                "livePhotoVideoId": None,
            },
        ]

    def list_all_asset_files_for_catalog_consistency(
        self,
        dsn: str,
        timeout_seconds: int,
    ) -> list[dict[str, object]]:
        del dsn, timeout_seconds
        return []


def test_catalog_consistency_suppresses_valid_motion_video_component(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    for path in [
        settings.immich_uploads_path,
        settings.immich_thumbs_path,
        settings.immich_profile_path,
        settings.immich_video_path,
    ]:
        assert path is not None
        path.mkdir(parents=True, exist_ok=True)

    (settings.immich_uploads_path / "user-a").mkdir(parents=True, exist_ok=True)
    (settings.immich_video_path / "user-a").mkdir(parents=True, exist_ok=True)
    (settings.immich_uploads_path / "user-a" / "live.jpg").write_bytes(b"image")
    (settings.immich_video_path / "user-a" / "live-motion-MP.mp4").write_bytes(b"video")

    for root_slug in ["uploads", "thumbs", "profile", "video"]:
        CatalogInventoryScanService().run(
            settings,
            root_slug=root_slug,
            resume_session_id=None,
            max_files=None,
        )

    report = CatalogConsistencyValidationService(
        postgres=_FakeMotionPostgres(),
        sample_limit=20,
    ).run(settings)

    totals = report.metadata["totals"]
    assert totals["dbOriginalsMissingOnStorage"] == 0
    assert totals["unmappedDatabasePaths"] == 0
    assert totals["filteredNoiseRemoved"] == 1
    assert totals["validMotionVideoComponents"] == 1
    assert totals["realIssuesRemaining"] == 0
    assert "Suppressed 1 valid motion video components" in report.summary


def test_catalog_consistency_reports_missing_motion_video_component_when_storage_file_missing(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)

    for path in [
        settings.immich_uploads_path,
        settings.immich_thumbs_path,
        settings.immich_profile_path,
        settings.immich_video_path,
    ]:
        assert path is not None
        path.mkdir(parents=True, exist_ok=True)

    (settings.immich_uploads_path / "user-a").mkdir(parents=True, exist_ok=True)
    (settings.immich_uploads_path / "user-a" / "live.jpg").write_bytes(b"image")

    for root_slug in ["uploads", "thumbs", "profile", "video"]:
        CatalogInventoryScanService().run(
            settings,
            root_slug=root_slug,
            resume_session_id=None,
            max_files=None,
        )

    report = CatalogConsistencyValidationService(
        postgres=_FakeMotionPostgres(),
        sample_limit=20,
    ).run(settings)

    totals = report.metadata["totals"]
    assert totals["dbOriginalsMissingOnStorage"] == 1
    assert totals["unmappedDatabasePaths"] == 0
    db_missing = next(
        section for section in report.sections if section.name == "DB_ORIGINALS_MISSING_ON_STORAGE"
    )
    assert db_missing.rows[0]["classification"] == "valid_motion_video_component_missing_on_storage"


class _FakeWindowedPostgres:
    def validate_connection(self, dsn: str, timeout_seconds: int) -> CheckResult:
        del dsn, timeout_seconds
        return CheckResult(
            name="postgres_connection",
            status=CheckStatus.PASS,
            message="PostgreSQL connection established.",
        )

    def list_all_assets_for_catalog_consistency(
        self,
        dsn: str,
        timeout_seconds: int,
    ) -> list[dict[str, object]]:
        del dsn, timeout_seconds
        return [
            {
                "id": "asset-stable",
                "type": "image",
                "ownerId": "user-1",
                "createdAt": "2026-04-09T08:00:00+00:00",
                "updatedAt": "2026-04-09T08:00:00+00:00",
                "originalFileName": "stable.jpg",
                "originalPath": "/usr/src/app/upload/upload/user-a/stable.jpg",
                "encodedVideoPath": "",
            },
            {
                "id": "asset-during-scan",
                "type": "image",
                "ownerId": "user-1",
                "createdAt": "2099-04-09T09:30:00+00:00",
                "updatedAt": "2099-04-09T09:30:00+00:00",
                "originalFileName": "during-scan.jpg",
                "originalPath": "/usr/src/app/upload/upload/user-a/during-scan.jpg",
                "encodedVideoPath": "",
            },
        ]

    def list_all_asset_files_for_catalog_consistency(
        self,
        dsn: str,
        timeout_seconds: int,
    ) -> list[dict[str, object]]:
        del dsn, timeout_seconds
        return []


def test_catalog_consistency_excludes_assets_created_after_snapshot_window_start(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)

    for path in [
        settings.immich_uploads_path,
        settings.immich_thumbs_path,
        settings.immich_profile_path,
        settings.immich_video_path,
    ]:
        assert path is not None
        path.mkdir(parents=True, exist_ok=True)

    (settings.immich_uploads_path / "user-a").mkdir(parents=True, exist_ok=True)
    stable_path = settings.immich_uploads_path / "user-a" / "stable.jpg"
    stable_path.write_bytes(b"stable")

    for root_slug in ["uploads", "thumbs", "profile", "video"]:
        CatalogInventoryScanService().run(
            settings,
            root_slug=root_slug,
            resume_session_id=None,
            max_files=None,
        )

    report = CatalogConsistencyValidationService(
        postgres=_FakeWindowedPostgres(),
        sample_limit=20,
    ).run(settings)

    totals = report.metadata["totals"]
    assert totals["dbOriginalsMissingOnStorage"] == 0
    assert totals["totalAssetsScanned"] == 1
    assert report.metadata["comparisonWindowStartedAt"] is not None
