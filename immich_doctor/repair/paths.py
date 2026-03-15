from __future__ import annotations

from pathlib import Path

from immich_doctor.core.config import AppSettings


def repair_manifests_root(settings: AppSettings) -> Path:
    return settings.manifests_path / "repair"


def repair_run_directory(settings: AppSettings, repair_run_id: str) -> Path:
    return repair_manifests_root(settings) / repair_run_id


def repair_run_file(settings: AppSettings, repair_run_id: str) -> Path:
    return repair_run_directory(settings, repair_run_id) / "run.json"


def repair_plan_token_file(settings: AppSettings, repair_run_id: str) -> Path:
    return repair_run_directory(settings, repair_run_id) / "plan-token.json"


def repair_journal_file(settings: AppSettings, repair_run_id: str) -> Path:
    return repair_run_directory(settings, repair_run_id) / "journal.jsonl"


def repair_quarantine_items_file(settings: AppSettings, repair_run_id: str) -> Path:
    return repair_run_directory(settings, repair_run_id) / "quarantine-items.jsonl"


def quarantine_index_file(settings: AppSettings) -> Path:
    return settings.quarantine_path / "index.jsonl"
