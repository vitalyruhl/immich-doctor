from __future__ import annotations

from pathlib import Path

from immich_doctor.core.config import AppSettings


def backup_manifest_root(settings: AppSettings) -> Path:
    return settings.manifests_path / "backup"


def backup_snapshot_root(settings: AppSettings) -> Path:
    return backup_manifest_root(settings) / "snapshots"


def backup_snapshot_manifest_path(settings: AppSettings, snapshot_id: str) -> Path:
    return backup_snapshot_root(settings) / f"{snapshot_id}.json"
