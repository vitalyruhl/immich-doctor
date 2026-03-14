from __future__ import annotations

from pathlib import Path

from immich_doctor.core.config import AppSettings


def configured_immich_paths(settings: AppSettings) -> dict[str, Path]:
    path_map: dict[str, Path | None] = {
        "immich_library_root": settings.immich_library_root,
        "immich_uploads_path": settings.immich_uploads_path,
        "immich_thumbs_path": settings.immich_thumbs_path,
        "immich_profile_path": settings.immich_profile_path,
        "immich_video_path": settings.immich_video_path,
    }
    return {name: path for name, path in path_map.items() if path is not None}


def runtime_paths(settings: AppSettings) -> dict[str, Path]:
    return {
        "reports_path": settings.reports_path,
        "manifests_path": settings.manifests_path,
        "quarantine_path": settings.quarantine_path,
        "logs_path": settings.logs_path,
        "tmp_path": settings.tmp_path,
    }
