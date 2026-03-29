from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.consistency.models import (
    ConsistencyCategory,
    ConsistencyFinding,
    ConsistencyRepairMode,
    ConsistencySeverity,
    ConsistencySummary,
    ConsistencyValidationReport,
)
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.db.schema_detection import (
    DatabaseSchemaSupportStatus,
    DatabaseStateDetector,
    DetectedDatabaseState,
)

MISSING_ASSET_CATEGORY = "db.orphan.album_asset.missing_asset"
MISSING_ALBUM_CATEGORY = "db.orphan.album_asset.missing_album"
MISSING_PREVIEW_PATH_CATEGORY = "db.asset_file.path_missing.preview"
MISSING_THUMBNAIL_PATH_CATEGORY = "db.asset_file.path_missing.thumbnail"

SAFE_DELETE_CATEGORIES = (MISSING_ASSET_CATEGORY, MISSING_ALBUM_CATEGORY)
INSPECT_ONLY_CATEGORIES = (MISSING_PREVIEW_PATH_CATEGORY, MISSING_THUMBNAIL_PATH_CATEGORY)
ALL_CATEGORIES = SAFE_DELETE_CATEGORIES + INSPECT_ONLY_CATEGORIES
DEFAULT_SAMPLE_LIMIT = 3
CONSISTENCY_SCHEMA_DETECTOR_NAME = "immich_db_schema_detection_v1"


@dataclass(frozen=True, slots=True)
class CategorySpec:
    name: str
    severity: ConsistencySeverity
    repair_mode: ConsistencyRepairMode
    safe_for_all_safe: bool
    description: str


CATEGORY_SPECS = {
    MISSING_ASSET_CATEGORY: CategorySpec(
        name=MISSING_ASSET_CATEGORY,
        severity=ConsistencySeverity.FAIL,
        repair_mode=ConsistencyRepairMode.SAFE_DELETE,
        safe_for_all_safe=True,
        description="Orphan album_asset rows whose assetId references no asset row.",
    ),
    MISSING_ALBUM_CATEGORY: CategorySpec(
        name=MISSING_ALBUM_CATEGORY,
        severity=ConsistencySeverity.FAIL,
        repair_mode=ConsistencyRepairMode.SAFE_DELETE,
        safe_for_all_safe=True,
        description="Orphan album_asset rows whose albumId references no album row.",
    ),
    MISSING_PREVIEW_PATH_CATEGORY: CategorySpec(
        name=MISSING_PREVIEW_PATH_CATEGORY,
        severity=ConsistencySeverity.WARN,
        repair_mode=ConsistencyRepairMode.INSPECT_ONLY,
        safe_for_all_safe=False,
        description="asset_file preview paths missing in the current container filesystem.",
    ),
    MISSING_THUMBNAIL_PATH_CATEGORY: CategorySpec(
        name=MISSING_THUMBNAIL_PATH_CATEGORY,
        severity=ConsistencySeverity.WARN,
        repair_mode=ConsistencyRepairMode.INSPECT_ONLY,
        safe_for_all_safe=False,
        description="asset_file thumbnail paths missing in the current container filesystem.",
    ),
}


@dataclass(slots=True)
class CollectedConsistencyState:
    checks: list[CheckResult]
    categories: list[ConsistencyCategory]
    findings: list[ConsistencyFinding]
    summary: ConsistencySummary
    profile_supported: bool
    asset_reference_column: str | None = None


