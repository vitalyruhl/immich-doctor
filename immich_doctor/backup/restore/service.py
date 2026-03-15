from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.backup.core.models import BackupSnapshot, SnapshotCoverage
from immich_doctor.backup.core.store import BackupSnapshotStore
from immich_doctor.backup.restore.instructions import (
    build_restore_instructions,
    detect_restore_instruction_profile,
)
from immich_doctor.backup.restore.models import (
    RestoreBlocker,
    RestoreReadiness,
    RestoreSimulationResult,
)
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.repair.store import RepairJournalStore


@dataclass(slots=True)
class BackupRestoreSimulationService:
    snapshot_store: BackupSnapshotStore = field(default_factory=BackupSnapshotStore)
    repair_store: RepairJournalStore = field(default_factory=RepairJournalStore)

    def simulate(
        self,
        settings: AppSettings,
        *,
        snapshot_id: str | None,
        repair_run_id: str | None,
    ) -> RestoreSimulationResult:
        checks: list[CheckResult] = []
        blockers: list[RestoreBlocker] = []

        snapshot, selection_source = self._select_snapshot(
            settings,
            snapshot_id=snapshot_id,
            repair_run_id=repair_run_id,
        )

        if snapshot is None:
            blockers.append(
                RestoreBlocker(
                    code="snapshot_unavailable",
                    message="No safe snapshot could be selected for restore simulation.",
                    severity="error",
                )
            )
            checks.append(
                CheckResult(
                    name="snapshot_selection",
                    status=CheckStatus.FAIL,
                    message="Restore simulation is blocked because no snapshot was selected.",
                )
            )
            return RestoreSimulationResult(
                domain="backup.restore",
                action="simulate",
                summary="Full restore simulation is blocked because no safe snapshot is available.",
                readiness=RestoreReadiness.BLOCKED,
                checks=checks,
                blockers=blockers,
                metadata={
                    "requested_snapshot_id": snapshot_id,
                    "requested_repair_run_id": repair_run_id,
                },
                recommendations=[
                    (
                        "Create or select a valid pre-repair or manual snapshot "
                        "before simulating full restore."
                    ),
                ],
            )

        checks.append(
            CheckResult(
                name="snapshot_selection",
                status=CheckStatus.PASS,
                message=f"Selected snapshot `{snapshot.snapshot_id}` from `{selection_source}`.",
                details={
                    "selection_source": selection_source,
                    "coverage": snapshot.coverage.value,
                },
            )
        )

        if snapshot.coverage != SnapshotCoverage.PAIRED:
            blockers.append(
                RestoreBlocker(
                    code="snapshot_coverage_insufficient",
                    message=(
                        f"Snapshot coverage `{snapshot.coverage.value}` cannot provide full "
                        "DB + file rollback."
                    ),
                    severity="error",
                )
            )
        if snapshot.db_artifact is None:
            blockers.append(
                RestoreBlocker(
                    code="missing_db_artifact",
                    message="Selected snapshot does not contain a database artifact.",
                    severity="error",
                )
            )
        if not snapshot.file_artifacts:
            blockers.append(
                RestoreBlocker(
                    code="missing_file_artifacts",
                    message="Selected snapshot does not contain file artifacts.",
                    severity="error",
                )
            )

        profile = detect_restore_instruction_profile(settings)
        instructions = build_restore_instructions(
            settings=settings,
            snapshot=snapshot,
            profile=profile,
        )
        readiness = RestoreReadiness.BLOCKED if blockers else RestoreReadiness.SIMULATION_ONLY
        checks.append(
            CheckResult(
                name="restore_execution_mode",
                status=CheckStatus.WARN if not blockers else CheckStatus.FAIL,
                message=(
                    "Full restore orchestration is currently simulation-only."
                    if not blockers
                    else "Full restore execution is blocked for the selected snapshot."
                ),
            )
        )

        return RestoreSimulationResult(
            domain="backup.restore",
            action="simulate",
            summary=(
                "Full restore simulation generated deterministic manual steps."
                if not blockers
                else "Full restore simulation found blockers for the selected snapshot."
            ),
            readiness=readiness,
            checks=checks,
            selected_snapshot={
                "snapshot_id": snapshot.snapshot_id,
                "kind": snapshot.kind.value,
                "coverage": snapshot.coverage.value,
                "repair_run_id": snapshot.repair_run_id,
                "manifest_path": snapshot.manifest_path.as_posix(),
                "selection_source": selection_source,
            },
            blockers=blockers,
            instructions=instructions,
            metadata={
                "instruction_profile": profile.name,
                "requested_snapshot_id": snapshot_id,
                "requested_repair_run_id": repair_run_id,
            },
            recommendations=[
                "Use targeted undo first when the repair run is journal-backed and reversible.",
                "Treat generated restore steps as manual orchestration instructions in this phase.",
            ],
        )

    def _select_snapshot(
        self,
        settings: AppSettings,
        *,
        snapshot_id: str | None,
        repair_run_id: str | None,
    ) -> tuple[BackupSnapshot | None, str | None]:
        if repair_run_id:
            run = self.repair_store.load_run(settings, repair_run_id)
            linked_snapshot_id = run.pre_repair_snapshot_id
            if linked_snapshot_id is None:
                return None, None
            if snapshot_id is not None and snapshot_id != linked_snapshot_id:
                return None, None
            return (
                self.snapshot_store.load_snapshot(settings, linked_snapshot_id),
                "repair_linked",
            )

        if snapshot_id is None:
            return None, None
        return self.snapshot_store.load_snapshot(settings, snapshot_id), "manual"
