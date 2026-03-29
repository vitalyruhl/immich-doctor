from __future__ import annotations

import errno
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.consistency.missing_asset_models import (
    MissingAssetApplyResult,
    MissingAssetBlockingSeverity,
    MissingAssetOperationItem,
    MissingAssetOperationStatus,
    MissingAssetPreviewResult,
    MissingAssetReferenceFinding,
    MissingAssetReferenceScanResult,
    MissingAssetReferenceStatus,
    MissingAssetRepairBlocker,
    MissingAssetRepairBlockerType,
    MissingAssetRestorePoint,
    MissingAssetRestorePointDeleteResult,
    MissingAssetRestorePointsResult,
    MissingAssetRestorePointStatus,
    MissingAssetRestoreResult,
    RepairReadinessStatus,
)
from immich_doctor.consistency.missing_asset_restore_point_store import (
    MissingAssetRestorePointStore,
)
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.db.schema_detection import (
    AssetDependencyCoverageStatus,
    AssetDependencyState,
    DatabaseStateDetector,
    DetectedDatabaseState,
)
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

DEFAULT_BATCH_LIMIT = 100
REPAIRABLE_STATUSES = {MissingAssetReferenceStatus.MISSING_ON_DISK}
OPTIONAL_ASSET_COLUMNS = ("ownerId", "createdAt", "updatedAt")
SUPPORTED_RELATION_TABLES = {
    ("public", "asset_file"),
    ("public", "album_asset"),
    ("public", "asset_job_status"),
}
SUPPORTED_RELATION_TABLE_NAMES = tuple(
    sorted(f"{schema}.{table}" for schema, table in SUPPORTED_RELATION_TABLES)
)
IMMICH_LOGICAL_STORAGE_PREFIXES = (
    PurePosixPath("/usr/src/app/upload"),
    PurePosixPath("/usr/src/app/upload/"),
)


@dataclass(frozen=True, slots=True)
class AssetReferenceRelation:
    table_schema: str
    table_name: str
    column_name: str
    referenced_schema: str
    referenced_table: str
    referenced_column: str

    @property
    def qualified_name(self) -> str:
        return f"{self.table_schema}.{self.table_name}"


@dataclass(frozen=True, slots=True)
class MissingAssetProfile:
    asset_table_present: bool
    detected_asset_columns: tuple[str, ...]
    supported_optional_columns: tuple[str, ...]
    relations: tuple[AssetReferenceRelation, ...]
    asset_dependencies: tuple[AssetDependencyState, ...]
    blocking_issues: tuple[MissingAssetRepairBlocker, ...]
    database_state: DetectedDatabaseState

    @property
    def supported(self) -> bool:
        return self.asset_table_present and "originalPath" in self.detected_asset_columns


@dataclass(frozen=True, slots=True)
class PreparedMissingAssetScan:
    dsn: str
    timeout: int
    profile: MissingAssetProfile
    checks: tuple[CheckResult, ...]