@dataclass(slots=True)
class ConsistencyCollector:
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    sample_limit: int = DEFAULT_SAMPLE_LIMIT

    def collect(self, dsn: str, timeout: int) -> CollectedConsistencyState:
        database_state = DatabaseStateDetector(self.postgres).detect(dsn, timeout)
        asset_reference_column = database_state.album_asset_asset_reference_column()
        validator_supported = (
            database_state.has_capability("can_validate_album_asset_missing_asset")
            and asset_reference_column is not None
            and database_state.support_status
            not in {
                DatabaseSchemaSupportStatus.PARTIAL_MIGRATION,
                DatabaseSchemaSupportStatus.UNSUPPORTED,
            }
        )
        checks = [
            self._scope_boundary_check(),
            self._profile_check(database_state),
        ]

        if not validator_supported:
            categories = [
                ConsistencyCategory(
                    name=spec.name,
                    severity=spec.severity,
                    repair_mode=spec.repair_mode,
                    status=CheckStatus.SKIP,
                    count=0,
                    repairable=spec.repair_mode == ConsistencyRepairMode.SAFE_DELETE,
                    message=(
                        "Skipped because the live PostgreSQL schema does not expose the "
                        "capabilities required for this validator."
                    ),
                    sample_findings=(),
                )
                for spec in CATEGORY_SPECS.values()
            ]
            summary = self._build_summary_model(
                database_state,
                profile_supported=False,
                executed_categories=(),
                skipped_categories=tuple(category.name for category in categories),
            )
            return CollectedConsistencyState(
                checks=checks,
                categories=categories,
                findings=[],
                summary=summary,
                profile_supported=False,
                asset_reference_column=asset_reference_column,
            )

        findings: list[ConsistencyFinding] = []
        findings.extend(
            self._collect_album_asset_missing_asset_findings(
                dsn,
                timeout,
                asset_reference_column=asset_reference_column,
            )
        )
        findings.extend(
            self._collect_album_asset_missing_album_findings(
                dsn,
                timeout,
                asset_reference_column=asset_reference_column,
            )
        )
        findings.extend(self._collect_asset_file_path_findings(dsn, timeout, file_type="preview"))
        findings.extend(self._collect_asset_file_path_findings(dsn, timeout, file_type="thumbnail"))

        grouped = {category: [] for category in ALL_CATEGORIES}
        for finding in findings:
            grouped[finding.category].append(finding)

        categories = [
            self._build_category(spec=CATEGORY_SPECS[name], findings=grouped[name])
            for name in ALL_CATEGORIES
        ]
        summary = self._build_summary_model(
            database_state,
            profile_supported=True,
            executed_categories=tuple(category.name for category in categories),
            skipped_categories=(),
        )
        return CollectedConsistencyState(
            checks=checks,
            categories=categories,
            findings=findings,
            summary=summary,
            profile_supported=True,
            asset_reference_column=asset_reference_column,
        )

    def _build_summary_model(
        self,
        database_state: DetectedDatabaseState,
        *,
        profile_supported: bool,
        executed_categories: tuple[str, ...],
        skipped_categories: tuple[str, ...],
    ) -> ConsistencySummary:
        return ConsistencySummary(
            profile_name=CONSISTENCY_SCHEMA_DETECTOR_NAME,
            profile_supported=profile_supported,
            support_status=database_state.support_status.value,
            product_version_current=database_state.product_version_current,
            product_version_confidence=database_state.product_version_confidence.value,
            schema_generation_key=database_state.schema_generation_key,
            schema_fingerprint=database_state.schema_fingerprint,
            asset_reference_column=database_state.album_asset_asset_reference_column(),
            capability_snapshot=dict(database_state.capabilities),
            risk_flags=database_state.risk_flags,
            executed_categories=executed_categories,
            skipped_categories=skipped_categories,
            scope_boundaries=(
                "Server PostgreSQL and container filesystem only. "
                "Client-side mobile SQLite is out of scope.",
            ),
        )

    def _scope_boundary_check(self) -> CheckResult:
        return CheckResult(
            name="consistency_scope_boundary",
            status=CheckStatus.PASS,
            message=(
                "Consistency checks validate server-side PostgreSQL rows and direct container "
                "filesystem paths only. Client-side mobile SQLite state is not inspected."
            ),
            details={"severity": "info"},
        )

    def _profile_check(self, database_state: DetectedDatabaseState) -> CheckResult:
        supported = database_state.has_capability("can_validate_album_asset_missing_asset") and (
            database_state.support_status
            not in {
                DatabaseSchemaSupportStatus.PARTIAL_MIGRATION,
                DatabaseSchemaSupportStatus.UNSUPPORTED,
            }
        )
        details = {
            "severity": "info",
            "product_version_current": database_state.product_version_current,
            "product_version_confidence": database_state.product_version_confidence.value,
            "schema_generation_key": database_state.schema_generation_key,
            "schema_fingerprint": database_state.schema_fingerprint,
            "asset_reference_column": database_state.album_asset_asset_reference_column(),
            "support_status": database_state.support_status.value,
            "risk_flags": list(database_state.risk_flags),
            "capabilities": {
                key: value for key, value in sorted(database_state.capabilities.items()) if value
            },
        }
        if supported:
            return CheckResult(
                name="schema_profile",
                status=(
                    CheckStatus.PASS
                    if database_state.support_status == DatabaseSchemaSupportStatus.SUPPORTED
                    else CheckStatus.WARN
                ),
                message=(
                    "Schema-aware validation is supported for the current live PostgreSQL shape."
                ),
                details=details,
            )
        return CheckResult(
            name="schema_profile",
            status=CheckStatus.SKIP,
            message=(
                "Schema-aware validation is blocked because the live PostgreSQL shape "
                "does not expose the required capabilities."
            ),
            details=details,
        )

    def _collect_album_asset_missing_asset_findings(
        self,
        dsn: str,
        timeout: int,
        *,
        asset_reference_column: str,
    ) -> list[ConsistencyFinding]:
        rows = self.postgres.list_grouped_album_asset_orphans(
            dsn,
            timeout,
            missing_target_table="asset",
            asset_reference_column=asset_reference_column,
        )
        return [
            ConsistencyFinding(
                category=MISSING_ASSET_CATEGORY,
                finding_id=f"album_asset:missing_asset:{row['albumId']}:{row['assetId']}",
                severity=ConsistencySeverity.FAIL,
                repair_mode=ConsistencyRepairMode.SAFE_DELETE,
                affected_tables=("public.album_asset", "public.asset"),
                key_fields={
                    "albumId": str(row["albumId"]),
                    "assetId": str(row["assetId"]),
                },
                message="album_asset references a missing asset row.",
                sample_metadata={
                    "albumId": row["albumId"],
                    "assetId": row["assetId"],
                    "assetReferenceColumn": asset_reference_column,
                },
                row_count=int(row["row_count"]),
            )
            for row in rows
        ]

    def _collect_album_asset_missing_album_findings(
        self,
        dsn: str,
        timeout: int,
        *,
        asset_reference_column: str,
    ) -> list[ConsistencyFinding]:
        rows = self.postgres.list_grouped_album_asset_orphans(
            dsn,
            timeout,
            missing_target_table="album",
            asset_reference_column=asset_reference_column,
        )
        return [
            ConsistencyFinding(
                category=MISSING_ALBUM_CATEGORY,
                finding_id=f"album_asset:missing_album:{row['albumId']}:{row['assetId']}",
                severity=ConsistencySeverity.FAIL,
                repair_mode=ConsistencyRepairMode.SAFE_DELETE,
                affected_tables=("public.album_asset", "public.album"),
                key_fields={
                    "albumId": str(row["albumId"]),
                    "assetId": str(row["assetId"]),
                },
                message="album_asset references a missing album row.",
                sample_metadata={
                    "albumId": row["albumId"],
                    "assetId": row["assetId"],
                    "assetReferenceColumn": asset_reference_column,
                },
                row_count=int(row["row_count"]),
            )
            for row in rows
        ]

    def _collect_asset_file_path_findings(
        self,
        dsn: str,
        timeout: int,
        *,
        file_type: str,
    ) -> list[ConsistencyFinding]:
        rows = self.postgres.list_asset_files_by_type(dsn, timeout, file_type=file_type)
        category = (
            MISSING_PREVIEW_PATH_CATEGORY
            if file_type == "preview"
            else MISSING_THUMBNAIL_PATH_CATEGORY
        )
        findings: list[ConsistencyFinding] = []
        for row in rows:
            path_value = str(row["path"])
            if self.filesystem.path_exists(Path(path_value)):
                continue
            findings.append(
                ConsistencyFinding(
                    category=category,
                    finding_id=f"asset_file:path_missing:{file_type}:{row['id']}",
                    severity=ConsistencySeverity.WARN,
                    repair_mode=ConsistencyRepairMode.INSPECT_ONLY,
                    affected_tables=("public.asset_file",),
                    affected_paths=(path_value,),
                    key_fields={"asset_file_id": str(row["id"])},
                    message=(
                        f"asset_file path is missing in the current container filesystem "
                        f"for type `{file_type}`."
                    ),
                    sample_metadata={
                        "id": row["id"],
                        "assetId": row["assetId"],
                        "path": path_value,
                        "type": row["type"],
                    },
                )
            )
        return findings

    def _build_category(
        self,
        *,
        spec: CategorySpec,
        findings: list[ConsistencyFinding],
    ) -> ConsistencyCategory:
        if findings:
            return ConsistencyCategory(
                name=spec.name,
                severity=spec.severity,
                repair_mode=spec.repair_mode,
                status=(
                    CheckStatus.FAIL
                    if spec.severity == ConsistencySeverity.FAIL
                    else CheckStatus.WARN
                ),
                count=sum(finding.row_count for finding in findings),
                repairable=spec.repair_mode == ConsistencyRepairMode.SAFE_DELETE,
                message=spec.description,
                sample_findings=tuple(findings[: self.sample_limit]),
            )

        return ConsistencyCategory(
            name=spec.name,
            severity=spec.severity,
            repair_mode=spec.repair_mode,
            status=CheckStatus.PASS,
            count=0,
            repairable=spec.repair_mode == ConsistencyRepairMode.SAFE_DELETE,
            message=f"No findings in category `{spec.name}`.",
            sample_findings=(),
        )


