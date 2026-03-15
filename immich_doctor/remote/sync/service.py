from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport
from immich_doctor.remote.sync.inspector import (
    RemoteSyncInspection,
    RemoteSyncPostgresInspector,
)

DEFAULT_SAMPLE_LIMIT = 5


@dataclass(slots=True)
class RemoteSyncValidationService:
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)
    sample_limit: int = DEFAULT_SAMPLE_LIMIT

    def run(self, settings: AppSettings) -> ValidationReport:
        dsn = settings.postgres_dsn_value()
        if not dsn:
            return ValidationReport(
                domain="remote.sync",
                action="validate",
                summary="Remote sync validation failed because database access is not configured.",
                checks=[
                    CheckResult(
                        name="postgres_connection",
                        status=CheckStatus.FAIL,
                        message="Database DSN is not configured.",
                    )
                ],
                metadata={"environment": settings.environment},
            )

        timeout = settings.postgres_connect_timeout_seconds
        connection_check = self.postgres.validate_connection(dsn, timeout)
        if connection_check.status == CheckStatus.FAIL:
            return ValidationReport(
                domain="remote.sync",
                action="validate",
                summary="Remote sync validation failed because PostgreSQL could not be reached.",
                checks=[connection_check],
                metadata={"environment": settings.environment},
            )

        inspection = RemoteSyncPostgresInspector(self.postgres).inspect(dsn, timeout)
        checks = [connection_check]
        checks.append(self._build_scope_boundary_check(inspection))
        checks.extend(self._build_server_table_checks(inspection))
        checks.extend(self._build_server_consistency_checks(dsn, timeout, inspection))

        recommendations = [
            check.details["remediation_hint"]
            for check in checks
            if "remediation_hint" in check.details
        ]

        return ValidationReport(
            domain="remote.sync",
            action="validate",
            summary=self._build_summary(checks),
            checks=checks,
            recommendations=recommendations,
            metadata={
                "environment": settings.environment,
                "detected_tables": {
                    name: table.qualified_name if table is not None else None
                    for name, table in inspection.detected_tables.items()
                },
            },
        )

    def _build_scope_boundary_check(self, inspection: RemoteSyncInspection) -> CheckResult:
        message = (
            "The reported `SqliteException(787)` / `remote_album_asset_entity` signature "
            "matches a likely client-side mobile app SQLite issue. This command validates "
            "server-side PostgreSQL album/asset link integrity only."
        )
        if inspection.client_side_table_present_in_postgres:
            message = (
                "The reported `SqliteException(787)` / `remote_album_asset_entity` signature "
                "still points to a likely client-side mobile app SQLite issue. A same-named "
                "table also exists in PostgreSQL and should be reviewed manually."
            )

        return CheckResult(
            name="remote_sync_scope_boundary",
            status=CheckStatus.PASS,
            message=message,
            details={
                "severity": "info",
                "remediation_hint": (
                    "Use this result for server-side PostgreSQL diagnostics only. "
                    "immich-doctor cannot inspect the mobile app local SQLite database."
                ),
            },
        )

    def _build_server_table_checks(self, inspection: RemoteSyncInspection) -> list[CheckResult]:
        checks: list[CheckResult] = []
        for table_name, table in inspection.detected_tables.items():
            if table is None:
                checks.append(
                    CheckResult(
                        name=f"server_table_{table_name}",
                        status=CheckStatus.SKIP,
                        message=(
                            f"Server-side table `{table_name}` was not detected in PostgreSQL. "
                            "Related album/asset integrity checks cannot run."
                        ),
                        details={
                            "severity": "info",
                            "expected_table": table_name,
                        },
                    )
                )
                continue

            checks.append(
                CheckResult(
                    name=f"server_table_{table_name}",
                    status=CheckStatus.PASS,
                    message=f"Server-side table `{table_name}` detected at {table.qualified_name}.",
                    details={
                        "severity": "info",
                        "impacted_tables": [table.qualified_name],
                    },
                )
            )
        return checks

    def _build_server_consistency_checks(
        self,
        dsn: str,
        timeout: int,
        inspection: RemoteSyncInspection,
    ) -> list[CheckResult]:
        album_asset_table = inspection.detected_tables["album_asset"]
        if album_asset_table is None:
            return [
                CheckResult(
                    name="album_asset_server_consistency",
                    status=CheckStatus.SKIP,
                    message=(
                        "Server-side album/asset integrity checks were not run because "
                        "`album_asset` is missing from PostgreSQL."
                    ),
                    details={
                        "severity": "info",
                        "expected_table": "album_asset",
                    },
                )
            ]

        checks = [
            CheckResult(
                name="album_asset_fk_metadata",
                status=(
                    CheckStatus.PASS
                    if inspection.album_asset_foreign_keys
                    else CheckStatus.SKIP
                ),
                message=(
                    "Foreign key metadata for `album_asset` was collected."
                    if inspection.album_asset_foreign_keys
                    else "No foreign key metadata was found for `album_asset`."
                ),
                details={
                    "severity": "info",
                    "count": len(inspection.album_asset_foreign_keys),
                    "impacted_tables": [album_asset_table.qualified_name],
                },
            )
        ]
        checks.append(
            self._resolution_check(
                name="album_asset_album_fk_resolution",
                target_label="album",
                resolution=inspection.album_resolution,
            )
        )
        checks.append(
            self._resolution_check(
                name="album_asset_asset_fk_resolution",
                target_label="asset",
                resolution=inspection.asset_resolution,
            )
        )

        if inspection.album_resolution.mapping is None:
            checks.append(
                CheckResult(
                    name="album_asset_missing_albums",
                    status=CheckStatus.SKIP,
                    message=(
                        "Server-side `album_asset` orphan album check was not run because "
                        "the foreign key to `album` could not be resolved safely."
                    ),
                    details={
                        "severity": "info",
                        "expected_table": "album",
                        "impacted_tables": [album_asset_table.qualified_name],
                    },
                )
            )
        else:
            checks.append(
                self._orphan_check(
                    dsn=dsn,
                    timeout=timeout,
                    name="album_asset_missing_albums",
                    message_prefix="Server-side `album_asset` rows with missing albums",
                    mapping=inspection.album_resolution.mapping,
                    sample_columns=self._sample_columns(inspection),
                )
            )

        if inspection.asset_resolution.mapping is None:
            checks.append(
                CheckResult(
                    name="album_asset_missing_assets",
                    status=CheckStatus.SKIP,
                    message=(
                        "Server-side `album_asset` orphan asset check was not run because "
                        "the foreign key to `asset` could not be resolved safely."
                    ),
                    details={
                        "severity": "info",
                        "expected_table": "asset",
                        "impacted_tables": [album_asset_table.qualified_name],
                    },
                )
            )
        else:
            checks.append(
                self._orphan_check(
                    dsn=dsn,
                    timeout=timeout,
                    name="album_asset_missing_assets",
                    message_prefix="Server-side `album_asset` rows with missing assets",
                    mapping=inspection.asset_resolution.mapping,
                    sample_columns=self._sample_columns(inspection),
                )
            )

        return checks

    def _resolution_check(self, name: str, target_label: str, resolution) -> CheckResult:
        if resolution.mapping is None:
            return CheckResult(
                name=name,
                status=CheckStatus.SKIP,
                message=(
                    f"Foreign key discovery for `album_asset` -> `{target_label}` could not "
                    "be resolved safely."
                ),
                details={
                    "severity": "info",
                    "count": resolution.matched_count,
                    "detected_columns": list(resolution.detected_columns),
                },
            )

        mapping = resolution.mapping
        return CheckResult(
            name=name,
            status=CheckStatus.PASS,
            message=(
                f"Foreign key discovery for `album_asset` -> `{target_label}` resolved "
                f"{mapping.source_column} -> {mapping.target_column} via "
                f"`{mapping.constraint_name}`."
            ),
            details={
                "severity": "info",
                "impacted_tables": [
                    mapping.source_table.qualified_name,
                    mapping.target_table.qualified_name,
                ],
                "detected_columns": [mapping.source_column, mapping.target_column],
            },
        )

    def _sample_columns(self, inspection: RemoteSyncInspection) -> tuple[str, ...]:
        columns: list[str] = []
        for resolution in [inspection.album_resolution, inspection.asset_resolution]:
            mapping = resolution.mapping
            if mapping is not None and mapping.source_column not in columns:
                columns.append(mapping.source_column)
        return tuple(columns)

    def _orphan_check(
        self,
        dsn: str,
        timeout: int,
        name: str,
        message_prefix: str,
        mapping,
        sample_columns: tuple[str, ...],
    ) -> CheckResult:
        result = self.postgres.find_missing_foreign_key_rows(
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
        count = int(result["count"])
        if count == 0:
            return CheckResult(
                name=name,
                status=CheckStatus.PASS,
                message=(
                    f"{message_prefix}: no orphan references found in "
                    f"{mapping.source_table.qualified_name}."
                ),
                details={
                    "severity": "info",
                    "count": 0,
                    "samples": [],
                    "impacted_tables": [
                        mapping.source_table.qualified_name,
                        mapping.target_table.qualified_name,
                    ],
                },
            )

        return CheckResult(
            name=name,
            status=CheckStatus.FAIL,
            message=(
                f"{message_prefix}: found {count} orphan references in "
                f"{mapping.source_table.qualified_name}."
            ),
            details={
                "severity": "error",
                "count": count,
                "samples": list(result["samples"]),
                "impacted_tables": [
                    mapping.source_table.qualified_name,
                    mapping.target_table.qualified_name,
                ],
                "remediation_hint": (
                    "Review album/asset link consistency manually before changing records. "
                    "This command is read-only and does not repair PostgreSQL data."
                ),
            },
        )

    def _build_summary(self, checks: list[CheckResult]) -> str:
        if any(check.status == CheckStatus.FAIL for check in checks):
            return "Remote sync validation found server-side PostgreSQL album/asset link issues."
        if any(check.status == CheckStatus.SKIP for check in checks):
            return (
                "Remote sync validation completed with partial server-side PostgreSQL coverage. "
                "See skipped checks for unresolved schema metadata."
            )
        return "Remote sync validation found no server-side PostgreSQL album/asset link issues."