@dataclass(slots=True)
class MissingAssetReferenceService:
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    repair_store: RepairJournalStore = field(default_factory=RepairJournalStore)
    restore_point_store: MissingAssetRestorePointStore = field(
        default_factory=MissingAssetRestorePointStore
    )
    batch_limit: int = DEFAULT_BATCH_LIMIT

    def scan(
        self,
        settings: AppSettings,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> MissingAssetReferenceScanResult:
        prepared = self._prepare_scan(settings, limit=limit, offset=offset)
        if isinstance(prepared, MissingAssetReferenceScanResult):
            return prepared

        batch_size = limit or self.batch_limit
        scan_timestamp = datetime.now(UTC).isoformat()
        asset_rows = self.postgres.list_assets_for_missing_references(
            prepared.dsn,
            prepared.timeout,
            limit=batch_size,
            offset=offset,
            optional_columns=prepared.profile.supported_optional_columns,
        )
        findings = self._inspect_asset_rows(
            asset_rows,
            settings=settings,
            scan_timestamp=scan_timestamp,
            blocking_issues=prepared.profile.blocking_issues,
        )

        return self._build_scan_result(
            settings,
            prepared=prepared,
            findings=findings,
            limit=batch_size,
            offset=offset,
            scanned_asset_count=len(asset_rows),
        )

    def scan_all(
        self,
        settings: AppSettings,
        *,
        batch_limit: int | None = None,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> MissingAssetReferenceScanResult:
        prepared = self._prepare_scan(settings, limit=batch_limit, offset=0)
        if isinstance(prepared, MissingAssetReferenceScanResult):
            return prepared

        effective_batch_limit = batch_limit or self.batch_limit
        scan_timestamp = datetime.now(UTC).isoformat()
        offset = 0
        scanned_asset_count = 0
        total_asset_count = self.postgres.count_assets(prepared.dsn, prepared.timeout)
        findings: list[MissingAssetReferenceFinding] = []

        if progress_callback is not None:
            progress_callback(
                {
                    "scanned_asset_count": 0,
                    "finding_count": 0,
                    "total_asset_count": total_asset_count,
                    "offset": 0,
                    "batch_size": 0,
                }
            )

        while True:
            asset_rows = self.postgres.list_assets_for_missing_references(
                prepared.dsn,
                prepared.timeout,
                limit=effective_batch_limit,
                offset=offset,
                optional_columns=prepared.profile.supported_optional_columns,
            )
            if not asset_rows:
                break

            findings.extend(
                self._inspect_asset_rows(
                    asset_rows,
                    settings=settings,
                    scan_timestamp=scan_timestamp,
                    blocking_issues=prepared.profile.blocking_issues,
                )
            )
            scanned_asset_count += len(asset_rows)

            if progress_callback is not None:
                progress_callback(
                    {
                        "scanned_asset_count": scanned_asset_count,
                        "finding_count": self._actual_finding_count(findings),
                        "total_asset_count": total_asset_count,
                        "offset": offset,
                        "batch_size": len(asset_rows),
                    }
                )

            if len(asset_rows) < effective_batch_limit:
                break
            offset += effective_batch_limit

        return self._build_scan_result(
            settings,
            prepared=prepared,
            findings=findings,
            limit=effective_batch_limit,
            offset=0,
            scanned_asset_count=scanned_asset_count,
            total_asset_count=total_asset_count,
        )

    def _prepare_scan(
        self,
        settings: AppSettings,
        *,
        limit: int | None,
        offset: int,
    ) -> PreparedMissingAssetScan | MissingAssetReferenceScanResult:
        dsn = settings.postgres_dsn_value()
        if not dsn:
            return MissingAssetReferenceScanResult(
                summary=(
                    "Missing asset reference scan failed because database access is not configured."
                ),
                checks=[
                    CheckResult(
                        name="postgres_connection",
                        status=CheckStatus.FAIL,
                        message="Database DSN is not configured.",
                    )
                ],
            )

        timeout = settings.postgres_connect_timeout_seconds
        connection_check = self.postgres.validate_connection(dsn, timeout)
        if connection_check.status == CheckStatus.FAIL:
            return MissingAssetReferenceScanResult(
                summary=(
                    "Missing asset reference scan failed because PostgreSQL could not be reached."
                ),
                checks=[connection_check],
            )

        database_state = DatabaseStateDetector(self.postgres).detect(dsn, timeout)
        profile = self._detect_profile(database_state)
        profile_check = self._profile_check(profile)
        checks = (connection_check, profile_check)
        if not profile.supported:
            return MissingAssetReferenceScanResult(
                summary=(
                    "Missing asset reference scan skipped because the current PostgreSQL schema "
                    "does not expose `public.asset.originalPath`."
                ),
                checks=checks,
                metadata={
                    "environment": settings.environment,
                    "limit": limit or self.batch_limit,
                    "offset": offset,
                    "scannedAssetCount": 0,
                    "database_state": profile.database_state.to_dict(),
                },
                recommendations=[
                    "This workflow currently supports only asset rows with a readable "
                    "`originalPath` column.",
                ],
            )
        return PreparedMissingAssetScan(
            dsn=dsn,
            timeout=timeout,
            profile=profile,
            checks=checks,
        )

    def _inspect_asset_rows(
        self,
        rows: list[dict[str, object]],
        *,
        settings: AppSettings,
        scan_timestamp: str,
        blocking_issues: tuple[MissingAssetRepairBlocker, ...],
    ) -> list[MissingAssetReferenceFinding]:
        return [
            self._inspect_asset_row(
                row,
                settings=settings,
                scan_timestamp=scan_timestamp,
                blocking_issues=blocking_issues,
            )
            for row in rows
        ]

    def _build_scan_result(
        self,
        settings: AppSettings,
        *,
        prepared: PreparedMissingAssetScan,
        findings: list[MissingAssetReferenceFinding],
        limit: int,
        offset: int,
        scanned_asset_count: int,
        total_asset_count: int | None = None,
    ) -> MissingAssetReferenceScanResult:
        actual_finding_count = self._actual_finding_count(findings)
        actionable_count = sum(
            1
            for finding in findings
            if finding.status in REPAIRABLE_STATUSES
            and finding.repair_readiness == RepairReadinessStatus.READY
        )
        summary = (
            f"Scanned {scanned_asset_count} asset rows. "
            f"{actionable_count} missing-on-disk references are ready for preview/apply."
        )
        recommendations = [
            (
                "Preview creates a repair run and plan token. Apply must reuse that repair run "
                "so live-state drift can be detected safely."
            )
        ]
        if prepared.profile.blocking_issues:
            recommendations.append(
                "Repair remains blocked until unsupported asset reference mappings are resolved."
            )

        return MissingAssetReferenceScanResult(
            summary=summary,
            checks=list(prepared.checks),
            findings=findings,
            metadata={
                "environment": settings.environment,
                "limit": limit,
                "offset": offset,
                "scannedAssetCount": scanned_asset_count,
                "totalAssetCount": total_asset_count
                if total_asset_count is not None
                else scanned_asset_count,
                "findingCount": actual_finding_count,
                "supportedScope": {
                    "scanTables": ["public.asset"],
                    "scanPathField": "public.asset.originalPath",
                    "repairRestoreTables": [
                        "public.asset",
                        *[relation.qualified_name for relation in prepared.profile.relations],
                    ],
                    "repairCoveredDependencyTables": list(SUPPORTED_RELATION_TABLE_NAMES),
                    "assetDependencies": [
                        dependency.to_dict() for dependency in prepared.profile.asset_dependencies
                    ],
                    "applyBlocked": bool(prepared.profile.blocking_issues),
                    "applyBlockers": [
                        blocker.to_dict() for blocker in prepared.profile.blocking_issues
                    ],
                    "scanBlockers": [
                        blocker.to_dict() for blocker in prepared.profile.blocking_issues
                    ],
                },
                "blockingIssues": [blocker.summary for blocker in prepared.profile.blocking_issues],
                "database_state": prepared.profile.database_state.to_dict(),
            },
            recommendations=recommendations,
        )

    def preview(
        self,
        settings: AppSettings,
        *,
        asset_ids: tuple[str, ...],
        select_all: bool,
        limit: int | None = None,
        offset: int = 0,
    ) -> MissingAssetPreviewResult:
        scan_result = self.scan(settings, limit=limit, offset=offset)
        actionable_findings = self._selected_findings(
            findings=scan_result.findings,
            asset_ids=asset_ids,
            select_all=select_all,
        )
        scope = {
            "domain": "consistency.missing_asset_references",
            "action": "preview_remove",
            "asset_ids": [finding.asset_id for finding in actionable_findings],
            "select_all": select_all,
            "limit": limit or self.batch_limit,
            "offset": offset,
        }
        db_fingerprint = self._db_fingerprint(actionable_findings)
        file_fingerprint = self._file_fingerprint(actionable_findings)
        plan_token = create_plan_token(
            scope=scope,
            db_fingerprint=db_fingerprint,
            file_fingerprint=file_fingerprint,
        )
        repair_run = RepairRun.new(
            repair_run_id=uuid4().hex,
            scope=scope,
            status=RepairRunStatus.PLANNED,
            live_state_fingerprint=build_live_state_fingerprint(
                db_fingerprint=db_fingerprint,
                file_fingerprint=file_fingerprint,
            ),
            plan_token_id=plan_token.token_id,
        )
        self.repair_store.create_run(settings, repair_run=repair_run, plan_token=plan_token)

        checks = list(scan_result.checks)
        checks.append(
            CheckResult(
                name="preview_selection",
                status=CheckStatus.PASS if actionable_findings else CheckStatus.WARN,
                message=(
                    f"Preview selected {len(actionable_findings)} repair-ready "
                    "missing asset references."
                    if actionable_findings
                    else "Preview selected no repair-ready missing asset references."
                ),
                details={
                    "requested_asset_ids": list(asset_ids),
                    "select_all": select_all,
                    "repair_run_id": repair_run.repair_run_id,
                },
            )
        )
        checks.append(
            CheckResult(
                name="repair_run_foundation",
                status=CheckStatus.PASS,
                message="Preview persisted a repair run and plan token for later apply.",
                details={
                    "repair_run_id": repair_run.repair_run_id,
                    "repair_run_path": str(
                        repair_run_directory(settings, repair_run.repair_run_id)
                    ),
                    "plan_token_id": plan_token.token_id,
                },
            )
        )

        return MissingAssetPreviewResult(
            summary=(
                f"Preview planned removal for {len(actionable_findings)} missing asset references."
            ),
            checks=checks,
            selected_findings=actionable_findings,
            repair_run_id=repair_run.repair_run_id,
            metadata={
                "environment": settings.environment,
                "dry_run": True,
                "selected_asset_ids": [finding.asset_id for finding in actionable_findings],
                "repair_run_id": repair_run.repair_run_id,
                "plan_token_id": plan_token.token_id,
            },
            recommendations=[
                "Review the exact selected assets before apply. Re-run preview if "
                "the runtime or DB state changes.",
            ],
        )

    def apply(
        self,
        settings: AppSettings,
        *,
        repair_run_id: str,
    ) -> MissingAssetApplyResult:
        run = self.repair_store.load_run(settings, repair_run_id)
        plan_token = self.repair_store.load_plan_token(settings, repair_run_id)
        selected_asset_ids = tuple(str(item) for item in run.scope.get("asset_ids", []))
        scan_result = self.scan(
            settings,
            limit=int(run.scope.get("limit", self.batch_limit)),
            offset=int(run.scope.get("offset", 0)),
        )
        selected_findings = [
            finding for finding in scan_result.findings if finding.asset_id in selected_asset_ids
        ]
        guard_result = validate_plan_token(
            plan_token,
            scope=dict(run.scope),
            db_fingerprint=self._db_fingerprint(selected_findings),
            file_fingerprint=self._file_fingerprint(selected_findings),
        )
        guard_check = CheckResult(
            name="repair_apply_guard",
            status=CheckStatus.PASS if guard_result.valid else CheckStatus.FAIL,
            message=guard_result.reason,
            details={
                "repair_run_id": repair_run_id,
                "token_id": guard_result.token_id,
                "expected_db_fingerprint": guard_result.expected_db_fingerprint,
                "expected_file_fingerprint": guard_result.expected_file_fingerprint,
                "actual_db_fingerprint": guard_result.actual_db_fingerprint,
                "actual_file_fingerprint": guard_result.actual_file_fingerprint,
            },
        )
        if not guard_result.valid:
            run.finish(RepairRunStatus.FAILED)
            self.repair_store.update_run(settings, run)
            return MissingAssetApplyResult(
                summary="Apply stopped because the preview scope drifted before mutation.",
                checks=[*scan_result.checks, guard_check],
                repair_run_id=repair_run_id,
                items=[],
                metadata={"environment": settings.environment, "dry_run": False},
                recommendations=[
                    "Re-run preview to bind a fresh plan token to the current live state.",
                ],
            )

        dsn = settings.postgres_dsn_value()
        if dsn is None:
            return MissingAssetApplyResult(
                summary="Apply failed because database access is not configured.",
                checks=[
                    CheckResult(
                        name="postgres_connection",
                        status=CheckStatus.FAIL,
                        message="Database DSN is not configured.",
                    )
                ],
                repair_run_id=repair_run_id,
                items=[],
            )

        timeout = settings.postgres_connect_timeout_seconds
        profile = self._detect_profile(DatabaseStateDetector(self.postgres).detect(dsn, timeout))
        run.status = RepairRunStatus.RUNNING
        self.repair_store.update_run(settings, run)

        items = [
            self._apply_single_asset(
                settings,
                dsn=dsn,
                timeout=timeout,
                asset_id=asset_id,
                finding=next(
                    (finding for finding in selected_findings if finding.asset_id == asset_id),
                    None,
                ),
                repair_run=run,
                relations=profile.relations,
            )
            for asset_id in selected_asset_ids
        ]
        run.finish(self._final_run_status(items))
        self.repair_store.update_run(settings, run)

        return MissingAssetApplyResult(
            summary=(f"Apply processed {len(items)} selected missing asset references."),
            checks=[*scan_result.checks, guard_check, self._journal_check(settings, run)],
            repair_run_id=repair_run_id,
            items=items,
            metadata={"environment": settings.environment, "dry_run": False},
            recommendations=[
                "Review created restore points before deleting them. Use restore "
                "points for reversal instead of ad-hoc reinserts.",
            ],
        )

    def list_restore_points(self, settings: AppSettings) -> MissingAssetRestorePointsResult:
        points = self.restore_point_store.list_points(settings)
        return MissingAssetRestorePointsResult(
            summary=f"Loaded {len(points)} missing-asset restore points.",
            checks=[
                CheckResult(
                    name="restore_points_store",
                    status=CheckStatus.PASS,
                    message="Missing asset restore point manifests were loaded.",
                )
            ],
            items=points,
            metadata={"environment": settings.environment},
        )

    def restore(
        self,
        settings: AppSettings,
        *,
        restore_point_ids: tuple[str, ...],
        restore_all: bool,
    ) -> MissingAssetRestoreResult:
        points = self.restore_point_store.list_points(settings)
        selected_points = (
            points
            if restore_all
            else [point for point in points if point.restore_point_id in set(restore_point_ids)]
        )
        repair_run_id = uuid4().hex
        scope = {
            "domain": "consistency.missing_asset_references",
            "action": "restore",
            "restore_point_ids": [point.restore_point_id for point in selected_points],
            "restore_all": restore_all,
        }
        plan_token = create_plan_token(
            scope=scope,
            db_fingerprint=fingerprint_payload(scope),
            file_fingerprint=fingerprint_payload(
                [
                    {
                        "restore_point_id": point.restore_point_id,
                        "status": point.status.value,
                    }
                    for point in selected_points
                ]
            ),
        )
        repair_run = RepairRun.new(
            repair_run_id=repair_run_id,
            scope=scope,
            status=RepairRunStatus.RUNNING,
            live_state_fingerprint=build_live_state_fingerprint(
                db_fingerprint=plan_token.db_fingerprint,
                file_fingerprint=plan_token.file_fingerprint,
            ),
            plan_token_id=plan_token.token_id,
        )
        self.repair_store.create_run(settings, repair_run=repair_run, plan_token=plan_token)

        dsn = settings.postgres_dsn_value()
        if dsn is None:
            repair_run.finish(RepairRunStatus.FAILED)
            self.repair_store.update_run(settings, repair_run)
            return MissingAssetRestoreResult(
                summary="Restore failed because database access is not configured.",
                checks=[
                    CheckResult(
                        name="postgres_connection",
                        status=CheckStatus.FAIL,
                        message="Database DSN is not configured.",
                    )
                ],
                repair_run_id=repair_run.repair_run_id,
                items=[],
            )

        timeout = settings.postgres_connect_timeout_seconds
        items = [
            self._restore_single_point(
                settings,
                dsn=dsn,
                timeout=timeout,
                point=point,
                repair_run=repair_run,
            )
            for point in selected_points
        ]
        repair_run.finish(self._final_restore_status(items))
        self.repair_store.update_run(settings, repair_run)

        return MissingAssetRestoreResult(
            summary=f"Restore processed {len(items)} missing-asset restore points.",
            checks=[self._journal_check(settings, repair_run)],
            repair_run_id=repair_run.repair_run_id,
            items=items,
            metadata={"environment": settings.environment},
        )

    def delete_restore_points(
        self,
        settings: AppSettings,
        *,
        restore_point_ids: tuple[str, ...],
        delete_all: bool,
    ) -> MissingAssetRestorePointDeleteResult:
        points = self.restore_point_store.list_points(settings)
        selected_ids = (
            tuple(point.restore_point_id for point in points) if delete_all else restore_point_ids
        )
        deleted = self.restore_point_store.delete(settings, selected_ids)
        return MissingAssetRestorePointDeleteResult(
            summary=f"Deleted {len(deleted)} missing-asset restore points.",
            checks=[
                CheckResult(
                    name="restore_points_delete",
                    status=CheckStatus.PASS,
                    message="Selected restore point manifests were deleted.",
                )
            ],
            items=[
                {"restore_point_id": restore_point_id, "status": "deleted"}
                for restore_point_id in deleted
            ],
            metadata={"environment": settings.environment, "delete_all": delete_all},
        )

    def _detect_profile(self, database_state: DetectedDatabaseState) -> MissingAssetProfile:
        asset_table = database_state.table("asset")
        asset_table_present = asset_table is not None
        detected_asset_columns = asset_table.column_names if asset_table is not None else ()
        optional_columns = tuple(
            column for column in OPTIONAL_ASSET_COLUMNS if column in detected_asset_columns
        )
        relations: list[AssetReferenceRelation] = []
        blockers: list[MissingAssetRepairBlocker] = []
        asset_dependencies = database_state.asset_dependencies
        unsupported_foreign_keys: list[dict[str, object]] = []
        for dependency in asset_dependencies:
            source_columns = tuple(dependency.source_columns)
            target_columns = tuple(dependency.target_columns)
            if (
                dependency.coverage_status
                == AssetDependencyCoverageStatus.COVERED_SAFE_FOR_ANALYSIS
                and len(source_columns) == 1
                and target_columns == ("id",)
            ):
                relations.append(
                    AssetReferenceRelation(
                        table_schema=dependency.source_schema,
                        table_name=dependency.source_table,
                        column_name=source_columns[0],
                        referenced_schema=dependency.target_schema,
                        referenced_table=dependency.target_table,
                        referenced_column=target_columns[0],
                    )
                )
                continue
            if len(source_columns) != 1 or target_columns != ("id",):
                unsupported_foreign_keys.append(
                    {
                        "constraint_name": dependency.constraint_name,
                        "table": dependency.qualified_name,
                        "column_names": list(source_columns),
                        "referenced_column_names": list(target_columns),
                        "delete_action": dependency.delete_action,
                        "risk_class": dependency.risk_class.value,
                        "coverage_status": dependency.coverage_status.value,
                    }
                )
            if not dependency.blocks_apply:
                continue
            blockers.append(
                MissingAssetRepairBlocker(
                    blocker_code=f"asset_dependency:{dependency.qualified_name}",
                    blocker_type=MissingAssetRepairBlockerType.SCHEMA,
                    summary=(
                        f"{dependency.qualified_name} blocks apply: {dependency.risk_class.value}"
                    ),
                    details={
                        "reason": dependency.reason,
                        "constraint_name": dependency.constraint_name,
                        "fk_column": source_columns[0] if len(source_columns) == 1 else None,
                        "column_names": list(source_columns),
                        "referenced_column_names": list(target_columns),
                        "delete_action": dependency.delete_action,
                        "risk_class": dependency.risk_class.value,
                        "coverage_status": dependency.coverage_status.value,
                        "blocks_apply": dependency.blocks_apply,
                        "notes": list(dependency.notes),
                    },
                    affected_tables=(dependency.qualified_name,),
                    repair_covered_tables=SUPPORTED_RELATION_TABLE_NAMES,
                    blocking_severity=MissingAssetBlockingSeverity.ERROR,
                    is_repairable=False,
                )
            )

        relations.sort(key=lambda item: item.qualified_name)
        if unsupported_foreign_keys:
            blockers.append(
                MissingAssetRepairBlocker(
                    blocker_code="unsupported_dependency_foreign_keys",
                    blocker_type=MissingAssetRepairBlockerType.SCHEMA,
                    summary="Unsupported asset foreign key definitions detected",
                    details={
                        "reason": (
                            "Repair only covers single-column foreign keys that point to "
                            "public.asset.id."
                        ),
                        "constraints": unsupported_foreign_keys,
                        "blocks_apply": True,
                    },
                    affected_tables=tuple(
                        sorted(
                            {
                                str(item["table"])
                                for item in unsupported_foreign_keys
                                if item.get("table")
                            }
                        )
                    ),
                    repair_covered_tables=SUPPORTED_RELATION_TABLE_NAMES,
                    blocking_severity=MissingAssetBlockingSeverity.ERROR,
                    is_repairable=False,
                )
            )
        return MissingAssetProfile(
            asset_table_present=asset_table_present,
            detected_asset_columns=detected_asset_columns,
            supported_optional_columns=optional_columns,
            relations=tuple(relations),
            asset_dependencies=asset_dependencies,
            blocking_issues=tuple(
                sorted(
                    blockers,
                    key=lambda item: (
                        item.affected_tables[0] if item.affected_tables else "",
                        item.blocker_code,
                    ),
                )
            ),
            database_state=database_state,
        )

    def _profile_check(self, profile: MissingAssetProfile) -> CheckResult:
        if profile.supported:
            return CheckResult(
                name="missing_asset_reference_profile",
                status=CheckStatus.PASS,
                message=(
                    "Schema-aware asset reference scan is supported for the current live "
                    "PostgreSQL shape."
                ),
                details={
                    "product_version_current": profile.database_state.product_version_current,
                    "product_version_confidence": (
                        profile.database_state.product_version_confidence.value
                    ),
                    "schema_generation_key": profile.database_state.schema_generation_key,
                    "schema_fingerprint": profile.database_state.schema_fingerprint,
                    "support_status": profile.database_state.support_status.value,
                    "optional_asset_columns": list(profile.supported_optional_columns),
                    "direct_asset_relations": [
                        relation.qualified_name for relation in profile.relations
                    ],
                    "asset_dependencies": [
                        dependency.to_dict() for dependency in profile.asset_dependencies
                    ],
                    "capabilities": {
                        key: value
                        for key, value in sorted(profile.database_state.capabilities.items())
                        if value
                    },
                    "risk_flags": list(profile.database_state.risk_flags),
                    "scan_blockers": [blocker.to_dict() for blocker in profile.blocking_issues],
                },
            )
        return CheckResult(
            name="missing_asset_reference_profile",
            status=CheckStatus.SKIP,
            message=(
                "Missing asset reference scan is unsupported because "
                "public.asset.originalPath is unavailable."
            ),
            details={
                "product_version_current": profile.database_state.product_version_current,
                "product_version_confidence": (
                    profile.database_state.product_version_confidence.value
                ),
                "schema_generation_key": profile.database_state.schema_generation_key,
                "schema_fingerprint": profile.database_state.schema_fingerprint,
                "support_status": profile.database_state.support_status.value,
                "risk_flags": list(profile.database_state.risk_flags),
            },
        )

    def _inspect_asset_row(
        self,
        row: dict[str, object],
        *,
        settings: AppSettings,
        scan_timestamp: str,
        blocking_issues: tuple[MissingAssetRepairBlocker, ...],
    ) -> MissingAssetReferenceFinding:
        asset_id = str(row["id"])
        logical_path = str(row.get("originalPath") or "")
        asset_path = Path(logical_path)
        resolved_asset_path = asset_path
        repair_readiness = RepairReadinessStatus.READY
        repair_blockers: list[str] = []
        repair_blocker_details: list[MissingAssetRepairBlocker] = []
        status = MissingAssetReferenceStatus.PRESENT
        message = "Original asset path exists in the current runtime filesystem."

        if not logical_path.strip():
            status = MissingAssetReferenceStatus.UNSUPPORTED
            repair_readiness = RepairReadinessStatus.BLOCKED
            repair_blocker_details.append(
                MissingAssetRepairBlocker(
                    blocker_code="empty_original_path",
                    blocker_type=MissingAssetRepairBlockerType.PATH,
                    summary="Original path is empty",
                    details={
                        "reason": "Asset originalPath is empty and cannot be resolved safely."
                    },
                    blocking_severity=MissingAssetBlockingSeverity.ERROR,
                    is_repairable=False,
                )
            )
            message = "Asset originalPath is empty."
        else:
            try:
                self._inspect_asset_path(asset_path)
            except FileNotFoundError:
                mapped_asset_path = self._map_asset_logical_path(
                    logical_path,
                    settings=settings,
                )
                if mapped_asset_path is not None and mapped_asset_path != asset_path:
                    resolved_asset_path = mapped_asset_path
                    try:
                        self._inspect_asset_path(resolved_asset_path)
                    except FileNotFoundError:
                        status = MissingAssetReferenceStatus.MISSING_ON_DISK
                        message = "Asset originalPath does not exist on disk."
                    except PermissionError:
                        status = MissingAssetReferenceStatus.PERMISSION_ERROR
                        repair_readiness = RepairReadinessStatus.BLOCKED
                        repair_blocker_details.append(
                            MissingAssetRepairBlocker(
                                blocker_code="asset_path_permission_error",
                                blocker_type=MissingAssetRepairBlockerType.FILESYSTEM,
                                summary="Asset path cannot be accessed",
                                details={
                                    "reason": ("The current process cannot access the asset path.")
                                },
                                blocking_severity=MissingAssetBlockingSeverity.ERROR,
                                is_repairable=False,
                            )
                        )
                        message = (
                            "Asset originalPath exists but is not accessible to the current "
                            "process."
                        )
                    except OSError as exc:
                        status = (
                            MissingAssetReferenceStatus.PERMISSION_ERROR
                            if exc.errno in {errno.EACCES, errno.EPERM}
                            else MissingAssetReferenceStatus.UNREADABLE_PATH
                        )
                        repair_readiness = RepairReadinessStatus.BLOCKED
                        repair_blocker_details.append(
                            MissingAssetRepairBlocker(
                                blocker_code="asset_path_unreadable",
                                blocker_type=MissingAssetRepairBlockerType.FILESYSTEM,
                                summary="Asset path could not be inspected",
                                details={"reason": exc.strerror or str(exc)},
                                blocking_severity=MissingAssetBlockingSeverity.ERROR,
                                is_repairable=False,
                            )
                        )
                        message = (
                            f"Asset originalPath could not be inspected: {exc.strerror or exc}."
                        )
                else:
                    status = MissingAssetReferenceStatus.MISSING_ON_DISK
                    message = "Asset originalPath does not exist on disk."
            except PermissionError:
                status = MissingAssetReferenceStatus.PERMISSION_ERROR
                repair_readiness = RepairReadinessStatus.BLOCKED
                repair_blocker_details.append(
                    MissingAssetRepairBlocker(
                        blocker_code="asset_path_permission_error",
                        blocker_type=MissingAssetRepairBlockerType.FILESYSTEM,
                        summary="Asset path cannot be accessed",
                        details={"reason": ("The current process cannot access the asset path.")},
                        blocking_severity=MissingAssetBlockingSeverity.ERROR,
                        is_repairable=False,
                    )
                )
                message = "Asset originalPath exists but is not accessible to the current process."
            except OSError as exc:
                status = (
                    MissingAssetReferenceStatus.PERMISSION_ERROR
                    if exc.errno in {errno.EACCES, errno.EPERM}
                    else MissingAssetReferenceStatus.UNREADABLE_PATH
                )
                repair_readiness = RepairReadinessStatus.BLOCKED
                repair_blocker_details.append(
                    MissingAssetRepairBlocker(
                        blocker_code="asset_path_unreadable",
                        blocker_type=MissingAssetRepairBlockerType.FILESYSTEM,
                        summary="Asset path could not be inspected",
                        details={"reason": exc.strerror or str(exc)},
                        blocking_severity=MissingAssetBlockingSeverity.ERROR,
                        is_repairable=False,
                    )
                )
                message = f"Asset originalPath could not be inspected: {exc.strerror or exc}."

        if status not in REPAIRABLE_STATUSES:
            repair_readiness = RepairReadinessStatus.BLOCKED
        if blocking_issues:
            repair_readiness = RepairReadinessStatus.BLOCKED
            repair_blocker_details.extend(blocking_issues)

        repair_blockers.extend(blocker.summary for blocker in repair_blocker_details)

        return MissingAssetReferenceFinding(
            finding_id=f"missing_asset_reference:{asset_id}",
            asset_id=asset_id,
            asset_type=str(row.get("type") or "unknown"),
            status=status,
            logical_path=logical_path,
            resolved_physical_path=str(resolved_asset_path),
            owner_id=str(row["ownerId"]) if row.get("ownerId") is not None else None,
            created_at=str(row["createdAt"]) if row.get("createdAt") is not None else None,
            updated_at=str(row["updatedAt"]) if row.get("updatedAt") is not None else None,
            scan_timestamp=scan_timestamp,
            repair_readiness=repair_readiness,
            repair_blockers=tuple(dict.fromkeys(repair_blockers)),
            repair_blocker_details=tuple(repair_blocker_details),
            message=message,
        )

    def _actual_finding_count(self, findings: list[MissingAssetReferenceFinding]) -> int:
        return sum(
            1 for finding in findings if finding.status != MissingAssetReferenceStatus.PRESENT
        )

    def _inspect_asset_path(self, path: Path) -> None:
        self.filesystem.stat_path(path)
        self.filesystem.read_probe(path)

    def _map_asset_logical_path(
        self,
        logical_path: str,
        *,
        settings: AppSettings,
    ) -> Path | None:
        library_root = settings.immich_library_root
        if library_root is None:
            return None

        normalized_path = logical_path.strip().replace("\\", "/")
        if not normalized_path:
            return None

        logical_posix_path = PurePosixPath(normalized_path)
        for prefix in IMMICH_LOGICAL_STORAGE_PREFIXES:
            try:
                relative_path = logical_posix_path.relative_to(prefix)
            except ValueError:
                continue
            return library_root.expanduser().joinpath(*relative_path.parts)

        return None

    def _selected_findings(
        self,
        *,
        findings: list[MissingAssetReferenceFinding],
        asset_ids: tuple[str, ...],
        select_all: bool,
    ) -> list[MissingAssetReferenceFinding]:
        selected_ids = set(asset_ids)
        selected: list[MissingAssetReferenceFinding] = []
        for finding in findings:
            if finding.repair_readiness != RepairReadinessStatus.READY:
                continue
            if finding.status not in REPAIRABLE_STATUSES:
                continue
            if select_all or finding.asset_id in selected_ids:
                selected.append(finding)
        return selected

    def _db_fingerprint(self, findings: list[MissingAssetReferenceFinding]) -> str:
        return fingerprint_payload(
            [
                {
                    "asset_id": finding.asset_id,
                    "status": finding.status.value,
                    "logical_path": finding.logical_path,
                    "repair_readiness": finding.repair_readiness.value,
                }
                for finding in findings
            ]
        )

    def _file_fingerprint(self, findings: list[MissingAssetReferenceFinding]) -> str:
        return fingerprint_payload(
            [
                {
                    "asset_id": finding.asset_id,
                    "resolved_physical_path": finding.resolved_physical_path,
                    "repair_blockers": [
                        blocker.to_dict() for blocker in finding.repair_blocker_details
                    ],
                }
                for finding in findings
            ]
        )

    def _apply_single_asset(
        self,
        settings: AppSettings,
        *,
        dsn: str,
        timeout: int,
        asset_id: str,
        finding: MissingAssetReferenceFinding | None,
        repair_run: RepairRun,
        relations: tuple[AssetReferenceRelation, ...],
    ) -> MissingAssetOperationItem:
        if finding is None:
            self._record_journal(
                settings,
                repair_run=repair_run,
                asset_id=asset_id,
                status=RepairJournalEntryStatus.SKIPPED,
                operation_type="remove_missing_asset_reference",
                old_db_values=None,
                new_db_values=None,
                original_path=None,
                error_details={"reason": "Asset is already absent from the current scan scope."},
            )
            return MissingAssetOperationItem(
                asset_id=asset_id,
                status=MissingAssetOperationStatus.ALREADY_REMOVED,
                restore_point_id=None,
                message="Selected asset is no longer present in the current scan scope.",
            )

        if finding.repair_readiness != RepairReadinessStatus.READY:
            self._record_journal(
                settings,
                repair_run=repair_run,
                asset_id=asset_id,
                status=RepairJournalEntryStatus.SKIPPED,
                operation_type="remove_missing_asset_reference",
                old_db_values=None,
                new_db_values=None,
                original_path=finding.logical_path,
                error_details={
                    "reason": "Finding is not repair-ready.",
                    "blockers": list(finding.repair_blockers),
                    "blocker_details": [
                        blocker.to_dict() for blocker in finding.repair_blocker_details
                    ],
                },
            )
            return MissingAssetOperationItem(
                asset_id=asset_id,
                status=MissingAssetOperationStatus.SKIPPED,
                restore_point_id=None,
                message="Finding is not repair-ready.",
                details={
                    "blockers": list(finding.repair_blockers),
                    "blocker_details": [
                        blocker.to_dict() for blocker in finding.repair_blocker_details
                    ],
                },
            )

        captured_records = self._capture_records(
            dsn,
            timeout,
            asset_id=asset_id,
            relations=relations,
        )
        if not captured_records:
            self._record_journal(
                settings,
                repair_run=repair_run,
                asset_id=asset_id,
                status=RepairJournalEntryStatus.SKIPPED,
                operation_type="remove_missing_asset_reference",
                old_db_values=None,
                new_db_values=None,
                original_path=finding.logical_path,
                error_details={"reason": "No asset rows remained to capture before deletion."},
            )
            return MissingAssetOperationItem(
                asset_id=asset_id,
                status=MissingAssetOperationStatus.ALREADY_REMOVED,
                restore_point_id=None,
                message="Asset row was already removed before apply.",
            )

        restore_point = MissingAssetRestorePoint(
            restore_point_id=uuid4().hex,
            repair_run_id=repair_run.repair_run_id,
            asset_id=asset_id,
            created_at=datetime.now(UTC).isoformat(),
            status=MissingAssetRestorePointStatus.AVAILABLE,
            record_count=sum(len(record["rows"]) for record in captured_records),
            logical_path=finding.logical_path,
            records=captured_records,
        )
        self.restore_point_store.create(settings, restore_point)
        try:
            deleted_records = self.postgres.delete_asset_reference_records(
                dsn,
                timeout,
                asset_id=asset_id,
                relations=tuple(
                    {
                        "table_schema": relation.table_schema,
                        "table_name": relation.table_name,
                        "column_name": relation.column_name,
                    }
                    for relation in relations
                ),
            )
        except Exception as exc:
            self.restore_point_store.delete(settings, (restore_point.restore_point_id,))
            self._record_journal(
                settings,
                repair_run=repair_run,
                asset_id=asset_id,
                status=RepairJournalEntryStatus.FAILED,
                operation_type="remove_missing_asset_reference",
                old_db_values={"restore_point_id": restore_point.restore_point_id},
                new_db_values=None,
                original_path=finding.logical_path,
                error_details={"reason": str(exc)},
            )
            return MissingAssetOperationItem(
                asset_id=asset_id,
                status=MissingAssetOperationStatus.FAILED,
                restore_point_id=None,
                message=f"Deletion failed: {exc}",
            )

        self._record_journal(
            settings,
            repair_run=repair_run,
            asset_id=asset_id,
            status=RepairJournalEntryStatus.APPLIED,
            operation_type="remove_missing_asset_reference",
            old_db_values={
                "restore_point_id": restore_point.restore_point_id,
                "records": captured_records,
            },
            new_db_values={"deleted_tables": [item["table"] for item in deleted_records]},
            original_path=finding.logical_path,
            error_details=None,
        )
        return MissingAssetOperationItem(
            asset_id=asset_id,
            status=MissingAssetOperationStatus.APPLIED,
            restore_point_id=restore_point.restore_point_id,
            message=(
                "Asset row and supported direct references were removed after "
                "restore point capture."
            ),
            record_count=restore_point.record_count,
            details={"deleted_tables": [item["table"] for item in deleted_records]},
        )

    def _capture_records(
        self,
        dsn: str,
        timeout: int,
        *,
        asset_id: str,
        relations: tuple[AssetReferenceRelation, ...],
    ) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        asset_rows = self.postgres.list_rows_by_column_values(
            dsn,
            timeout,
            table_schema="public",
            table_name="asset",
            column_name="id",
            values=(asset_id,),
            order_columns=("id",),
        )
        if asset_rows:
            records.append({"table": "public.asset", "rows": asset_rows})
        for relation in relations:
            rows = self.postgres.list_rows_by_column_values(
                dsn,
                timeout,
                table_schema=relation.table_schema,
                table_name=relation.table_name,
                column_name=relation.column_name,
                values=(asset_id,),
            )
            if rows:
                records.append({"table": relation.qualified_name, "rows": rows})
        return records

    def _restore_single_point(
        self,
        settings: AppSettings,
        *,
        dsn: str,
        timeout: int,
        point: MissingAssetRestorePoint,
        repair_run: RepairRun,
    ) -> MissingAssetOperationItem:
        if point.status == MissingAssetRestorePointStatus.RESTORED:
            self._record_journal(
                settings,
                repair_run=repair_run,
                asset_id=point.asset_id,
                status=RepairJournalEntryStatus.SKIPPED,
                operation_type="restore_missing_asset_reference",
                old_db_values={"restore_point_id": point.restore_point_id},
                new_db_values=None,
                original_path=point.logical_path,
                error_details={"reason": "Restore point was already restored."},
            )
            return MissingAssetOperationItem(
                asset_id=point.asset_id,
                status=MissingAssetOperationStatus.SKIPPED,
                restore_point_id=point.restore_point_id,
                message="Restore point was already restored.",
            )

        try:
            inserted_count = self.postgres.restore_asset_reference_records(
                dsn,
                timeout,
                records=point.records,
            )
        except Exception as exc:
            self._record_journal(
                settings,
                repair_run=repair_run,
                asset_id=point.asset_id,
                status=RepairJournalEntryStatus.FAILED,
                operation_type="restore_missing_asset_reference",
                old_db_values={"restore_point_id": point.restore_point_id},
                new_db_values=None,
                original_path=point.logical_path,
                error_details={"reason": str(exc)},
            )
            return MissingAssetOperationItem(
                asset_id=point.asset_id,
                status=MissingAssetOperationStatus.FAILED,
                restore_point_id=point.restore_point_id,
                message=f"Restore failed: {exc}",
            )

        point.status = MissingAssetRestorePointStatus.RESTORED
        self.restore_point_store.update(settings, point)
        self._record_journal(
            settings,
            repair_run=repair_run,
            asset_id=point.asset_id,
            status=RepairJournalEntryStatus.APPLIED,
            operation_type="restore_missing_asset_reference",
            old_db_values={"restore_point_id": point.restore_point_id},
            new_db_values={"restored_record_count": inserted_count},
            original_path=point.logical_path,
            error_details=None,
        )
        return MissingAssetOperationItem(
            asset_id=point.asset_id,
            status=MissingAssetOperationStatus.RESTORED,
            restore_point_id=point.restore_point_id,
            message="Restore point rows were reinserted into PostgreSQL.",
            record_count=inserted_count,
        )

    def _record_journal(
        self,
        settings: AppSettings,
        *,
        repair_run: RepairRun,
        asset_id: str,
        status: RepairJournalEntryStatus,
        operation_type: str,
        old_db_values: dict[str, object] | None,
        new_db_values: dict[str, object] | None,
        original_path: str | None,
        error_details: dict[str, object] | None,
    ) -> None:
        entry = RepairJournalEntry(
            entry_id=uuid4().hex,
            repair_run_id=repair_run.repair_run_id,
            operation_type=operation_type,
            status=status,
            asset_id=asset_id,
            table="public.asset",
            old_db_values=old_db_values,
            new_db_values=new_db_values,
            original_path=original_path,
            quarantine_path=None,
            undo_type=UndoType.NONE,
            undo_payload={},
            error_details=error_details,
        )
        self.repair_store.append_journal_entry(settings, entry)

    def _final_run_status(self, items: list[MissingAssetOperationItem]) -> RepairRunStatus:
        if any(item.status == MissingAssetOperationStatus.FAILED for item in items):
            if any(item.status == MissingAssetOperationStatus.APPLIED for item in items):
                return RepairRunStatus.PARTIAL
            return RepairRunStatus.FAILED
        return RepairRunStatus.COMPLETED

    def _final_restore_status(self, items: list[MissingAssetOperationItem]) -> RepairRunStatus:
        if any(item.status == MissingAssetOperationStatus.FAILED for item in items):
            if any(item.status == MissingAssetOperationStatus.RESTORED for item in items):
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
