from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.consistency.models import (
    ConsistencyFinding,
    ConsistencyRepairAction,
    ConsistencyRepairMode,
    ConsistencyRepairPlan,
    ConsistencyRepairResult,
    ConsistencyRepairStatus,
    ConsistencySummary,
)
from immich_doctor.consistency.service import (
    CATEGORY_SPECS,
    CONSISTENCY_SCHEMA_DETECTOR_NAME,
    SAFE_DELETE_CATEGORIES,
    ConsistencyCollector,
    ConsistencyValidationService,
)
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus


@dataclass(slots=True)
class ConsistencyRepairService:
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    sample_limit: int = 3

    def run(
        self,
        settings: AppSettings,
        *,
        categories: tuple[str, ...],
        finding_ids: tuple[str, ...],
        all_safe: bool,
        apply: bool,
    ) -> ConsistencyRepairResult:
        dsn = settings.postgres_dsn_value()
        if not dsn:
            return self._error_result(
                settings=settings,
                summary="Consistency repair failed because database access is not configured.",
                message="Database DSN is not configured.",
            )

        timeout = settings.postgres_connect_timeout_seconds
        connection_check = self.postgres.validate_connection(dsn, timeout)
        if connection_check.status == CheckStatus.FAIL:
            return ConsistencyRepairResult(
                domain="consistency",
                action="repair",
                summary="Consistency repair failed because PostgreSQL could not be reached.",
                checks=[connection_check],
                repair_plan=ConsistencyRepairPlan(
                    selected_categories=categories,
                    selected_ids=finding_ids,
                    all_safe=all_safe,
                ),
                consistency_summary=ConsistencySummary(
                    profile_name=CONSISTENCY_SCHEMA_DETECTOR_NAME,
                    profile_supported=False,
                ),
                metadata={"environment": settings.environment, "dry_run": not apply},
            )

        collected = ConsistencyCollector(
            postgres=self.postgres,
            filesystem=self.filesystem,
            sample_limit=self.sample_limit,
        ).collect(dsn, timeout)
        checks = [connection_check, *collected.checks]

        selected_categories = self._resolve_selected_categories(categories, all_safe)
        matched_findings = self._select_findings(
            findings=collected.findings,
            selected_categories=selected_categories,
            selected_ids=finding_ids,
        )

        actions = self._build_actions(
            dsn=dsn,
            timeout=timeout,
            findings=matched_findings,
            selected_categories=selected_categories,
            selected_ids=finding_ids,
            apply=apply,
            profile_supported=collected.profile_supported,
        )

        if apply and any(action.applied for action in actions):
            post_validation = ConsistencyValidationService(
                postgres=self.postgres,
                filesystem=self.filesystem,
                sample_limit=self.sample_limit,
            ).run(settings)
            checks.append(
                CheckResult(
                    name="post_repair_validation",
                    status=post_validation.overall_status,
                    message=post_validation.summary,
                    details={"severity": "info"},
                )
            )

        return ConsistencyRepairResult(
            domain="consistency",
            action="repair",
            summary=self._build_summary(actions, apply=apply),
            checks=checks,
            repair_plan=ConsistencyRepairPlan(
                selected_categories=selected_categories,
                selected_ids=finding_ids,
                all_safe=all_safe,
                actions=tuple(actions),
            ),
            consistency_summary=collected.summary,
            recommendations=self._recommendations(apply=apply),
            metadata={"environment": settings.environment, "dry_run": not apply},
        )

    def _error_result(
        self,
        settings: AppSettings,
        *,
        summary: str,
        message: str,
    ) -> ConsistencyRepairResult:
        return ConsistencyRepairResult(
            domain="consistency",
            action="repair",
            summary=summary,
            checks=[
                CheckResult(
                    name="postgres_connection",
                    status=CheckStatus.FAIL,
                    message=message,
                )
            ],
            repair_plan=ConsistencyRepairPlan(),
            consistency_summary=ConsistencySummary(
                profile_name=CONSISTENCY_SCHEMA_DETECTOR_NAME,
                profile_supported=False,
            ),
            metadata={"environment": settings.environment, "dry_run": True},
        )

    def _resolve_selected_categories(
        self,
        categories: tuple[str, ...],
        all_safe: bool,
    ) -> tuple[str, ...]:
        if all_safe:
            return tuple(dict.fromkeys([*categories, *SAFE_DELETE_CATEGORIES]))
        return tuple(dict.fromkeys(categories))

    def _select_findings(
        self,
        *,
        findings: list[ConsistencyFinding],
        selected_categories: tuple[str, ...],
        selected_ids: tuple[str, ...],
    ) -> list[ConsistencyFinding]:
        if not selected_categories and not selected_ids:
            return []
        selected = []
        for finding in findings:
            if finding.category in selected_categories or finding.finding_id in selected_ids:
                selected.append(finding)
        return selected

    def _build_actions(
        self,
        *,
        dsn: str,
        timeout: int,
        findings: list[ConsistencyFinding],
        selected_categories: tuple[str, ...],
        selected_ids: tuple[str, ...],
        apply: bool,
        profile_supported: bool,
    ) -> list[ConsistencyRepairAction]:
        if not profile_supported:
            return [
                ConsistencyRepairAction(
                    category="schema.unsupported",
                    repair_mode=ConsistencyRepairMode.INSPECT_ONLY,
                    status=ConsistencyRepairStatus.SKIPPED,
                    message=(
                        "Repair skipped because the current PostgreSQL schema is unsupported "
                        "for the consistency framework."
                    ),
                    dry_run=not apply,
                )
            ]

        if not selected_categories and not selected_ids:
            return [
                ConsistencyRepairAction(
                    category="selection.none",
                    repair_mode=ConsistencyRepairMode.INSPECT_ONLY,
                    status=ConsistencyRepairStatus.SKIPPED,
                    message=(
                        "No repair selectors provided. Use --category, --id, or --all-safe "
                        "to choose findings."
                    ),
                    dry_run=not apply,
                )
            ]

        if not findings:
            return [
                ConsistencyRepairAction(
                    category="selection.empty",
                    repair_mode=ConsistencyRepairMode.INSPECT_ONLY,
                    status=ConsistencyRepairStatus.SKIPPED,
                    message="No findings matched the selected categories or IDs.",
                    dry_run=not apply,
                )
            ]

        grouped: dict[str, list[ConsistencyFinding]] = {}
        for finding in findings:
            grouped.setdefault(finding.category, []).append(finding)

        actions: list[ConsistencyRepairAction] = []
        for category_name, category_findings in grouped.items():
            spec = CATEGORY_SPECS[category_name]
            asset_reference_column = self._asset_reference_column(category_findings)
            if spec.repair_mode == ConsistencyRepairMode.INSPECT_ONLY:
                actions.append(
                    ConsistencyRepairAction(
                        category=category_name,
                        repair_mode=spec.repair_mode,
                        status=ConsistencyRepairStatus.SKIPPED,
                        message=(
                            f"Selected findings matched inspect-only category `{category_name}`. "
                            "No mutation is allowed in this step."
                        ),
                        finding_ids=tuple(finding.finding_id for finding in category_findings),
                        row_count=sum(finding.row_count for finding in category_findings),
                        sample_findings=tuple(category_findings[: self.sample_limit]),
                        dry_run=not apply,
                        applied=False,
                    )
                )
                continue

            if not apply:
                actions.append(
                    ConsistencyRepairAction(
                        category=category_name,
                        repair_mode=spec.repair_mode,
                        status=ConsistencyRepairStatus.WOULD_REPAIR,
                        message=f"Dry-run would repair category `{category_name}`.",
                        target_table="public.album_asset",
                        finding_ids=tuple(finding.finding_id for finding in category_findings),
                        row_count=sum(finding.row_count for finding in category_findings),
                        sample_findings=tuple(category_findings[: self.sample_limit]),
                        dry_run=True,
                        applied=False,
                        backup_sql=self._backup_sql(
                            category_name,
                            asset_reference_column=asset_reference_column,
                        ),
                    )
                )
                continue

            deleted_count = 0
            for finding in category_findings:
                deleted_count += self._delete_finding(
                    dsn,
                    timeout,
                    finding,
                    asset_reference_column=asset_reference_column,
                )

            actions.append(
                ConsistencyRepairAction(
                    category=category_name,
                    repair_mode=spec.repair_mode,
                    status=ConsistencyRepairStatus.REPAIRED,
                    message=f"Repaired selected findings in category `{category_name}`.",
                    target_table="public.album_asset",
                    finding_ids=tuple(finding.finding_id for finding in category_findings),
                    row_count=deleted_count,
                    sample_findings=tuple(category_findings[: self.sample_limit]),
                    dry_run=False,
                    applied=deleted_count > 0,
                    backup_sql=self._backup_sql(
                        category_name,
                        asset_reference_column=asset_reference_column,
                    ),
                )
            )
        return actions

    def _delete_finding(
        self,
        dsn: str,
        timeout: int,
        finding: ConsistencyFinding,
        *,
        asset_reference_column: str | None,
    ) -> int:
        if asset_reference_column is None:
            raise ValueError("Asset reference column could not be resolved for repair.")
        return self.postgres.delete_album_asset_rows_by_keys(
            dsn,
            timeout,
            album_id=finding.key_fields["albumId"],
            asset_id=finding.key_fields["assetId"],
            missing_target_table=(
                "asset" if finding.category == SAFE_DELETE_CATEGORIES[0] else "album"
            ),
            asset_reference_column=asset_reference_column,
        )

    def _backup_sql(self, category: str, *, asset_reference_column: str | None) -> str:
        missing_target = "asset" if category == SAFE_DELETE_CATEGORIES[0] else "album"
        if missing_target == "asset" and asset_reference_column is None:
            return (
                "-- immich-doctor could not derive the album_asset asset reference column "
                "for backup SQL generation"
            )
        target_column = (
            f'"{asset_reference_column}"'
            if missing_target == "asset" and asset_reference_column
            else '"albumId"'
        )
        return (
            "CREATE TABLE album_asset_orphan_backup AS "
            "SELECT * FROM public.album_asset AS link "
            f"WHERE NOT EXISTS (SELECT 1 FROM public.{missing_target} AS target "
            f"WHERE target.id = link.{target_column});"
        )

    def _asset_reference_column(self, findings: list[ConsistencyFinding]) -> str | None:
        for finding in findings:
            value = finding.sample_metadata.get("assetReferenceColumn")
            if value:
                return str(value)
        return None

    def _build_summary(self, actions: list[ConsistencyRepairAction], *, apply: bool) -> str:
        if not apply:
            planned_rows = sum(action.row_count for action in actions)
            if planned_rows == 0:
                return "Consistency repair dry-run found no selected repairable findings."
            return (
                f"Consistency repair dry-run planned changes for {planned_rows} selected "
                "repairable rows."
            )
        repaired_rows = sum(action.row_count for action in actions if action.applied)
        if repaired_rows == 0:
            return "Consistency repair apply mode changed no rows."
        return f"Consistency repair applied {repaired_rows} row changes."

    def _recommendations(self, *, apply: bool) -> list[str]:
        if not apply:
            return [
                "Review the selected categories or IDs and rerun with --apply "
                "for safe_delete findings.",
            ]
        return [
            "Review the post-repair validation summary and remaining inspect-only categories.",
        ]
