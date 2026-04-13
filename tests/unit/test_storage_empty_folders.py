from __future__ import annotations

from pathlib import Path

from immich_doctor.core.config import AppSettings
from immich_doctor.storage.empty_folders import EmptyDirQuarantineManager, EmptyFolderScanner


def _settings(tmp_path: Path) -> AppSettings:
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
    for path in [storage, uploads, thumbs, profile, video, quarantine, manifests, reports, logs, tmp_dir]:
        path.mkdir(parents=True, exist_ok=True)
    return AppSettings(
        immich_library_root=storage,
        immich_uploads_path=uploads,
        immich_thumbs_path=thumbs,
        immich_profile_path=profile,
        immich_video_path=video,
        quarantine_path=quarantine,
        manifests_path=manifests,
        reports_path=reports,
        logs_path=logs,
        tmp_path=tmp_dir,
    )


def test_scan_detects_leaf_empty_directories_and_orphan_parents(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    empty_leaf = settings.immich_uploads_path / "user-a" / "leaf-empty"
    nested_leaf = settings.immich_uploads_path / "user-b" / "parent-empty" / "child-empty"
    non_empty_dir = settings.immich_uploads_path / "user-c" / "has-file"
    for path in [empty_leaf, nested_leaf, non_empty_dir]:
        path.mkdir(parents=True, exist_ok=True)
    (non_empty_dir / "asset.jpg").write_bytes(b"data")

    report = EmptyFolderScanner().scan(settings)

    assert report.total_empty_dirs == 2
    assert {item.relative_path for item in report.findings} == {
        "user-a/leaf-empty",
        "user-b/parent-empty/child-empty",
    }
    assert {item.relative_path for item in report.orphan_parents} == {
        "user-a",
        "user-b",
        "user-b/parent-empty",
    }
    assert report.total_orphan_parents == 3


def test_quarantine_restore_and_delete_cycle(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    target = settings.immich_uploads_path / "restore-me"
    target.mkdir(parents=True, exist_ok=True)

    manager = EmptyDirQuarantineManager()
    quarantine_result = manager.quarantine(
        settings,
        root_slugs=("uploads",),
        paths=("restore-me",),
        quarantine_all=False,
        dry_run=False,
    )

    assert quarantine_result.to_dict()["quarantined_count"] == 1
    assert not target.exists()
    listed = manager.list_quarantined(settings, session_id=quarantine_result.session_id)
    assert len(listed) == 1

    restore_result = manager.restore(
        settings,
        session_id=quarantine_result.session_id or "",
        paths=(),
        restore_all=True,
        dry_run=False,
    )
    assert restore_result.to_dict()["restored_count"] == 1
    assert target.exists()
    assert manager.list_quarantined(settings, session_id=quarantine_result.session_id) == []

    delete_target = settings.immich_uploads_path / "delete-me"
    delete_target.mkdir(parents=True, exist_ok=True)
    delete_result = manager.quarantine(
        settings,
        root_slugs=("uploads",),
        paths=("delete-me",),
        quarantine_all=False,
        dry_run=False,
    )
    assert delete_result.session_id is not None
    finalize_result = manager.finalize_delete(
        settings,
        session_id=delete_result.session_id,
        paths=(),
        delete_all=True,
        dry_run=False,
    )
    assert finalize_result.to_dict()["deleted_count"] == 1
    assert not delete_target.exists()
