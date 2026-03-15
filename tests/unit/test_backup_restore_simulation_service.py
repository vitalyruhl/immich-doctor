from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from immich_doctor.backup.core.models import (
    BackupArtifact,
    BackupSnapshot,
    BackupTarget,
    SnapshotCoverage,
    SnapshotKind,
)
from immich_doctor.backup.core.store import BackupSnapshotStore
from immich_doctor.backup.restore import BackupRestoreSimulationService, RestoreReadiness
from immich_doctor.core.config import AppSettings
from immich_doctor.repair import PlanToken, RepairJournalStore, RepairRun, RepairRunStatus


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        environment="docker-unraid",
        immich_library_root=tmp_path / "library",
        manifests_path=tmp_path / "manifests",
        quarantine_path=tmp_path / "quarantine",
    )


def _persist_snapshot(
    settings: AppSettings,
    *,
    snapshot_id: str,
    coverage: SnapshotCoverage,
    repair_run_id: str | None,
    with_db_artifact: bool,
) -> BackupSnapshot:
    target = BackupTarget(kind="local", reference="/backup", display_name="backup")
    file_artifact = BackupArtifact(
        name="files",
        kind="file_archive",
        target=target,
        relative_path=Path(f"{snapshot_id}/files"),
    )
    db_artifact = (
        BackupArtifact(
            name="db.sql",
            kind="database_dump",
            target=target,
            relative_path=Path(f"{snapshot_id}/db.sql"),
        )
        if with_db_artifact
        else None
    )
    return BackupSnapshotStore().persist_snapshot(
        settings,
        BackupSnapshot(
            snapshot_id=snapshot_id,
            kind=SnapshotKind.PRE_REPAIR,
            created_at=datetime(2026, 3, 15, 10, 0, tzinfo=UTC),
            source_fingerprint="fingerprint",
            coverage=coverage,
            file_artifacts=(file_artifact,),
            db_artifact=db_artifact,
            manifest_path=Path("placeholder.json"),
            verified=True,
            repair_run_id=repair_run_id,
        ),
    )


def _persist_repair_run(settings: AppSettings, repair_run_id: str, snapshot_id: str) -> None:
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
        repair_run_id=repair_run_id,
        started_at="2026-03-15T10:00:00+00:00",
        ended_at="2026-03-15T10:01:00+00:00",
        scope={"domain": "runtime.metadata_failures", "action": "repair"},
        status=RepairRunStatus.COMPLETED,
        live_state_fingerprint="live",
        plan_token_id=plan_token.token_id,
        pre_repair_snapshot_id=snapshot_id,
    )
    store.create_run(settings, repair_run=run, plan_token=plan_token)


def test_restore_simulation_reports_blockers_for_files_only_snapshot(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    snapshot = _persist_snapshot(
        settings,
        snapshot_id="snapshot-files",
        coverage=SnapshotCoverage.FILES_ONLY,
        repair_run_id="repair-run-1",
        with_db_artifact=False,
    )
    _persist_repair_run(settings, "repair-run-1", snapshot.snapshot_id)
    service = BackupRestoreSimulationService()

    result = service.simulate(settings, snapshot_id=None, repair_run_id="repair-run-1")

    assert result.readiness == RestoreReadiness.BLOCKED
    assert result.selected_snapshot is not None
    assert any(blocker.code == "missing_db_artifact" for blocker in result.blockers)
    assert any(blocker.code == "snapshot_coverage_insufficient" for blocker in result.blockers)


def test_restore_simulation_supports_manual_paired_snapshot_selection(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _persist_snapshot(
        settings,
        snapshot_id="snapshot-paired",
        coverage=SnapshotCoverage.PAIRED,
        repair_run_id=None,
        with_db_artifact=True,
    )
    service = BackupRestoreSimulationService()

    result = service.simulate(settings, snapshot_id="snapshot-paired", repair_run_id=None)

    assert result.readiness == RestoreReadiness.SIMULATION_ONLY
    assert result.selected_snapshot is not None
    assert result.selected_snapshot["selection_source"] == "manual"
    assert len(result.instructions) >= 4


def test_restore_simulation_rejects_manual_snapshot_mismatch_for_repair_run(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    linked = _persist_snapshot(
        settings,
        snapshot_id="snapshot-linked",
        coverage=SnapshotCoverage.FILES_ONLY,
        repair_run_id="repair-run-1",
        with_db_artifact=False,
    )
    _persist_snapshot(
        settings,
        snapshot_id="snapshot-other",
        coverage=SnapshotCoverage.PAIRED,
        repair_run_id=None,
        with_db_artifact=True,
    )
    _persist_repair_run(settings, "repair-run-1", linked.snapshot_id)
    service = BackupRestoreSimulationService()

    result = service.simulate(
        settings,
        snapshot_id="snapshot-other",
        repair_run_id="repair-run-1",
    )

    assert result.readiness == RestoreReadiness.BLOCKED
    assert result.selected_snapshot is None
