from pathlib import Path

from immich_doctor.core.config import AppSettings
from immich_doctor.storage.path_mapping import ImmichStoragePathResolver


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        _env_file=None,
        immich_library_root=tmp_path / "library",
        immich_uploads_path=tmp_path / "upload",
        immich_thumbs_path=tmp_path / "thumbs",
        immich_profile_path=tmp_path / "profile",
        immich_video_path=tmp_path / "encoded-video",
        manifests_path=tmp_path / "manifests",
        reports_path=tmp_path / "reports",
        quarantine_path=tmp_path / "quarantine",
        logs_path=tmp_path / "logs",
        tmp_path=tmp_path / "tmp",
    )


def test_resolver_maps_legacy_immich_paths_into_configured_roots(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    resolver = ImmichStoragePathResolver(settings)

    resolved = resolver.resolve("/usr/src/app/upload/upload/user-a/ab/cd/original.jpg")

    assert resolved is not None
    assert resolved.root_slug == "uploads"
    assert resolved.relative_path == "user-a/ab/cd/original.jpg"
    assert resolved.mapping_mode == "legacy"
    assert resolved.absolute_path == (
        settings.immich_uploads_path / "user-a" / "ab" / "cd" / "original.jpg"
    )


def test_resolver_maps_legacy_library_paths_into_library_root(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    resolver = ImmichStoragePathResolver(settings)

    resolved = resolver.resolve("/usr/src/app/upload/library/user-a/ab/cd/original.jpg")

    assert resolved is not None
    assert resolved.root_slug == "library"
    assert resolved.relative_path == "user-a/ab/cd/original.jpg"
    assert resolved.mapping_mode == "legacy"
    assert resolved.absolute_path == (
        settings.immich_library_root / "user-a" / "ab" / "cd" / "original.jpg"
    )


def test_resolver_maps_runtime_paths_without_legacy_translation(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    resolver = ImmichStoragePathResolver(settings)

    runtime_path = str(settings.immich_thumbs_path / "user-a" / "00" / "preview.webp")
    resolved = resolver.resolve(runtime_path)

    assert resolved is not None
    assert resolved.root_slug == "thumbs"
    assert resolved.relative_path == "user-a/00/preview.webp"
    assert resolved.mapping_mode == "runtime"


def test_resolver_detects_legacy_prefix_even_when_path_is_not_mappable(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        immich_uploads_path=tmp_path / "upload",
        manifests_path=tmp_path / "manifests",
        reports_path=tmp_path / "reports",
        quarantine_path=tmp_path / "quarantine",
        logs_path=tmp_path / "logs",
        tmp_path=tmp_path / "tmp",
    )
    resolver = ImmichStoragePathResolver(settings)

    assert resolver.resolve("/usr/src/app/upload/thumbs/user-a/preview.webp") is None
    assert resolver.looks_like_legacy_immich_path("/usr/src/app/upload/thumbs/user-a/preview.webp")
