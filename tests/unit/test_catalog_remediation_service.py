from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from immich_doctor.catalog.remediation_models import CatalogRemediationActionKind
from immich_doctor.catalog.remediation_service import CatalogRemediationService
from immich_doctor.catalog.service import CatalogInventoryScanService
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus


@dataclass
class _FakeExternalTools:
    responses: dict[str, dict[str, object]]

    def inspect_open_file_handles(self, path: Path) -> dict[str, object]:
        return self.responses.get(
            str(path),
            {"status": "unavailable", "tool": "lsof", "reason": "lsof unavailable"},
        )


class _FakePostgres:
    def __init__(self, checksum_value: str) -> None:
        self.checksum_value = checksum_value

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
                "originalFileName": "keep.jpg",
                "originalPath": "/usr/src/app/upload/upload/user-a/keep.jpg",
                "encodedVideoPath": "",
            },
            {
                "id": "asset-missing-confirmed",
                "type": "image",
                "originalFileName": "confirmed.jpg",
                "originalPath": "/usr/src/app/upload/upload/user-a/confirmed.jpg",
                "encodedVideoPath": "",
            },
            {
                "id": "asset-found-elsewhere",
                "type": "image",
                "originalFileName": "relocated.jpg",
                "originalPath": "/usr/src/app/upload/upload/user-a/relocated.jpg",
                "encodedVideoPath": "",
            },
            {
                "id": "asset-path-fix",
                "type": "image",
                "originalFileName": "path-fix.jpg",
                "originalPath": "/usr/src/app/upload/upload/user-a/path-fix.jpg",
                "checksum": self.checksum_value,
                "encodedVideoPath": "",
            },
            {
                "id": "asset-zero-critical",
                "type": "image",
                "originalFileName": "critical-zero.jpg",
                "originalPath": "/usr/src/app/upload/upload/user-a/critical-zero.jpg",
                "encodedVideoPath": "",
            },
            {
                "id": "asset-video",
                "type": "video",
                "originalFileName": "keep.jpg",
                "originalPath": "/usr/src/app/upload/upload/user-a/keep.jpg",
                "encodedVideoPath": "/usr/src/app/upload/encoded-video/user-a/video-zero.mp4",
            },
            {
                "id": "asset-thumb",
                "type": "image",
                "originalFileName": "keep.jpg",
                "originalPath": "/usr/src/app/upload/upload/user-a/keep.jpg",
                "encodedVideoPath": "",
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
                "id": "thumb-1",
                "assetId": "asset-thumb",
                "type": "thumbnail",
                "path": "/usr/src/app/upload/thumbs/user-a/thumb-zero.webp",
            }
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


def _build_scanned_settings(tmp_path: Path) -> tuple[AppSettings, str]:
    settings = _settings(tmp_path)
    for path in [
        settings.immich_uploads_path,
        settings.immich_thumbs_path,
        settings.immich_profile_path,
        settings.immich_video_path,
    ]:
        assert path is not None
        path.mkdir(parents=True, exist_ok=True)

    assert settings.immich_uploads_path is not None
    assert settings.immich_thumbs_path is not None
    assert settings.immich_video_path is not None

    (settings.immich_uploads_path / "user-a").mkdir(parents=True, exist_ok=True)
    (settings.immich_uploads_path / "user-b").mkdir(parents=True, exist_ok=True)
    (settings.immich_thumbs_path / "user-a").mkdir(parents=True, exist_ok=True)
    (settings.immich_video_path / "user-a").mkdir(parents=True, exist_ok=True)

    (settings.immich_uploads_path / "user-a" / "keep.jpg").write_bytes(b"ok")
    (settings.immich_uploads_path / "user-a" / "path-fix.jpg").write_bytes(b"path-fix")
    (settings.immich_uploads_path / "user-a" / "critical-zero.jpg").write_bytes(b"")
    (settings.immich_uploads_path / "user-a" / ".immich").write_bytes(b"marker")
    (settings.immich_uploads_path / "user-a" / ".fuse_hidden0001").write_bytes(b"blocked")
    (settings.immich_uploads_path / "user-b" / ".fuse_hidden0002").write_bytes(b"free")
    (settings.immich_uploads_path / "user-b" / ".fuse_hidden0003").write_bytes(b"unknown")
    (settings.immich_uploads_path / "user-b" / "relocated.jpg").write_bytes(b"relocated")
    (settings.immich_uploads_path / "user-b" / "orphan-zero.jpg").write_bytes(b"")
    (settings.immich_thumbs_path / "user-a" / "thumb-zero.webp").write_bytes(b"")
    (settings.immich_video_path / "user-a" / "video-zero.mp4").write_bytes(b"")

    for root_slug in ["uploads", "thumbs", "profile", "video"]:
        CatalogInventoryScanService().run(
            settings,
            root_slug=root_slug,
            resume_session_id=None,
            max_files=None,
        )
    checksum_value = sha256(b"path-fix").hexdigest()
    return settings, checksum_value


