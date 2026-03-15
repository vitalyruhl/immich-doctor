from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import (
    CheckResult,
    CheckStatus,
    RepairItemStatus,
    RepairPlanItem,
    RepairReport,
)
from immich_doctor.remote.sync.inspector import RemoteSyncInspection, RemoteSyncPostgresInspector
from immich_doctor.remote.sync.service import RemoteSyncValidationService

DEFAULT_SAMPLE_LIMIT = 5


@dataclass(slots=True)
class RemoteSyncRepairService:
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)
    sample_limit: int = DEFAULT_SAMPLE_LIMIT

    def run(self, settings: AppSettings, *, apply: bool) -> RepairReport:
        dsn = settings.postgres_dsn_value()
        if not dsn:
            return RepairReport(
                domain="remote.sync",
                action="repair",
                summary="Remote sync repair failed because database access is not configured.",
                checks=[
                    CheckResult(
                        name="postgres_connection",
                        status=CheckStatus.FAIL,
                        message="Database DSN is not configured.",
                    )
                ],
                metadata={"environment": settings.environment, "dry_run": not apply},
            )

        timeout = settings.postgres_connect_timeout_seconds
        connection_check = self.postgres.validate_connection(dsn, timeout)
        if connection_check.status == CheckStatus.FAIL:
            return RepairReport(
                domain="remote.sync",
                action="repair",
                summary="Remote sync repair failed because PostgreSQL could not be reached.",
                checks=[connection_check],
                metadata={"environment": settings.environment, "dry_run": not apply},
            )

        inspection = RemoteSyncPostgresInspector(self.postgres).inspect(dsn, timeout)
        checks = [connection_check, self._scope_boundary_check()]
        checks.extend(self._schema_checks(inspection))

        plans = self._build_plans(dsn, timeout, inspection, apply=apply)
        if apply and any(plan.applied for plan in plans):
            post_validation = RemoteSyncValidationService(
                postgres=self.postgres,
                sample_limit=self.sample_limit,
            ).run(settings)
            checks.append(
                CheckResult(
                    name="post_repair_validation",
                    status=post_validation.overall_status,
                    message=post_validation.summary,
                    details={
                        "severity": "info",
                        "post_validation_status": post_validation.overall_status.value,
                    },
                )
            )
        elif apply:
            checks.append(
                CheckResult(
                    name="post_repair_validation",
                    status=CheckStatus.SKIP,
                    message="Post-repair validation was skipped because no rows were deleted.",
                    details={"severity": "info"},
                )
            )

        return RepairReport(
            domain="remote.sync",
            action="repair",
            summary=self._build_summary(plans, apply=apply),
            checks=checks,
            plans=plans,
            recommendations=self._recommendations(apply=apply),
            metadata={"environment": settings.environment, "dry_run": not apply},
        )

    def _scope_boundary_check(self) -> CheckResult:
        return CheckResult(
            name="remote_sync_scope_boundary",
            status=CheckStatus.PASS,
            message=(
                "This repair workflow only removes confirmed orphan rows from PostgreSQL "
                "`album_asset`. It does not repair mobile app SQLite state, assets, albums, "
                "or storage files."
            ),
            details={"severity": "info"},
        )

    def _schema_checks(self, inspection: RemoteSyncInspection) -> list[CheckResult]:
        checks: list[CheckResult] = []
        album_asset_table = inspection.detected_tables["album_asset"]
        if album_asset_table is None:
            checks.append(
                CheckResult(
                    name="album_asset_repair_scope",
                    status=CheckStatus.SKIP,
                    message=(
                        "Repair scope skipped because `album_asset` is missing from PostgreSQL."
                    ),
                    details={"severity": "info", "expected_table": "album_asset"},
                )
            )
            return checks

        checks.append(
            CheckResult(
                name="album_asset_repair_scope",
                status=CheckStatus.PASS,
                message=f"Repair scope confirmed for {album_asset_table.qualified_name}.",
                details={
                    "severity": "info",
                    "impacted_tables": [album_asset_table.qualified_name],
                },
            )
        )
        return checks

    def _build_plans(
        self,
        dsn: str,
        timeout: int,
        inspection: RemoteSyncInspection,
        *,
        apply: bool,
    ) -> list[RepairPlanItem]:
        album_asset_table = inspection.detected_tables["album_asset"]
        if album_asset_table is None:
            return [
                RepairPlanItem(
                    action="delete",
                    target_table="public.album_asset",
                    reason="Repair skipped because `album_asset` is missing from PostgreSQL.",
                    key_columns=(),
                    row_count=0,
                    dry_run=not apply,
                    applied=False,
                    status=RepairItemStatus.SKIPPED,
                )
            ]

        plans: list[RepairPlanItem] = []
        plans.append(
            self._plan_for_resolution(
                dsn=dsn,
                timeout=timeout,
                resolution=inspection.asset_resolution,
                paired_resolution=inspection.album_resolution,
                apply=apply,
                reason="orphan album_asset rows with missing asset references",
            )
        )
        plans.append(
            self._plan_for_resolution(
                dsn=dsn,
                timeout=timeout,
                resolution=inspection.album_resolution,
                paired_resolution=inspection.asset_resolution,
                apply=apply,
                reason="orphan album_asset rows with missing album references",
            )
        )
        return plans

    def _plan_for_resolution(
        self,
        *,
        dsn: str,
        timeout: int,
        resolution,
        paired_resolution,
        apply: bool,
        reason: str,
    ) -> RepairPlanItem:
        if resolution.mapping is None:
            return RepairPlanItem(
                action="delete",
                target_table="public.album_asset",
                reason=(
                    "Repair skipped because FK metadata could not be resolved safely: "
                    f"{resolution.issue}"
                ),
                key_columns=(),
                row_count=0,
                dry_run=not apply,
                applied=False,
                status=RepairItemStatus.SKIPPED,
            )

        mapping = resolution.mapping
        sample_columns = self._sample_columns(mapping, paired_resolution.mapping)
        detected = self.postgres.find_missing_foreign_key_rows(
            dsn,
            timeout,
            link_schema=mapping.source_table.schema,
            link_table=mapping.source_table.name,
            reference_schema=mapping.target_table.schema,
            reference_table=mapping.target_table.name,
            link_column=mapping.source_column,
            reference_column=mapping.target_column,
            sample_columns=sample_columns,
            sample_limit=self.sample_limit,
        )
        count = int(detected["count"])
        backup_sql = self._backup_sql(mapping)
        if not apply:
            status = RepairItemStatus.PLANNED if count else RepairItemStatus.DETECTED
            return RepairPlanItem(
                action="delete",
                target_table=mapping.source_table.qualified_name,
                reason=reason,
                key_columns=sample_columns,
                row_count=count,
                sample_rows=list(detected["samples"]),
                dry_run=True,
                applied=False,
                status=status,
                backup_sql=backup_sql,
            )

        deleted = self.postgres.delete_missing_foreign_key_rows(
            dsn,
            timeout,
            link_schema=mapping.source_table.schema,
            link_table=mapping.source_table.name,
            reference_schema=mapping.target_table.schema,
            reference_table=mapping.target_table.name,
            link_column=mapping.source_column,
            reference_column=mapping.target_column,
            sample_columns=sample_columns,
            sample_limit=self.sample_limit,
        )
        deleted_count = int(deleted["count"])
        return RepairPlanItem(
            action="delete",
            target_table=mapping.source_table.qualified_name,
            reason=reason,
            key_columns=sample_columns,
            row_count=deleted_count,
            sample_rows=list(deleted["samples"]),
            dry_run=False,
            applied=deleted_count > 0,
            status=RepairItemStatus.REPAIRED if deleted_count > 0 else RepairItemStatus.DETECTED,
            backup_sql=backup_sql,
        )

    def _sample_columns(self, primary_mapping, secondary_mapping) -> tuple[str, ...]:
        columns = [primary_mapping.source_column]
        if secondary_mapping is not None and secondary_mapping.source_column not in columns:
            columns.append(secondary_mapping.source_column)
        return tuple(columns)

    def _backup_sql(self, mapping) -> str:
        return (
            f"CREATE TABLE {mapping.source_table.name}_{mapping.source_column}_orphan_backup AS "
            f"SELECT * FROM {mapping.source_table.qualified_name} AS link "
            f"WHERE NOT EXISTS (SELECT 1 FROM {mapping.target_table.qualified_name} AS ref "
            f"WHERE ref.{mapping.target_column} = link.{mapping.source_column});"
        )

    def _build_summary(self, plans: list[RepairPlanItem], *, apply: bool) -> str:
        total_rows = sum(
            plan.row_count for plan in plans if plan.status != RepairItemStatus.SKIPPED
        )
        if not apply:
            if total_rows == 0:
                return "Remote sync repair dry-run found no orphan album_asset rows to delete."
            return (
                f"Remote sync repair dry-run planned deletion of {total_rows} orphan "
                "album_asset rows."
            )
        repaired_rows = sum(plan.row_count for plan in plans if plan.applied)
        if repaired_rows == 0:
            return "Remote sync repair apply mode deleted no album_asset rows."
        return f"Remote sync repair deleted {repaired_rows} orphan album_asset rows."

    def _recommendations(self, *, apply: bool) -> list[str]:
        if not apply:
            return [
                "Review planned deletions and backup SQL before rerunning with --apply.",
            ]
        return [
            "Review the post-repair validation summary to confirm album_asset link integrity.",
        ]
