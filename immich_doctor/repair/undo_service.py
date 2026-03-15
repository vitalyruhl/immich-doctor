from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from stat import S_IMODE
from uuid import uuid4

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.repair.guards import (
    build_live_state_fingerprint,
    create_plan_token,
    fingerprint_payload,
    validate_plan_token,
)
from immich_doctor.repair.models import (
    RepairJournalEntry,
    RepairJournalEntryStatus,
    RepairRun,
    RepairRunStatus,
    UndoType,
)
from immich_doctor.repair.paths import repair_run_directory
from immich_doctor.repair.store import RepairJournalStore
from immich_doctor.repair.undo_models import (
    UndoBlocker,
    UndoEligibility,
    UndoEntryAssessment,
    UndoExecutionItem,
    UndoExecutionResult,
    UndoExecutionStatus,
    UndoPlanResult,
)


@dataclass(slots=True)
class RepairUndoService:
    store: RepairJournalStore = field(default_factory=RepairJournalStore)
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)

    def plan(
        self,
        settings: AppSettings,
        *,
        repair_run_id: str,
        entry_ids: tuple[str, ...] = (),
    ) -> UndoPlanResult:
        run = self.store.load_run(settings, repair_run_id)
        entries = self.store.load_journal_entries(settings, repair_run_id)
        selected_entries = self._select_entries(entries, entry_ids)
        entry_assessments = [self._assess_entry(entry) for entry in selected_entries]
        blockers = self._global_blockers(run, entries, entry_assessments)
        eligibility = self._eligibility(entry_assessments, blockers)
        return UndoPlanResult(
            domain="repair.undo",
            action="plan",
            summary=self._plan_summary(eligibility, entry_assessments),
            repair_run_id=repair_run_id,
            target_repair_run_status=run.status.value,
            eligibility=eligibility,
            apply_allowed=eligibility == UndoEligibility.REVERSIBLE_NOW,
            checks=self._plan_checks(run, entry_assessments),
            blockers=blockers,
            entry_assessments=entry_assessments,
            metadata={
                "selected_entry_ids": [entry.entry_id for entry in selected_entries],
                "pre_repair_snapshot_id": run.pre_repair_snapshot_id,
            },
            recommendations=self._plan_recommendations(eligibility),
        )

    def execute(
        self,
        settings: AppSettings,
        *,
        repair_run_id: str,
        entry_ids: tuple[str, ...] = (),
        apply: bool,
    ) -> UndoExecutionResult:
        plan = self.plan(settings, repair_run_id=repair_run_id, entry_ids=entry_ids)
        if not apply:
            return UndoExecutionResult(
                domain="repair.undo",
                action="apply",
                summary="Undo execution remained dry-run and produced no mutations.",
                repair_run_id="",
                target_repair_run_id=repair_run_id,
                eligibility=plan.eligibility,
                checks=[
                    *plan.checks,
                    CheckResult(
                        name="undo_dry_run",
                        status=CheckStatus.SKIP,
                        message="Undo execution was not requested with apply mode.",
                    ),
                ],
                blockers=plan.blockers,
                execution_items=[
                    UndoExecutionItem(
                        entry_id=entry.entry_id,
                        operation_type=entry.operation_type,
                        status=UndoExecutionStatus.PLANNED,
                        message="Undo was planned but not executed.",
                        original_path=entry.original_path,
                        details=entry.details,
                    )
                    for entry in plan.entry_assessments
                ],
                metadata=plan.metadata,
                recommendations=plan.recommendations,
            )

        if plan.eligibility != UndoEligibility.REVERSIBLE_NOW:
            return UndoExecutionResult(
                domain="repair.undo",
                action="apply",
                summary=(
                    "Undo execution was blocked because the selected run is not safely "
                    "reversible now."
                ),
                repair_run_id="",
                target_repair_run_id=repair_run_id,
                eligibility=plan.eligibility,
                checks=[
                    *plan.checks,
                    CheckResult(
                        name="undo_apply_guard",
                        status=CheckStatus.FAIL,
                        message="Undo apply was blocked by current restore/undo eligibility.",
                    ),
                ],
                blockers=plan.blockers,
                execution_items=[],
                metadata=plan.metadata,
                recommendations=plan.recommendations,
            )

        source_entries = self.store.load_journal_entries(settings, repair_run_id)
        source_entries = self._select_entries(
            source_entries,
            tuple(str(entry_id) for entry_id in plan.metadata["selected_entry_ids"]),
        )
        db_fingerprint = fingerprint_payload([entry.entry_id for entry in source_entries])
        file_fingerprint = fingerprint_payload(
            [self._file_state_payload(entry) for entry in source_entries]
        )
        scope = {
            "domain": "repair.undo",
            "action": "apply",
            "target_repair_run_id": repair_run_id,
            "selected_entry_ids": [entry.entry_id for entry in source_entries],
        }
        plan_token = create_plan_token(
            scope=scope,
            db_fingerprint=db_fingerprint,
            file_fingerprint=file_fingerprint,
        )
        undo_run = RepairRun.new(
            repair_run_id=uuid4().hex,
            scope=scope,
            status=RepairRunStatus.RUNNING,
            live_state_fingerprint=build_live_state_fingerprint(
                db_fingerprint=db_fingerprint,
                file_fingerprint=file_fingerprint,
            ),
            plan_token_id=plan_token.token_id,
        )
        self.store.create_run(settings, repair_run=undo_run, plan_token=plan_token)

        guard = validate_plan_token(
            plan_token,
            scope=scope,
            db_fingerprint=db_fingerprint,
            file_fingerprint=file_fingerprint,
        )
        guard_check = CheckResult(
            name="undo_apply_guard",
            status=CheckStatus.PASS if guard.valid else CheckStatus.FAIL,
            message=guard.reason,
            details={
                "token_id": guard.token_id,
                "expected_db_fingerprint": guard.expected_db_fingerprint,
                "expected_file_fingerprint": guard.expected_file_fingerprint,
                "actual_db_fingerprint": guard.actual_db_fingerprint,
                "actual_file_fingerprint": guard.actual_file_fingerprint,
            },
        )
        if not guard.valid:
            undo_run.finish(RepairRunStatus.FAILED)
            self.store.update_run(settings, undo_run)
            return UndoExecutionResult(
                domain="repair.undo",
                action="apply",
                summary="Undo execution stopped because live state drift was detected.",
                repair_run_id=undo_run.repair_run_id,
                target_repair_run_id=repair_run_id,
                eligibility=plan.eligibility,
                checks=[*plan.checks, guard_check, self._journal_check(settings, undo_run)],
                blockers=plan.blockers,
                execution_items=[],
                metadata={
                    **plan.metadata,
                    "undo_repair_run_id": undo_run.repair_run_id,
                    "undo_repair_run_path": str(
                        repair_run_directory(settings, undo_run.repair_run_id)
                    ),
                },
                recommendations=[
                    "Re-run undo planning to bind a fresh plan token to the current live state.",
                ],
            )

        execution_items = [
            self._execute_entry(settings, undo_run, entry) for entry in source_entries
        ]
        undo_run.finish(self._final_status(execution_items))
        self.store.update_run(settings, undo_run)

        return UndoExecutionResult(
            domain="repair.undo",
            action="apply",
            summary=self._execution_summary(execution_items),
            repair_run_id=undo_run.repair_run_id,
            target_repair_run_id=repair_run_id,
            eligibility=plan.eligibility,
            checks=[*plan.checks, guard_check, self._journal_check(settings, undo_run)],
            blockers=plan.blockers,
            execution_items=execution_items,
            metadata={
                **plan.metadata,
                "undo_repair_run_id": undo_run.repair_run_id,
                "undo_repair_run_path": str(
                    repair_run_directory(settings, undo_run.repair_run_id)
                ),
            },
            recommendations=[
                "Inspect the new undo repair run journal for exact restored mode values.",
            ],
        )

    def _select_entries(
        self,
        entries: list[RepairJournalEntry],
        entry_ids: tuple[str, ...],
    ) -> list[RepairJournalEntry]:
        if not entry_ids:
            return [entry for entry in entries if entry.undo_type != UndoType.NONE]
        selected = set(entry_ids)
        return [entry for entry in entries if entry.entry_id in selected]

    def _assess_entry(self, entry: RepairJournalEntry) -> UndoEntryAssessment:
        blockers: list[UndoBlocker] = []
        details: dict[str, object] = {}

        if entry.status != RepairJournalEntryStatus.APPLIED:
            blockers.append(
                UndoBlocker(
                    code="entry_not_applied",
                    message="Only applied journal entries can be undone.",
                    severity="error",
                    entry_id=entry.entry_id,
                )
            )
        if entry.undo_type != UndoType.RESTORE_PERMISSIONS:
            blockers.append(
                UndoBlocker(
                    code="unsupported_undo_type",
                    message=(
                        "This journal entry does not support targeted undo in the current phase."
                    ),
                    severity="error",
                    entry_id=entry.entry_id,
                )
            )

        path_value = entry.undo_payload.get("path") or entry.original_path
        old_mode = entry.undo_payload.get("old_mode")
        new_mode = entry.undo_payload.get("new_mode")
        details["path"] = path_value
        details["old_mode"] = old_mode
        details["new_mode"] = new_mode

        if not path_value or old_mode is None or new_mode is None:
            blockers.append(
                UndoBlocker(
                    code="missing_undo_payload",
                    message="The journal entry is missing path or mode data required for undo.",
                    severity="error",
                    entry_id=entry.entry_id,
                )
            )
            return UndoEntryAssessment(
                entry_id=entry.entry_id,
                operation_type=entry.operation_type,
                eligibility=UndoEligibility.NOT_REVERSIBLE,
                asset_id=entry.asset_id,
                original_path=entry.original_path,
                undo_type=entry.undo_type.value,
                blockers=tuple(blockers),
                details=details,
            )

        path = Path(str(path_value))
        try:
            current_mode = S_IMODE(self.filesystem.stat_path(path).st_mode)
        except FileNotFoundError:
            blockers.append(
                UndoBlocker(
                    code="missing_file_for_undo",
                    message=(
                        "The file no longer exists, so targeted undo cannot restore permissions."
                    ),
                    severity="error",
                    entry_id=entry.entry_id,
                )
            )
            return UndoEntryAssessment(
                entry_id=entry.entry_id,
                operation_type=entry.operation_type,
                eligibility=UndoEligibility.REQUIRES_FULL_RESTORE,
                asset_id=entry.asset_id,
                original_path=entry.original_path,
                undo_type=entry.undo_type.value,
                blockers=tuple(blockers),
                details=details,
            )

        details["current_mode"] = current_mode
        if int(current_mode) != int(new_mode):
            blockers.append(
                UndoBlocker(
                    code="current_mode_drift",
                    message=(
                        "Current file mode differs from the recorded post-repair mode. "
                        "Automatic targeted undo is blocked."
                    ),
                    severity="error",
                    entry_id=entry.entry_id,
                )
            )
            return UndoEntryAssessment(
                entry_id=entry.entry_id,
                operation_type=entry.operation_type,
                eligibility=UndoEligibility.REQUIRES_FULL_RESTORE,
                asset_id=entry.asset_id,
                original_path=entry.original_path,
                undo_type=entry.undo_type.value,
                blockers=tuple(blockers),
                details=details,
            )

        return UndoEntryAssessment(
            entry_id=entry.entry_id,
            operation_type=entry.operation_type,
            eligibility=(
                UndoEligibility.NOT_REVERSIBLE if blockers else UndoEligibility.REVERSIBLE_NOW
            ),
            asset_id=entry.asset_id,
            original_path=entry.original_path,
            undo_type=entry.undo_type.value,
            blockers=tuple(blockers),
            details=details,
        )

    def _global_blockers(
        self,
        run: RepairRun,
        entries: list[RepairJournalEntry],
        assessments: list[UndoEntryAssessment],
    ) -> list[UndoBlocker]:
        blockers: list[UndoBlocker] = []
        if run.status != RepairRunStatus.COMPLETED:
            blockers.append(
                UndoBlocker(
                    code="repair_run_not_stable",
                    message=(
                        "Target repair run is not completed. Partial or failed runs should be "
                        "handled through full restore analysis first."
                    ),
                    severity="error",
                )
            )
        if not assessments:
            blockers.append(
                UndoBlocker(
                    code="no_undoable_entries",
                    message="No journal entries with undo capability were selected.",
                    severity="error",
                )
            )
        if any(entry.status == RepairJournalEntryStatus.FAILED for entry in entries):
            blockers.append(
                UndoBlocker(
                    code="repair_run_contains_failed_entries",
                    message=(
                        "The target repair run contains failed journal entries. Full restore may "
                        "be safer than partial targeted undo."
                    ),
                    severity="error",
                )
            )
        return blockers

    def _eligibility(
        self,
        assessments: list[UndoEntryAssessment],
        blockers: list[UndoBlocker],
    ) -> UndoEligibility:
        if blockers:
            return UndoEligibility.REQUIRES_FULL_RESTORE
        if not assessments:
            return UndoEligibility.NOT_REVERSIBLE
        eligibilities = {assessment.eligibility for assessment in assessments}
        if eligibilities == {UndoEligibility.REVERSIBLE_NOW}:
            return UndoEligibility.REVERSIBLE_NOW
        if UndoEligibility.REQUIRES_FULL_RESTORE in eligibilities:
            return UndoEligibility.REQUIRES_FULL_RESTORE
        if UndoEligibility.NOT_REVERSIBLE in eligibilities:
            return UndoEligibility.NOT_REVERSIBLE
        return UndoEligibility.PARTIALLY_REVERSIBLE

    def _plan_checks(
        self,
        run: RepairRun,
        assessments: list[UndoEntryAssessment],
    ) -> list[CheckResult]:
        return [
            CheckResult(
                name="target_repair_run",
                status=CheckStatus.PASS,
                message=f"Loaded target repair run `{run.repair_run_id}`.",
                details={
                    "status": run.status.value,
                    "pre_repair_snapshot_id": run.pre_repair_snapshot_id,
                },
            ),
            CheckResult(
                name="undo_entry_selection",
                status=CheckStatus.PASS if assessments else CheckStatus.FAIL,
                message=f"Selected {len(assessments)} undo-capable journal entries.",
                details={"selected_entries": [entry.entry_id for entry in assessments]},
            ),
        ]

    def _plan_summary(
        self,
        eligibility: UndoEligibility,
        assessments: list[UndoEntryAssessment],
    ) -> str:
        return (
            f"Undo planning classified {len(assessments)} journal entries as "
            f"`{eligibility.value}`."
        )

    def _plan_recommendations(self, eligibility: UndoEligibility) -> list[str]:
        if eligibility == UndoEligibility.REVERSIBLE_NOW:
            return [
                "Runtime permission repair can be reverted through targeted undo in this phase.",
            ]
        if eligibility == UndoEligibility.REQUIRES_FULL_RESTORE:
            return [
                "Use full restore simulation and review blockers before mutating live state.",
            ]
        return ["Targeted undo is not fully available for the selected repair run."]

    def _file_state_payload(self, entry: RepairJournalEntry) -> dict[str, object]:
        path = Path(str(entry.undo_payload.get("path") or entry.original_path or ""))
        current_mode: int | None = None
        try:
            current_mode = S_IMODE(self.filesystem.stat_path(path).st_mode)
        except OSError:
            current_mode = None
        return {
            "entry_id": entry.entry_id,
            "path": str(path),
            "current_mode": current_mode,
            "expected_new_mode": entry.undo_payload.get("new_mode"),
        }

    def _execute_entry(
        self,
        settings: AppSettings,
        undo_run: RepairRun,
        entry: RepairJournalEntry,
    ) -> UndoExecutionItem:
        path = Path(str(entry.undo_payload["path"]))
        old_mode = int(entry.undo_payload["old_mode"])
        current_mode: int | None = None
        try:
            current_mode = S_IMODE(self.filesystem.stat_path(path).st_mode)
            self.filesystem.set_permissions(path, old_mode)
            restored_mode = S_IMODE(self.filesystem.stat_path(path).st_mode)
            item = UndoExecutionItem(
                entry_id=entry.entry_id,
                operation_type=entry.operation_type,
                status=UndoExecutionStatus.APPLIED,
                message="Permission mode was restored from journal data.",
                original_path=str(path),
                details={
                    "previous_mode": current_mode,
                    "restored_mode": restored_mode,
                    "source_repair_run_id": entry.repair_run_id,
                },
            )
            journal_status = RepairJournalEntryStatus.APPLIED
            error_details = None
        except FileNotFoundError:
            item = UndoExecutionItem(
                entry_id=entry.entry_id,
                operation_type=entry.operation_type,
                status=UndoExecutionStatus.FAILED,
                message="Undo failed because the file is missing.",
                original_path=str(path),
                details={"source_repair_run_id": entry.repair_run_id},
            )
            journal_status = RepairJournalEntryStatus.FAILED
            error_details = {"reason": item.message}
        except PermissionError:
            item = UndoExecutionItem(
                entry_id=entry.entry_id,
                operation_type=entry.operation_type,
                status=UndoExecutionStatus.FAILED,
                message="Undo failed because the current process cannot chmod the file.",
                original_path=str(path),
                details={
                    "previous_mode": current_mode,
                    "source_repair_run_id": entry.repair_run_id,
                },
            )
            journal_status = RepairJournalEntryStatus.FAILED
            error_details = {"reason": item.message}

        self.store.append_journal_entry(
            settings,
            RepairJournalEntry(
                entry_id=uuid4().hex,
                repair_run_id=undo_run.repair_run_id,
                operation_type="undo_restore_permissions",
                status=journal_status,
                asset_id=entry.asset_id,
                table=None,
                old_db_values=None,
                new_db_values=None,
                original_path=str(path),
                quarantine_path=None,
                undo_type=UndoType.NONE,
                undo_payload=item.details,
                error_details=error_details,
            ),
        )
        return item

    def _final_status(self, items: list[UndoExecutionItem]) -> RepairRunStatus:
        if any(item.status == UndoExecutionStatus.FAILED for item in items):
            if any(item.status == UndoExecutionStatus.APPLIED for item in items):
                return RepairRunStatus.PARTIAL
            return RepairRunStatus.FAILED
        return RepairRunStatus.COMPLETED

    def _execution_summary(self, items: list[UndoExecutionItem]) -> str:
        applied = sum(1 for item in items if item.status == UndoExecutionStatus.APPLIED)
        failed = sum(1 for item in items if item.status == UndoExecutionStatus.FAILED)
        return f"Targeted undo restored {applied} journal entries and failed {failed}."

    def _journal_check(self, settings: AppSettings, repair_run: RepairRun) -> CheckResult:
        return CheckResult(
            name="undo_journal",
            status=CheckStatus.PASS,
            message="Undo execution persisted a dedicated repair run and journal.",
            details={
                "repair_run_id": repair_run.repair_run_id,
                "repair_run_path": str(repair_run_directory(settings, repair_run.repair_run_id)),
            },
        )
