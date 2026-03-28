from __future__ import annotations

import errno
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.consistency.missing_asset_models import (
    MissingAssetApplyResult,
    MissingAssetOperationItem,
    MissingAssetOperationStatus,
    MissingAssetPreviewResult,
    MissingAssetReferenceFinding,
    MissingAssetReferenceScanResult,
    MissingAssetReferenceStatus,
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
    blocking_issues: tuple[str, ...]

    @property
    def supported(self) -> bool:
        return self.asset_table_present and "originalPath" in self.detected_asset_columns


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

        profile = self._detect_profile(dsn, timeout)
        profile_check = self._profile_check(profile)
        checks = [connection_check, profile_check]
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
                },
                recommendations=[
                    "This workflow currently supports only asset rows with a readable "
                    "`originalPath` column.",
                ],
            )

        batch_size = limit or self.batch_limit
        asset_rows = self.postgres.list_assets_for_missing_references(
            dsn,
            timeout,
            limit=batch_size,
            offset=offset,
            optional_columns=profile.supported_optional_columns,
        )
        scan_timestamp = datetime.now(UTC).isoformat()
        findings = [
            self._inspect_asset_row(
                row,
                scan_timestamp=scan_timestamp,
                blocking_issues=profile.blocking_issues,
            )
            for row in asset_rows
        ]

        actionable_count = sum(
            1
            for finding in findings
            if finding.status in REPAIRABLE_STATUSES
            and finding.repair_readiness == RepairReadinessStatus.READY
        )
        summary = (
            f"Scanned {len(findings)} asset rows. "
            f"{actionable_count} missing-on-disk references are ready for preview/apply."
        )
        recommendations = [
            (
                "Preview creates a repair run and plan token. Apply must reuse that repair run "
                "so live-state drift can be detected safely."
            )
        ]
        if profile.blocking_issues:
            recommendations.append(
                "Repair remains blocked until unsupported asset reference mappings are resolved."
            )

        return MissingAssetReferenceScanResult(
            summary=summary,
            checks=checks,
            findings=findings,
            metadata={
                "environment": settings.environment,
                "limit": batch_size,
                "offset": offset,
                "supportedScope": {
                    "scanTables": ["public.asset"],
                    "scanPathField": "public.asset.originalPath",
                    "repairRestoreTables": [
                        "public.asset",
                        *[relation.qualified_name for relation in profile.relations],
                    ],
                },
                "blockingIssues": list(profile.blocking_issues),
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
        profile = self._detect_profile(dsn, timeout)
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

    def _detect_profile(self, dsn: str, timeout: int) -> MissingAssetProfile:
        tables = self.postgres.list_tables(dsn, timeout)
        table_lookup = {
            (str(table["table_schema"]), str(table["table_name"])): True for table in tables
        }
        asset_table_present = ("public", "asset") in table_lookup
        detected_asset_columns: tuple[str, ...] = ()
        optional_columns: tuple[str, ...] = ()
        if asset_table_present:
            columns = self.postgres.list_columns(
                dsn,
                timeout,
                table_schema="public",
                table_name="asset",
            )
            detected_asset_columns = tuple(str(column["column_name"]) for column in columns)
            optional_columns = tuple(
                column for column in OPTIONAL_ASSET_COLUMNS if column in detected_asset_columns
            )

        relations: list[AssetReferenceRelation] = []
        blockers: list[str] = []
        for table in tables:
            schema = str(table["table_schema"])
            name = str(table["table_name"])
            foreign_keys = self.postgres.list_foreign_keys(
                dsn,
                timeout,
                table_schema=schema,
                table_name=name,
            )
            for foreign_key in foreign_keys:
                if (
                    foreign_key["referenced_table_schema"] != "public"
                    or foreign_key["referenced_table_name"] != "asset"
                ):
                    continue
                source_columns = tuple(str(item) for item in foreign_key["column_names"])
                target_columns = tuple(str(item) for item in foreign_key["referenced_column_names"])
                if (schema, name) not in SUPPORTED_RELATION_TABLES:
                    blockers.append(
                        f"Unsupported asset dependency table {schema}.{name}: "
                        "only album_asset, asset_file, and asset_job_status are "
                        "repair-covered."
                    )
                    continue
                if len(source_columns) != 1 or target_columns != ("id",):
                    blockers.append(
                        f"Unsupported FK `{foreign_key['constraint_name']}` on "
                        f"{schema}.{name}: only single-column references to "
                        "public.asset.id are supported."
                    )
                    continue
                relations.append(
                    AssetReferenceRelation(
                        table_schema=schema,
                        table_name=name,
                        column_name=source_columns[0],
                        referenced_schema="public",
                        referenced_table="asset",
                        referenced_column="id",
                    )
                )

        relations.sort(key=lambda item: item.qualified_name)
        blockers = list(dict.fromkeys(blockers))
        return MissingAssetProfile(
            asset_table_present=asset_table_present,
            detected_asset_columns=detected_asset_columns,
            supported_optional_columns=optional_columns,
            relations=tuple(relations),
            blocking_issues=tuple(blockers),
        )

    def _profile_check(self, profile: MissingAssetProfile) -> CheckResult:
        if profile.supported:
            return CheckResult(
                name="missing_asset_reference_profile",
                status=CheckStatus.PASS,
                message="Supported asset path profile detected for missing asset reference scan.",
                details={
                    "optional_asset_columns": list(profile.supported_optional_columns),
                    "direct_asset_relations": [
                        relation.qualified_name for relation in profile.relations
                    ],
                },
            )
        return CheckResult(
            name="missing_asset_reference_profile",
            status=CheckStatus.SKIP,
            message=(
                "Missing asset reference scan is unsupported because "
                "public.asset.originalPath is unavailable."
            ),
        )

    def _inspect_asset_row(
        self,
        row: dict[str, object],
        *,
        scan_timestamp: str,
        blocking_issues: tuple[str, ...],
    ) -> MissingAssetReferenceFinding:
        asset_id = str(row["id"])
        logical_path = str(row.get("originalPath") or "")
        asset_path = Path(logical_path)
        repair_readiness = RepairReadinessStatus.READY
        repair_blockers: list[str] = []
        status = MissingAssetReferenceStatus.PRESENT
        message = "Original asset path exists in the current runtime filesystem."

        if not logical_path.strip():
            status = MissingAssetReferenceStatus.UNSUPPORTED
            repair_readiness = RepairReadinessStatus.BLOCKED
            repair_blockers.append("Asset originalPath is empty and cannot be resolved safely.")
            message = "Asset originalPath is empty."
        else:
            try:
                self.filesystem.stat_path(asset_path)
                self.filesystem.read_probe(asset_path)
            except FileNotFoundError:
                status = MissingAssetReferenceStatus.MISSING_ON_DISK
                message = "Asset originalPath does not exist on disk."
            except PermissionError:
                status = MissingAssetReferenceStatus.PERMISSION_ERROR
                repair_readiness = RepairReadinessStatus.BLOCKED
                repair_blockers.append("The current process cannot access the asset path.")
                message = "Asset originalPath exists but is not accessible to the current process."
            except OSError as exc:
                status = (
                    MissingAssetReferenceStatus.PERMISSION_ERROR
                    if exc.errno in {errno.EACCES, errno.EPERM}
                    else MissingAssetReferenceStatus.UNREADABLE_PATH
                )
                repair_readiness = RepairReadinessStatus.BLOCKED
                repair_blockers.append(exc.strerror or str(exc))
                message = f"Asset originalPath could not be inspected: {exc.strerror or exc}."

        if status not in REPAIRABLE_STATUSES:
            repair_readiness = RepairReadinessStatus.BLOCKED
        if blocking_issues:
            repair_readiness = RepairReadinessStatus.BLOCKED
            repair_blockers.extend(blocking_issues)

        return MissingAssetReferenceFinding(
            finding_id=f"missing_asset_reference:{asset_id}",
            asset_id=asset_id,
            asset_type=str(row.get("type") or "unknown"),
            status=status,
            logical_path=logical_path,
            resolved_physical_path=str(asset_path),
            owner_id=str(row["ownerId"]) if row.get("ownerId") is not None else None,
            created_at=str(row["createdAt"]) if row.get("createdAt") is not None else None,
            updated_at=str(row["updatedAt"]) if row.get("updatedAt") is not None else None,
            scan_timestamp=scan_timestamp,
            repair_readiness=repair_readiness,
            repair_blockers=tuple(dict.fromkeys(repair_blockers)),
            message=message,
        )

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
                    "repair_blockers": list(finding.repair_blockers),
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
                },
            )
            return MissingAssetOperationItem(
                asset_id=asset_id,
                status=MissingAssetOperationStatus.SKIPPED,
                restore_point_id=None,
                message="Finding is not repair-ready.",
                details={"blockers": list(finding.repair_blockers)},
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
