from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from immich_doctor.core.config import AppSettings
from immich_doctor.repair.guards import (
    create_plan_token,
    fingerprint_payload,
    validate_plan_token,
)
from immich_doctor.repair.models import (
    QuarantineItem,
    RepairJournalEntry,
    RepairJournalEntryStatus,
    RepairRun,
    RepairRunStatus,
    UndoType,
)
from immich_doctor.repair.paths import (
    quarantine_index_file,
    repair_journal_file,
    repair_manifests_root,
    repair_plan_token_file,
    repair_quarantine_items_file,
    repair_run_directory,
    repair_run_file,
)
from immich_doctor.repair.store import RepairJournalStore


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        manifests_path=tmp_path / "manifests",
        quarantine_path=tmp_path / "quarantine",
    )


def test_repair_run_creation_and_persistence(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    store = RepairJournalStore()
    plan_token = create_plan_token(
        scope={"domain": "runtime.metadata_failures", "action": "repair"},
        db_fingerprint="db-fingerprint",
        file_fingerprint="file-fingerprint",
    )
    repair_run = RepairRun.new(
        repair_run_id=uuid4().hex,
        scope={"domain": "runtime.metadata_failures", "action": "repair"},
        status=RepairRunStatus.RUNNING,
        live_state_fingerprint="live-fingerprint",
        plan_token_id=plan_token.token_id,
    )

    store.create_run(settings, repair_run=repair_run, plan_token=plan_token)

    assert repair_manifests_root(settings) == settings.manifests_path / "repair"
    assert repair_run_directory(settings, repair_run.repair_run_id).exists()
    assert repair_run_file(settings, repair_run.repair_run_id).exists()
    assert repair_plan_token_file(settings, repair_run.repair_run_id).exists()

    loaded_run = store.load_run(settings, repair_run.repair_run_id)
    loaded_token = store.load_plan_token(settings, repair_run.repair_run_id)

    assert loaded_run.repair_run_id == repair_run.repair_run_id
    assert loaded_run.status == RepairRunStatus.RUNNING
    assert loaded_token.token_id == plan_token.token_id
    assert loaded_token.scope == {"domain": "runtime.metadata_failures", "action": "repair"}


def test_repair_journal_retains_partial_and_failed_entries(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = RepairJournalStore()
    plan_token = create_plan_token(
        scope={"domain": "consistency", "action": "repair"},
        db_fingerprint="db",
        file_fingerprint="file",
    )
    repair_run = RepairRun.new(
        repair_run_id=uuid4().hex,
        scope={"domain": "consistency", "action": "repair"},
        status=RepairRunStatus.RUNNING,
        live_state_fingerprint="live",
        plan_token_id=plan_token.token_id,
    )
    store.create_run(settings, repair_run=repair_run, plan_token=plan_token)

    planned_entry = RepairJournalEntry(
        entry_id=uuid4().hex,
        repair_run_id=repair_run.repair_run_id,
        operation_type="fix_permissions",
        status=RepairJournalEntryStatus.PLANNED,
        asset_id="asset-1",
        table=None,
        old_db_values=None,
        new_db_values=None,
        original_path="/library/a.jpg",
        quarantine_path=None,
        undo_type=UndoType.NONE,
        undo_payload={},
    )
    failed_entry = RepairJournalEntry(
        entry_id=uuid4().hex,
        repair_run_id=repair_run.repair_run_id,
        operation_type="delete_album_asset",
        status=RepairJournalEntryStatus.FAILED,
        asset_id="asset-2",
        table="public.album_asset",
        old_db_values={"albumId": "album-1", "assetsId": "asset-2"},
        new_db_values=None,
        original_path=None,
        quarantine_path=None,
        undo_type=UndoType.RESTORE_DB_VALUES,
        undo_payload={"albumId": "album-1", "assetsId": "asset-2"},
        error_details={"message": "statement failed"},
    )

    store.append_journal_entry(settings, planned_entry)
    store.append_journal_entry(settings, failed_entry)
    repair_run.finish(RepairRunStatus.PARTIAL)
    store.update_run(settings, repair_run)

    loaded_entries = store.load_journal_entries(settings, repair_run.repair_run_id)
    loaded_run = store.load_run(settings, repair_run.repair_run_id)

    assert repair_journal_file(settings, repair_run.repair_run_id).exists()
    assert [entry.status for entry in loaded_entries] == [
        RepairJournalEntryStatus.PLANNED,
        RepairJournalEntryStatus.FAILED,
    ]
    assert loaded_run.status == RepairRunStatus.PARTIAL
    assert loaded_run.ended_at is not None


def test_plan_token_generation_and_validation_behavior() -> None:
    now = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
    scope = {"domain": "runtime.metadata_failures", "ids": ["asset-1"]}
    plan_token = create_plan_token(
        scope=scope,
        db_fingerprint=fingerprint_payload(["asset-1"]),
        file_fingerprint=fingerprint_payload(["/library/a.jpg"]),
        ttl=timedelta(minutes=5),
        now=now,
    )

    valid_result = validate_plan_token(
        plan_token,
        scope=scope,
        db_fingerprint=fingerprint_payload(["asset-1"]),
        file_fingerprint=fingerprint_payload(["/library/a.jpg"]),
        now=now + timedelta(minutes=1),
    )
    drift_result = validate_plan_token(
        plan_token,
        scope=scope,
        db_fingerprint=fingerprint_payload(["asset-1", "asset-2"]),
        file_fingerprint=fingerprint_payload(["/library/a.jpg"]),
        now=now + timedelta(minutes=1),
    )
    expired_result = validate_plan_token(
        plan_token,
        scope=scope,
        db_fingerprint=fingerprint_payload(["asset-1"]),
        file_fingerprint=fingerprint_payload(["/library/a.jpg"]),
        now=now + timedelta(minutes=10),
    )

    assert valid_result.valid is True
    assert drift_result.valid is False
    assert drift_result.reason == "Live state drift detected between inspect and apply."
    assert expired_result.valid is False
    assert expired_result.reason == "Plan token expired before apply."


def test_quarantine_index_persistence(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = RepairJournalStore()
    plan_token = create_plan_token(
        scope={"domain": "runtime.metadata_failures", "action": "repair"},
        db_fingerprint="db",
        file_fingerprint="file",
    )
    repair_run = RepairRun.new(
        repair_run_id=uuid4().hex,
        scope={"domain": "runtime.metadata_failures", "action": "repair"},
        status=RepairRunStatus.RUNNING,
        live_state_fingerprint="live",
        plan_token_id=plan_token.token_id,
    )
    store.create_run(settings, repair_run=repair_run, plan_token=plan_token)

    item = QuarantineItem(
        quarantine_item_id=uuid4().hex,
        repair_run_id=repair_run.repair_run_id,
        asset_id="asset-1",
        source_path="/library/a.jpg",
        quarantine_path="/quarantine/a.jpg",
        reason="corrupted_file",
        checksum="abc123",
        size_bytes=42,
        restorable=True,
    )

    store.append_quarantine_item(settings, item)

    per_run_items = store.load_quarantine_items(settings, repair_run.repair_run_id)
    global_items = store.load_quarantine_index(settings)

    assert repair_quarantine_items_file(settings, repair_run.repair_run_id).exists()
    assert quarantine_index_file(settings).exists()
    assert per_run_items[0].source_path == "/library/a.jpg"
    assert global_items[0].quarantine_path == "/quarantine/a.jpg"
