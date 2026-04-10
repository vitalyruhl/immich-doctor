from dataclasses import dataclass
from pathlib import Path

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
            },
            {
                "id": "asset-missing-confirmed",
                "type": "image",
                "ownerId": "user-1",
                "createdAt": "2026-04-09T09:01:00+00:00",
                "updatedAt": "2026-04-09T09:01:00+00:00",
                "originalFileName": "confirmed.jpg",
                "originalPath": "/usr/src/app/upload/upload/user-a/confirmed.jpg",
                "encodedVideoPath": "",
            },
            {
                "id": "asset-found-elsewhere",
                "type": "image",
                "ownerId": "user-1",
                "createdAt": "2026-04-09T09:02:00+00:00",
                "updatedAt": "2026-04-09T09:02:00+00:00",
                "originalFileName": "relocated.jpg",
                "originalPath": "/usr/src/app/upload/upload/user-a/relocated.jpg",
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


def _build_scanned_settings(tmp_path: Path) -> AppSettings:
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
    (settings.immich_uploads_path / "user-a").mkdir(parents=True, exist_ok=True)
    (settings.immich_uploads_path / "user-b").mkdir(parents=True, exist_ok=True)
    (settings.immich_uploads_path / "user-a" / "keep.jpg").write_bytes(b"ok")
    (settings.immich_uploads_path / "user-a" / ".immich").write_bytes(b"marker")
    (settings.immich_uploads_path / "user-a" / ".fuse_hidden0001").write_bytes(b"blocked")
    (settings.immich_uploads_path / "user-b" / ".fuse_hidden0002").write_bytes(b"free")
    (settings.immich_uploads_path / "user-b" / "relocated.jpg").write_bytes(b"relocated")

    for root_slug in ["uploads", "thumbs", "profile", "video"]:
        CatalogInventoryScanService().run(
            settings,
            root_slug=root_slug,
            resume_session_id=None,
            max_files=None,
        )
    return settings


def test_catalog_remediation_classifies_broken_db_originals_and_fuse_hidden_orphans(
    tmp_path: Path,
) -> None:
    settings = _build_scanned_settings(tmp_path)
    assert settings.immich_uploads_path is not None
    service = CatalogRemediationService(
        postgres=_FakePostgres(),
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

    assert confirmed.classification.value == "missing_confirmed"
    assert confirmed.action_eligible is True
    assert relocated.classification.value == "found_elsewhere"
    assert relocated.action_eligible is False
    assert relocated.found_relative_path == "user-b/relocated.jpg"
    assert blocked.classification.value == "blocked_in_use"
    assert blocked.action_eligible is False
    assert deletable.classification.value == "deletable_orphan"
    assert deletable.action_eligible is True
    assert all(item.file_name != ".immich" for item in result.fuse_hidden_orphans)


def test_catalog_remediation_bulk_preview_filters_to_eligible_items(tmp_path: Path) -> None:
    settings = _build_scanned_settings(tmp_path)
    assert settings.immich_uploads_path is not None
    service = CatalogRemediationService(
        postgres=_FakePostgres(),
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

    broken_preview = service.preview_broken_db_originals(settings, asset_ids=(), select_all=True)
    fuse_preview = service.preview_fuse_hidden_orphans(settings, finding_ids=(), select_all=True)

    assert [item["asset_id"] for item in broken_preview.selected_items] == [
        "asset-missing-confirmed"
    ]
    assert [item["relative_path"] for item in fuse_preview.selected_items] == [
        "user-b/.fuse_hidden0002"
    ]