@dataclass(slots=True)
class ConsistencyValidationService:
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    sample_limit: int = DEFAULT_SAMPLE_LIMIT

    def run(self, settings: AppSettings) -> ConsistencyValidationReport:
        dsn = settings.postgres_dsn_value()
        if not dsn:
            return ConsistencyValidationReport(
                domain="consistency",
                action="validate",
                summary="Consistency validation failed because database access is not configured.",
                checks=[
                    CheckResult(
                        name="postgres_connection",
                        status=CheckStatus.FAIL,
                        message="Database DSN is not configured.",
                    )
                ],
                categories=[],
                findings=[],
                consistency_summary=ConsistencySummary(
                    profile_name=CONSISTENCY_SCHEMA_DETECTOR_NAME,
                    profile_supported=False,
                ),
                metadata={"environment": settings.environment},
            )

        timeout = settings.postgres_connect_timeout_seconds
        connection_check = self.postgres.validate_connection(dsn, timeout)
        if connection_check.status == CheckStatus.FAIL:
            return ConsistencyValidationReport(
                domain="consistency",
                action="validate",
                summary="Consistency validation failed because PostgreSQL could not be reached.",
                checks=[connection_check],
                categories=[],
                findings=[],
                consistency_summary=ConsistencySummary(
                    profile_name=CONSISTENCY_SCHEMA_DETECTOR_NAME,
                    profile_supported=False,
                ),
                metadata={"environment": settings.environment},
            )

        collected = ConsistencyCollector(
            postgres=self.postgres,
            filesystem=self.filesystem,
            sample_limit=self.sample_limit,
        ).collect(dsn, timeout)
        checks = [connection_check, *collected.checks]

        return ConsistencyValidationReport(
            domain="consistency",
            action="validate",
            summary=self._build_summary(collected),
            checks=checks,
            categories=collected.categories,
            findings=collected.findings,
            consistency_summary=collected.summary,
            recommendations=self._recommendations(collected),
            metadata={
                "environment": settings.environment,
                "database_state": collected.summary.to_dict(),
            },
        )

    def _build_summary(self, collected: CollectedConsistencyState) -> str:
        if not collected.profile_supported:
            return (
                "Consistency validation skipped category execution because the current "
                "PostgreSQL schema capabilities are unsupported."
            )
        if any(category.status == CheckStatus.FAIL for category in collected.categories):
            return "Consistency validation found repairable server-side PostgreSQL orphan links."
        if any(category.status == CheckStatus.WARN for category in collected.categories):
            return "Consistency validation found inspect-only server-side path issues."
        return "Consistency validation found no issues in the supported schema categories."

    def _recommendations(self, collected: CollectedConsistencyState) -> list[str]:
        if not collected.profile_supported:
            return [
                "Inspect the reported schema generation key, capability snapshot, and risk flags "
                "before enabling additional validator variants.",
            ]
        return [
            "Use `consistency repair --category ...` or `--id ...` for safe dry-run planning.",
        ]
