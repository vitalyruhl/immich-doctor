from __future__ import annotations

from pathlib import Path

from immich_doctor.core.config import AppSettings


def backup_config_root(settings: AppSettings) -> Path:
    configured = settings.config_path or Path("data/config")
    return configured.expanduser() / "backup"


def backup_targets_config_path(settings: AppSettings) -> Path:
    return backup_config_root(settings) / "targets.json"


def backup_secret_root(settings: AppSettings) -> Path:
    return backup_config_root(settings) / "secrets"


def backup_secret_path(settings: AppSettings, secret_id: str) -> Path:
    return backup_secret_root(settings) / f"{secret_id}.json"


def backup_workflow_root(target_root: Path) -> Path:
    return target_root / "_immich-doctor"


def backup_workflow_current_root(target_root: Path) -> Path:
    return backup_workflow_root(target_root) / "current"


def backup_workflow_current_library_root(target_root: Path) -> Path:
    return backup_workflow_current_root(target_root) / "immich-library"


def backup_workflow_test_root(target_root: Path) -> Path:
    return backup_workflow_root(target_root) / "tests"
