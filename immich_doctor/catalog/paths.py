from __future__ import annotations

from pathlib import Path

from immich_doctor.core.config import AppSettings


def catalog_root(settings: AppSettings) -> Path:
    return settings.manifests_path / "catalog"


def catalog_database_path(settings: AppSettings) -> Path:
    return catalog_root(settings) / "file-catalog.sqlite3"


def catalog_remediation_cache_path(settings: AppSettings) -> Path:
    return catalog_root(settings) / "remediation-cache.json"


def catalog_ignored_findings_path(settings: AppSettings) -> Path:
    return catalog_root(settings) / "ignored-findings.json"