def test_catalog_remediation_classifies_broken_zero_byte_and_fuse_hidden_findings(
    tmp_path: Path,
) -> None:
    settings, checksum_value = _build_scanned_settings(tmp_path)
    assert settings.immich_uploads_path is not None
    service = CatalogRemediationService(
        postgres=_FakePostgres(checksum_value=checksum_value),
        external_tools=_FakeExternalTools(
            responses={
                str(settings.immich_uploads_path / "user-a" / ".fuse_hidden0001"): {
                    "status": "in_use",
                    "tool": "lsof",
                    "reason": "Open file handles were detected.",
                },
                str(settings.immich_uploads_path / "user-b" / ".fuse_hidden0002"): {
                    "status": "not_in_use",
                    "tool": "lsof",
                    "reason": "No open file handles were reported.",
                },
            }
        ),
    )

    result = service.scan(settings)

    confirmed = next(
        item for item in result.broken_db_originals if item.asset_id == "asset-missing-confirmed"
    )
    relocated = next(
        item for item in result.broken_db_originals if item.asset_id == "asset-found-elsewhere"
    )
    hash_match = next(
        item for item in result.broken_db_originals if item.asset_id == "asset-path-fix"
    )
    upload_orphan = next(
        item for item in result.zero_byte_findings if item.relative_path == "user-b/orphan-zero.jpg"
    )
    upload_critical = next(
        item
        for item in result.zero_byte_findings
        if item.relative_path == "user-a/critical-zero.jpg"
    )
    thumb_derivative = next(
        item for item in result.zero_byte_findings if item.relative_path == "user-a/thumb-zero.webp"
    )
    video_derivative = next(
        item for item in result.zero_byte_findings if item.relative_path == "user-a/video-zero.mp4"
    )
    blocked = next(
        item
        for item in result.fuse_hidden_orphans
        if item.relative_path == "user-a/.fuse_hidden0001"
    )
    deletable = next(
        item
        for item in result.fuse_hidden_orphans
        if item.relative_path == "user-b/.fuse_hidden0002"
    )
    check_failed = next(
        item
        for item in result.fuse_hidden_orphans
        if item.relative_path == "user-b/.fuse_hidden0003"
    )

    assert confirmed.classification.value == "missing_confirmed"
    assert confirmed.eligible_actions == (CatalogRemediationActionKind.BROKEN_DB_CLEANUP,)
    assert relocated.classification.value == "found_elsewhere"
    assert relocated.action_eligible is False
    assert hash_match.classification.value == "found_with_hash_match"
    assert hash_match.checksum_match is True
    assert hash_match.eligible_actions == (CatalogRemediationActionKind.BROKEN_DB_PATH_FIX,)
    assert upload_orphan.classification.value == "zero_byte_upload_orphan"
    assert upload_orphan.action_eligible is False
    assert upload_critical.classification.value == "zero_byte_upload_critical"
    assert upload_critical.action_eligible is False
    assert thumb_derivative.classification.value == "zero_byte_thumb_derivative"
    assert thumb_derivative.action_eligible is False
    assert video_derivative.classification.value == "zero_byte_video_derivative"
    assert video_derivative.action_eligible is False
    assert blocked.classification.value == "blocked_in_use"
    assert blocked.action_eligible is False
    assert deletable.classification.value == "deletable_orphan"
    assert deletable.action_eligible is True
    assert deletable.eligible_actions == (CatalogRemediationActionKind.FUSE_HIDDEN_DELETE,)
    assert check_failed.classification.value == "check_failed"
    assert check_failed.action_eligible is True
    assert check_failed.eligible_actions == (CatalogRemediationActionKind.FUSE_HIDDEN_DELETE,)
    assert all(item.file_name != ".immich" for item in result.fuse_hidden_orphans)
    assert all(item.file_name != ".immich" for item in result.zero_byte_findings)


def test_catalog_remediation_bulk_preview_filters_to_eligible_items(tmp_path: Path) -> None:
    settings, checksum_value = _build_scanned_settings(tmp_path)
    assert settings.immich_uploads_path is not None
    service = CatalogRemediationService(
        postgres=_FakePostgres(checksum_value=checksum_value),
        external_tools=_FakeExternalTools(
            responses={
                str(settings.immich_uploads_path / "user-a" / ".fuse_hidden0001"): {
                    "status": "in_use",
                    "tool": "lsof",
                    "reason": "Open file handles were detected.",
                },
                str(settings.immich_uploads_path / "user-b" / ".fuse_hidden0002"): {
                    "status": "not_in_use",
                    "tool": "lsof",
                    "reason": "No open file handles were reported.",
                },
            }
        ),
    )

    cleanup_preview = service.preview_broken_db_cleanup(settings, asset_ids=(), select_all=True)
    path_fix_preview = service.preview_broken_db_path_fix(settings, asset_ids=(), select_all=True)
    zero_byte_preview = service.preview_zero_byte_files(settings, finding_ids=(), select_all=True)
    fuse_preview = service.preview_fuse_hidden_orphans(settings, finding_ids=(), select_all=True)

    assert [item["asset_id"] for item in cleanup_preview.selected_items] == [
        "asset-missing-confirmed"
    ]
    assert [item["asset_id"] for item in path_fix_preview.selected_items] == ["asset-path-fix"]
    assert zero_byte_preview.selected_items == []
    assert sorted(item["relative_path"] for item in fuse_preview.selected_items) == [
        "user-b/.fuse_hidden0002",
        "user-b/.fuse_hidden0003",
    ]
