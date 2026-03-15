from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
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
        selected_actions = self._selected_actions(
            retry_jobs=retry_jobs,
            requeue=requeue,
            fix_permissions=fix_permissions,
            quarantine_corrupt=quarantine_corrupt,
            mark_unrecoverable=mark_unrecoverable,
        )
        if not selected_actions:
            selected_actions = {diagnostic.suggested_action for diagnostic in diagnostics}

        repair_actions = [
            self._plan_or_apply_action(
                diagnostic=diagnostic,
                selected_actions=selected_actions,
                apply=apply,
            )
            for diagnostic in diagnostics
        ]

        post_validation: MetadataFailureInspectResult | None = None
        if apply and any(
            action.status == MetadataRepairStatus.REPAIRED for action in repair_actions
        ):
            post_validation = self.inspect_service.run(settings, limit=limit, offset=offset)

        checks = list(inspect_result.checks)
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

        return MetadataFailureRepairResult(
            domain="runtime.metadata_failures",
            action="repair",
            summary=self._build_summary(repair_actions, apply),
            checks=checks,
            diagnostics=diagnostics,
            repair_actions=repair_actions,
            post_validation=post_validation,
            recommendations=self._recommendations(repair_actions),
            metadata={
                "environment": settings.environment,
                "dry_run": not apply,
                "diagnostic_ids": list(diagnostic_ids),
                "selected_actions": sorted(action.value for action in selected_actions),
            },
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
    ) -> MetadataRepairAction:
        matching_actions = tuple(
            action for action in diagnostic.available_actions if action in selected_actions
        )
        if not matching_actions:
            return MetadataRepairAction(
                action=diagnostic.suggested_action,
                diagnostic_id=diagnostic.diagnostic_id,
                status=MetadataRepairStatus.SKIPPED,
                reason="No selected repair flag matched this diagnostic.",
                path=diagnostic.source_path,
                supports_apply=self._supports_apply(diagnostic.suggested_action),
                dry_run=not apply,
                applied=False,
            )

        action = matching_actions[0]
        supports_apply = self._supports_apply(action)
        if not apply:
            return MetadataRepairAction(
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

        if action == SuggestedAction.FIX_PERMISSIONS:
            return self._apply_permission_fix(diagnostic)

        return MetadataRepairAction(
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

    def _apply_permission_fix(
        self,
        diagnostic: MetadataFailureDiagnostic,
    ) -> MetadataRepairAction:
        try:
            self.filesystem.add_read_permissions(Path(diagnostic.source_path))
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
        )

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
                f"{skipped_count}, "
                f"and failed {failed_count}."
            )
        return (
            f"Metadata failure repair planned {planned_count} actions and skipped {skipped_count} "
            f"without mutating data."
        )

    def _recommendations(self, repair_actions: list[MetadataRepairAction]) -> list[str]:
        if any(action.action == SuggestedAction.RETRY_JOBS for action in repair_actions):
            return [
                "Healthy files with unresolved metadata extraction remain candidates for manual "
                "Immich-side retry or requeue actions.",
            ]
        return ["Unknown or unsupported actions remain intentionally non-destructive."]
