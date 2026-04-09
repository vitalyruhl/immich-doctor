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
                "originalPath": "/usr/src/app/upload/upload/user-a/keep.jpg",
                "encodedVideoPath": "",
            },
            {
                "id": "asset-missing",
                "type": "image",
                "ownerId": "user-1",
                "createdAt": "2026-04-09T09:01:00+00:00",
                "updatedAt": "2026-04-09T09:01:00+00:00",
                "originalPath": "/usr/src/app/upload/upload/user-a/missing.jpg",
                "encodedVideoPath": "/usr/src/app/upload/encoded-video/user-a/missing.mp4",
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

    db_missing = next(
        section for section in report.sections if section.name == "DB_ORIGINALS_MISSING_ON_STORAGE"
    )
    assert db_missing.rows[0]["asset_id"] == "asset-missing"
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
