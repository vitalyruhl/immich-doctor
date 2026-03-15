from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from immich_doctor.core.config import AppSettings
from immich_doctor.repair import (
    PlanToken,
    RepairJournalEntry,
    RepairJournalEntryStatus,
    RepairJournalStore,
    RepairRun,
    RepairRunStatus,
    RepairUndoService,
    UndoEligibility,
    UndoType,
)


@dataclass(slots=True)
class _FakeFilesystem:
    modes: dict[str, int]

    def stat_path(self, path) -> SimpleNamespace:  # type: ignore[no-untyped-def]
        normalized = str(path).replace("\\", "/")
        if normalized not in self.modes:
            raise FileNotFoundError(normalized)
        return SimpleNamespace(st_mode=self.modes[normalized])

    def set_permissions(self, path, mode: int) -> None:  # type: ignore[no-untyped-def]
        normalized = str(path).replace("\\", "/")
        if normalized not in self.modes:
            raise FileNotFoundError(normalized)
        self.modes[normalized] = mode


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        manifests_path=tmp_path / "manifests",
        quarantine_path=tmp_path / "quarantine",
    )


def _create_run(
    tmp_path: Path,
    *,
    status: RepairRunStatus = RepairRunStatus.COMPLETED,
    path: str = "/library/asset.jpg",
    old_mode: int = 0o200,
    new_mode: int = 0o640,
) -> tuple[AppSettings, RepairJournalStore, RepairRun, RepairJournalEntry]:
    settings = _settings(tmp_path)
    store = RepairJournalStore()
    plan_token = PlanToken(
        token_id="token-1",
        created_at="2026-03-15T10:00:00+00:00",
        scope={"domain": "runtime.metadata_failures", "action": "repair"},
        db_fingerprint="db",
        file_fingerprint="file",
        expires_at=None,
    )
    run = RepairRun(
        repair_run_id=uuid4().hex,
        started_at="2026-03-15T10:00:00+00:00",
        ended_at="2026-03-15T10:01:00+00:00",
        scope={"domain": "runtime.metadata_failures", "action": "repair"},
        status=status,
        live_state_fingerprint="live",
        plan_token_id=plan_token.token_id,
        pre_repair_snapshot_id="snapshot-1",
    )
    store.create_run(settings, repair_run=run, plan_token=plan_token)
    entry = RepairJournalEntry(
        entry_id=uuid4().hex,
        repair_run_id=run.repair_run_id,
        operation_type="fix_permissions",
        status=RepairJournalEntryStatus.APPLIED,
        asset_id="asset-1",
        table=None,
        old_db_values=None,
        new_db_values=None,
        original_path=path,
        quarantine_path=None,
        undo_type=UndoType.RESTORE_PERMISSIONS,
        undo_payload={"path": path, "old_mode": old_mode, "new_mode": new_mode},
    )
    store.append_journal_entry(settings, entry)
    return settings, store, run, entry


def test_undo_plan_reports_reversible_now_for_runtime_permission_repairs(
    tmp_path: Path,
) -> None:
    path = str((tmp_path / "asset.jpg").resolve()).replace("\\", "/")
    settings, _, run, entry = _create_run(tmp_path, path=path)
    service = RepairUndoService(filesystem=_FakeFilesystem({path: 0o640}))

    result = service.plan(settings, repair_run_id=run.repair_run_id)

    assert result.eligibility == UndoEligibility.REVERSIBLE_NOW
    assert result.apply_allowed is True
    assert result.entry_assessments[0].entry_id == entry.entry_id


def test_undo_plan_requires_full_restore_when_file_is_missing(tmp_path: Path) -> None:
    path = str((tmp_path / "missing.jpg").resolve()).replace("\\", "/")
    settings, _, run, _ = _create_run(tmp_path, path=path)
    service = RepairUndoService(filesystem=_FakeFilesystem({}))

    result = service.plan(settings, repair_run_id=run.repair_run_id)

    assert result.eligibility == UndoEligibility.REQUIRES_FULL_RESTORE
    assert any(
        blocker.code == "missing_file_for_undo" for blocker in result.entry_assessments[0].blockers
    )


def test_undo_execute_restores_recorded_mode_for_runtime_permission_repairs(
    tmp_path: Path,
) -> None:
    path = str((tmp_path / "asset.jpg").resolve()).replace("\\", "/")
    settings, store, run, entry = _create_run(tmp_path, path=path, old_mode=0o200, new_mode=0o640)
    filesystem = _FakeFilesystem({path: 0o640})
    service = RepairUndoService(filesystem=filesystem, store=store)

    result = service.execute(settings, repair_run_id=run.repair_run_id, apply=True)

    assert result.eligibility == UndoEligibility.REVERSIBLE_NOW
    assert result.execution_items[0].status.value == "applied"
    assert filesystem.modes[path] == 0o200
    undo_run = store.load_run(settings, result.repair_run_id)
    undo_entries = store.load_journal_entries(settings, result.repair_run_id)
    assert undo_run.status == RepairRunStatus.COMPLETED
    assert undo_entries[0].operation_type == "undo_restore_permissions"
    assert undo_entries[0].undo_payload["restored_mode"] == 0o200


def test_undo_execute_blocks_partial_target_run(tmp_path: Path) -> None:
    path = str((tmp_path / "asset.jpg").resolve()).replace("\\", "/")
    settings, _, run, _ = _create_run(
        tmp_path,
        status=RepairRunStatus.PARTIAL,
        path=path,
    )
    service = RepairUndoService(filesystem=_FakeFilesystem({path: 0o640}))

    result = service.execute(settings, repair_run_id=run.repair_run_id, apply=True)

    assert result.repair_run_id == ""
    assert result.eligibility == UndoEligibility.REQUIRES_FULL_RESTORE
    assert any(blocker.code == "repair_run_not_stable" for blocker in result.blockers)
