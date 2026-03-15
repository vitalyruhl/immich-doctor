from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from stat import S_IMODE
from uuid import uuid4

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.backup.core.models import SnapshotKind
from immich_doctor.backup.orchestration import BackupFilesService
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.repair import (
    RepairJournalEntry,
    RepairJournalEntryStatus,
    RepairJournalStore,
    RepairRun,
    RepairRunStatus,
    UndoType,
    build_live_state_fingerprint,
    create_plan_token,
    fingerprint_payload,
    validate_plan_token,
)
from immich_doctor.repair.paths import repair_run_directory
from immich_doctor.runtime.metadata_failures.models import (
    MetadataFailureDiagnostic,
    MetadataFailureInspectResult,
    MetadataFailureRepairResult,
    MetadataRepairAction,
    MetadataRepairStatus,
    SuggestedAction,
)
from immich_doctor.runtime.metadata_failures.service import RuntimeMetadataFailuresInspectService


@dataclass(slots=True)
class RuntimeMetadataFailuresRepairService:
    inspect_service: RuntimeMetadataFailuresInspectService = field(
        default_factory=RuntimeMetadataFailuresInspectService
    )
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    repair_store: RepairJournalStore = field(default_factory=RepairJournalStore)
    backup_files_service: BackupFilesService = field(default_factory=BackupFilesService)

    def run(
        self,
        settings: AppSettings,
        *,
        apply: bool,
        limit: int | None,
        offset: int,
        diagnostic_ids: tuple[str, ...],
        retry_jobs: bool,
        requeue: bool,
        fix_permissions: bool,
        quarantine_corrupt: bool,
        mark_unrecoverable: bool,
    ) -> MetadataFailureRepairResult:
        inspect_result = self.inspect_service.run(settings, limit=limit, offset=offset)
        diagnostics = self._filter_diagnostics(inspect_result.diagnostics, diagnostic_ids)
        scope = self._build_scope(
            diagnostics=diagnostics,
            apply=apply,
            limit=limit,
            offset=offset,
            diagnostic_ids=diagnostic_ids,
        )
        db_fingerprint = self._db_fingerprint(diagnostics)
        file_fingerprint = self._file_fingerprint(diagnostics)
        plan_token = create_plan_token(
            scope=scope,
            db_fingerprint=db_fingerprint,
            file_fingerprint=file_fingerprint,
        )
        repair_run = RepairRun.new(
            repair_run_id=uuid4().hex,
            scope=scope,
            status=RepairRunStatus.RUNNING,
            live_state_fingerprint=build_live_state_fingerprint(
                db_fingerprint=db_fingerprint,
                file_fingerprint=file_fingerprint,
            ),
            plan_token_id=plan_token.token_id,
        )
        self.repair_store.create_run(settings, repair_run=repair_run, plan_token=plan_token)

        selected_actions = self._selected_actions(
            retry_jobs=retry_jobs,
            requeue=requeue,
            fix_permissions=fix_permissions,
            quarantine_corrupt=quarantine_corrupt,
            mark_unrecoverable=mark_unrecoverable,
        )
        if not selected_actions:
            selected_actions = {diagnostic.suggested_action for diagnostic in diagnostics}

        guard_check: CheckResult | None = None
        if apply:
            latest_inspect = self.inspect_service.run(settings, limit=limit, offset=offset)
            latest_diagnostics = self._filter_diagnostics(
                latest_inspect.diagnostics,
                diagnostic_ids,
            )
            guard_result = validate_plan_token(
                plan_token,
                scope=scope,
                db_fingerprint=self._db_fingerprint(latest_diagnostics),
                file_fingerprint=self._file_fingerprint(latest_diagnostics),
            )
            guard_check = CheckResult(
                name="repair_apply_guard",
                status=CheckStatus.PASS if guard_result.valid else CheckStatus.FAIL,
                message=guard_result.reason,
                details=asdict(guard_result),
            )
            if not guard_result.valid:
                repair_run.finish(RepairRunStatus.FAILED)
                self.repair_store.update_run(settings, repair_run)
                return MetadataFailureRepairResult(
                    domain="runtime.metadata_failures",
                    action="repair",
                    summary=(
                        "Metadata failure repair stopped because the live state changed "
                        "before apply."
                    ),
                    checks=[
                        *inspect_result.checks,
                        self._journal_check(settings, repair_run),
                        guard_check,
                    ],
                    diagnostics=diagnostics,
                    repair_actions=[],
                    recommendations=[
                        (
                            "Re-run inspect or repair to create a fresh plan token against the "
                            "current live state."
                        ),
                    ],
                    metadata=self._result_metadata(
                        settings,
                        repair_run,
                        plan_token,
                        apply=apply,
                        diagnostic_ids=diagnostic_ids,
                        selected_actions=selected_actions,
                    ),
                )

            snapshot_result = self.backup_files_service.run(
                settings,
                snapshot_kind=SnapshotKind.PRE_REPAIR,
                repair_run_id=repair_run.repair_run_id,
                source_fingerprint=repair_run.live_state_fingerprint,
            )
            if snapshot_result.status != "success" or snapshot_result.snapshot is None:
                repair_run.finish(RepairRunStatus.FAILED)
                self.repair_store.update_run(settings, repair_run)
                snapshot_check = CheckResult(
                    name="pre_repair_snapshot",
                    status=CheckStatus.FAIL,
                    message=(
                        "Pre-repair snapshot creation failed. Apply stopped before mutating files."
                    ),
                    details={
                        "summary": snapshot_result.summary,
                        "warnings": list(snapshot_result.warnings),
                        "details": snapshot_result.details,
                    },
                )
                return MetadataFailureRepairResult(
                    domain="runtime.metadata_failures",
                    action="repair",
                    summary=(
                        "Metadata failure repair stopped because the pre-repair snapshot could "
                        "not be created."
                    ),
                    checks=[
                        *inspect_result.checks,
                        self._journal_check(settings, repair_run),
                        guard_check,
                        snapshot_check,
                    ],
                    diagnostics=diagnostics,
                    repair_actions=[],
                    recommendations=[
                        (
                            "Configure and verify backup files so a pre-repair snapshot can be "
                            "created."
                        ),
                    ],
                    metadata=self._result_metadata(
                        settings,
                        repair_run,
                        plan_token,
                        apply=apply,
                        diagnostic_ids=diagnostic_ids,
                        selected_actions=selected_actions,
                    ),
                )

            repair_run.pre_repair_snapshot_id = snapshot_result.snapshot.snapshot_id
            self.repair_store.update_run(settings, repair_run)
            snapshot_check = CheckResult(
                name="pre_repair_snapshot",
                status=CheckStatus.PASS,
                message="Pre-repair snapshot metadata was created before apply.",
                details={
                    "snapshot_id": snapshot_result.snapshot.snapshot_id,
                    "snapshot_kind": snapshot_result.snapshot.kind.value,
                    "snapshot_manifest_path": snapshot_result.snapshot.manifest_path.as_posix(),
                    "coverage": snapshot_result.snapshot.coverage.value,
                },
            )
        else:
            snapshot_check = CheckResult(
                name="pre_repair_snapshot",
                status=CheckStatus.SKIP,
                message="Pre-repair snapshot creation is only attempted during apply.",
            )

        repair_actions = [
            self._plan_or_apply_action(
                diagnostic=diagnostic,
                selected_actions=selected_actions,
                apply=apply,
                repair_run=repair_run,
                settings=settings,
            )
            for diagnostic in diagnostics
        ]

        post_validation: MetadataFailureInspectResult | None = None
        if apply and any(
            action.status == MetadataRepairStatus.REPAIRED for action in repair_actions
        ):
            post_validation = self.inspect_service.run(settings, limit=limit, offset=offset)

        checks = list(inspect_result.checks)
        checks.append(self._journal_check(settings, repair_run))
        if guard_check is not None:
            checks.append(guard_check)
        checks.append(snapshot_check)
        checks.append(
            CheckResult(
                name="repair_scope",
                status=CheckStatus.PASS,
                message=(
                    "Repair planning is dry-run by default. Only explicit permission fixes are "
                    "currently apply-capable."
                ),
            )
        )

        repair_run.finish(self._final_run_status(repair_actions))
        self.repair_store.update_run(settings, repair_run)

        return MetadataFailureRepairResult(
            domain="runtime.metadata_failures",
            action="repair",
            summary=self._build_summary(repair_actions, apply),
            checks=checks,
            diagnostics=diagnostics,
            repair_actions=repair_actions,
            post_validation=post_validation,
            recommendations=self._recommendations(repair_actions),
            metadata=self._result_metadata(
                settings,
                repair_run,
                plan_token,
                apply=apply,
                diagnostic_ids=diagnostic_ids,
                selected_actions=selected_actions,
            ),
        )

    def _filter_diagnostics(
        self,
        diagnostics: list[MetadataFailureDiagnostic],
        diagnostic_ids: tuple[str, ...],
    ) -> list[MetadataFailureDiagnostic]:
        if not diagnostic_ids:
            return diagnostics
        requested_ids = set(diagnostic_ids)
        return [
            diagnostic for diagnostic in diagnostics if diagnostic.diagnostic_id in requested_ids
        ]

    def _plan_or_apply_action(
        self,
        *,
        diagnostic: MetadataFailureDiagnostic,
        selected_actions: set[SuggestedAction],
        apply: bool,
        repair_run: RepairRun,
        settings: AppSettings,
    ) -> MetadataRepairAction:
        matching_actions = tuple(
            action for action in diagnostic.available_actions if action in selected_actions
        )
        if not matching_actions:
            repair_action = MetadataRepairAction(
                action=diagnostic.suggested_action,
                diagnostic_id=diagnostic.diagnostic_id,
                status=MetadataRepairStatus.SKIPPED,
                reason="No selected repair flag matched this diagnostic.",
                path=diagnostic.source_path,
                supports_apply=self._supports_apply(diagnostic.suggested_action),
                dry_run=not apply,
                applied=False,
            )
            self._record_action(
                settings=settings,
                repair_run=repair_run,
                diagnostic=diagnostic,
                repair_action=repair_action,
            )
            return repair_action

        action = matching_actions[0]
        supports_apply = self._supports_apply(action)
        if not apply:
            repair_action = MetadataRepairAction(
                action=action,
                diagnostic_id=diagnostic.diagnostic_id,
                status=MetadataRepairStatus.PLANNED,
                reason=self._plan_reason(action, diagnostic),
                path=diagnostic.source_path,
                supports_apply=supports_apply,
                dry_run=True,
                applied=False,
                details={"confidence": diagnostic.confidence.value},
            )
            self._record_action(
                settings=settings,
                repair_run=repair_run,
                diagnostic=diagnostic,
                repair_action=repair_action,
            )
            return repair_action

        if action == SuggestedAction.FIX_PERMISSIONS:
            repair_action = self._apply_permission_fix(diagnostic)
            self._record_action(
                settings=settings,
                repair_run=repair_run,
                diagnostic=diagnostic,
                repair_action=repair_action,
            )
            return repair_action

        repair_action = MetadataRepairAction(
            action=action,
            diagnostic_id=diagnostic.diagnostic_id,
            status=MetadataRepairStatus.SKIPPED,
            reason=(
                "No safe automatic apply primitive is implemented for this action in the current "
                "phase."
            ),
            path=diagnostic.source_path,
            supports_apply=False,
            dry_run=False,
            applied=False,
        )
        self._record_action(
            settings=settings,
            repair_run=repair_run,
            diagnostic=diagnostic,
            repair_action=repair_action,
        )
        return repair_action

    def _apply_permission_fix(
        self,
        diagnostic: MetadataFailureDiagnostic,
    ) -> MetadataRepairAction:
        source_path = Path(diagnostic.source_path)
        old_mode: int | None = None
        try:
            old_mode = S_IMODE(self.filesystem.stat_path(source_path).st_mode)
            self.filesystem.add_read_permissions(source_path)
            new_mode = S_IMODE(self.filesystem.stat_path(source_path).st_mode)
        except FileNotFoundError:
            return MetadataRepairAction(
                action=SuggestedAction.FIX_PERMISSIONS,
                diagnostic_id=diagnostic.diagnostic_id,
                status=MetadataRepairStatus.FAILED,
                reason="Permission repair failed because the file is missing.",
                path=diagnostic.source_path,
                supports_apply=True,
                dry_run=False,
                applied=False,
                details={"old_mode": old_mode},
            )
        except PermissionError:
            return MetadataRepairAction(
                action=SuggestedAction.FIX_PERMISSIONS,
                diagnostic_id=diagnostic.diagnostic_id,
                status=MetadataRepairStatus.FAILED,
                reason=(
                    "Permission repair failed because the current process cannot chmod the file."
                ),
                path=diagnostic.source_path,
                supports_apply=True,
                dry_run=False,
                applied=False,
                details={"old_mode": old_mode},
            )
        except OSError as exc:
            return MetadataRepairAction(
                action=SuggestedAction.FIX_PERMISSIONS,
                diagnostic_id=diagnostic.diagnostic_id,
                status=MetadataRepairStatus.FAILED,
                reason=f"Permission repair failed: {exc.strerror or exc}.",
                path=diagnostic.source_path,
                supports_apply=True,
                dry_run=False,
                applied=False,
                details={"old_mode": old_mode, "error": exc.strerror or str(exc)},
            )

        return MetadataRepairAction(
            action=SuggestedAction.FIX_PERMISSIONS,
            diagnostic_id=diagnostic.diagnostic_id,
            status=MetadataRepairStatus.REPAIRED,
            reason="Read permissions were granted to the source file.",
            path=diagnostic.source_path,
            supports_apply=True,
            dry_run=False,
            applied=True,
            details={"old_mode": old_mode, "new_mode": new_mode},
        )

    def _record_action(
        self,
        *,
        settings: AppSettings,
        repair_run: RepairRun,
        diagnostic: MetadataFailureDiagnostic,
        repair_action: MetadataRepairAction,
    ) -> None:
        status_map = {
            MetadataRepairStatus.PLANNED: RepairJournalEntryStatus.PLANNED,
            MetadataRepairStatus.REPAIRED: RepairJournalEntryStatus.APPLIED,
            MetadataRepairStatus.SKIPPED: RepairJournalEntryStatus.SKIPPED,
            MetadataRepairStatus.FAILED: RepairJournalEntryStatus.FAILED,
        }
        undo_type = (
            UndoType.RESTORE_PERMISSIONS
            if repair_action.action == SuggestedAction.FIX_PERMISSIONS and repair_action.applied
            else UndoType.NONE
        )
        undo_payload = (
            {
                "path": diagnostic.source_path,
                "old_mode": repair_action.details.get("old_mode"),
                "new_mode": repair_action.details.get("new_mode"),
            }
            if undo_type == UndoType.RESTORE_PERMISSIONS
            else {}
        )
        error_details = None
        if repair_action.status == MetadataRepairStatus.FAILED:
            error_details = {
                "reason": repair_action.reason,
                "details": repair_action.details,
            }

        entry = RepairJournalEntry(
            entry_id=uuid4().hex,
            repair_run_id=repair_run.repair_run_id,
            operation_type=repair_action.action.value,
            status=status_map[repair_action.status],
            asset_id=diagnostic.asset_id,
            table=None,
            old_db_values=None,
            new_db_values=None,
            original_path=diagnostic.source_path,
            quarantine_path=None,
            undo_type=undo_type,
            undo_payload=undo_payload,
            error_details=error_details,
        )
        self.repair_store.append_journal_entry(settings, entry)

    def _selected_actions(self, **flags: bool) -> set[SuggestedAction]:
        mapping = {
            "retry_jobs": SuggestedAction.RETRY_JOBS,
            "requeue": SuggestedAction.REQUEUE,
            "fix_permissions": SuggestedAction.FIX_PERMISSIONS,
            "quarantine_corrupt": SuggestedAction.QUARANTINE_CORRUPT,
            "mark_unrecoverable": SuggestedAction.MARK_UNRECOVERABLE,
        }
        return {action for flag_name, action in mapping.items() if flags[flag_name]}

    def _supports_apply(self, action: SuggestedAction) -> bool:
        return action == SuggestedAction.FIX_PERMISSIONS

    def _plan_reason(
        self,
        action: SuggestedAction,
        diagnostic: MetadataFailureDiagnostic,
    ) -> str:
        return (
            f"Planned `{action.value}` because root cause `{diagnostic.root_cause.value}` was "
            f"classified with {diagnostic.confidence.value} confidence."
        )

    def _build_summary(
        self,
        repair_actions: list[MetadataRepairAction],
        apply: bool,
    ) -> str:
        repaired_count = sum(
            1 for action in repair_actions if action.status == MetadataRepairStatus.REPAIRED
        )
        planned_count = sum(
            1 for action in repair_actions if action.status == MetadataRepairStatus.PLANNED
        )
        skipped_count = sum(
            1 for action in repair_actions if action.status == MetadataRepairStatus.SKIPPED
        )
        failed_count = sum(
            1 for action in repair_actions if action.status == MetadataRepairStatus.FAILED
        )
        if apply:
            return (
                f"Metadata failure repair applied {repaired_count} actions, skipped "
                f"{skipped_count}, and failed {failed_count}."
            )
        return (
            f"Metadata failure repair planned {planned_count} actions and skipped {skipped_count} "
            "without mutating data."
        )

    def _recommendations(self, repair_actions: list[MetadataRepairAction]) -> list[str]:
        if any(action.action == SuggestedAction.RETRY_JOBS for action in repair_actions):
            return [
                "Healthy files with unresolved metadata extraction remain candidates for manual "
                "Immich-side retry or requeue actions.",
            ]
        return ["Unknown or unsupported actions remain intentionally non-destructive."]

    def _build_scope(
        self,
        *,
        diagnostics: list[MetadataFailureDiagnostic],
        apply: bool,
        limit: int | None,
        offset: int,
        diagnostic_ids: tuple[str, ...],
    ) -> dict[str, object]:
        return {
            "domain": "runtime.metadata_failures",
            "action": "repair",
            "apply": apply,
            "limit": limit,
            "offset": offset,
            "diagnostic_ids": list(diagnostic_ids),
            "selected_diagnostics": [diagnostic.diagnostic_id for diagnostic in diagnostics],
        }

    def _db_fingerprint(self, diagnostics: list[MetadataFailureDiagnostic]) -> str:
        return fingerprint_payload(
            [
                {
                    "diagnostic_id": diagnostic.diagnostic_id,
                    "asset_id": diagnostic.asset_id,
                    "job_name": diagnostic.job_name,
                    "root_cause": diagnostic.root_cause.value,
                }
                for diagnostic in diagnostics
            ]
        )

    def _file_fingerprint(self, diagnostics: list[MetadataFailureDiagnostic]) -> str:
        return fingerprint_payload(
            [
                {
                    "diagnostic_id": diagnostic.diagnostic_id,
                    "source_path": diagnostic.source_path,
                    "source_file_status": diagnostic.source_file_status,
                    "file_findings": [finding.to_dict() for finding in diagnostic.file_findings],
                }
                for diagnostic in diagnostics
            ]
        )

    def _final_run_status(self, repair_actions: list[MetadataRepairAction]) -> RepairRunStatus:
        if any(action.status == MetadataRepairStatus.FAILED for action in repair_actions):
            if any(action.applied for action in repair_actions):
                return RepairRunStatus.PARTIAL
            return RepairRunStatus.FAILED
        return RepairRunStatus.COMPLETED

    def _journal_check(self, settings: AppSettings, repair_run: RepairRun) -> CheckResult:
        return CheckResult(
            name="repair_journal",
            status=CheckStatus.PASS,
            message="Repair run foundation persisted manifest and journal files.",
            details={
                "repair_run_id": repair_run.repair_run_id,
                "repair_run_path": str(repair_run_directory(settings, repair_run.repair_run_id)),
                "plan_token_id": repair_run.plan_token_id,
            },
        )

    def _result_metadata(
        self,
        settings: AppSettings,
        repair_run: RepairRun,
        plan_token,
        *,
        apply: bool,
        diagnostic_ids: tuple[str, ...],
        selected_actions: set[SuggestedAction],
    ) -> dict[str, object]:
        return {
            "environment": settings.environment,
            "dry_run": not apply,
            "diagnostic_ids": list(diagnostic_ids),
            "selected_actions": sorted(action.value for action in selected_actions),
            "repair_run_id": repair_run.repair_run_id,
            "repair_run_path": str(repair_run_directory(settings, repair_run.repair_run_id)),
            "plan_token_id": plan_token.token_id,
            "pre_repair_snapshot_id": repair_run.pre_repair_snapshot_id,
        }
