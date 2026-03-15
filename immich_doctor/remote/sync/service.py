from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport

CLIENT_SIDE_REMOTE_TABLE = "remote_album_asset_entity"
SERVER_TABLES = ("album", "asset", "album_asset")
DEFAULT_SAMPLE_LIMIT = 5


@dataclass(frozen=True, slots=True)
class DetectedTable:
    schema: str
    name: str

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.name}"


@dataclass(frozen=True, slots=True)
class ForeignKeyMapping:
    constraint_name: str
    source_table: DetectedTable
    target_table: DetectedTable
    source_column: str
    target_column: str


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

        available_tables = self.postgres.list_tables(dsn, timeout)
        detected_tables = self._detect_server_tables(available_tables)

        checks = [connection_check]
        checks.append(self._build_scope_boundary_check(available_tables))
        checks.extend(self._build_server_table_checks(detected_tables))
        checks.extend(self._build_server_consistency_checks(dsn, timeout, detected_tables))

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
                    for name, table in detected_tables.items()
                },
            },
        )

    def _detect_server_tables(
        self,
        available_tables: list[dict[str, object]],
    ) -> dict[str, DetectedTable | None]:
        detected: dict[str, DetectedTable | None] = {}
        for table_name in SERVER_TABLES:
            detected[table_name] = self._select_table(available_tables, table_name)
        return detected

    def _select_table(
        self,
        available_tables: list[dict[str, object]],
        table_name: str,
    ) -> DetectedTable | None:
        for table in available_tables:
            if table["table_name"] == table_name:
                return DetectedTable(
                    schema=str(table["table_schema"]),
                    name=str(table["table_name"]),
                )
        return None

    def _build_scope_boundary_check(
        self,
        available_tables: list[dict[str, object]],
    ) -> CheckResult:
        client_side_table_present = any(
            str(table["table_name"]) == CLIENT_SIDE_REMOTE_TABLE for table in available_tables
        )
        message = (
            "The reported `SqliteException(787)` / `remote_album_asset_entity` signature "
            "matches a likely client-side mobile app SQLite issue. This command validates "
            "server-side PostgreSQL album/asset link integrity only."
        )
        if client_side_table_present:
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
                "client_side_table_present_in_postgres": client_side_table_present,
                "remediation_hint": (
                    "Use this result for server-side PostgreSQL diagnostics only. "
                    "immich-doctor cannot inspect the mobile app local SQLite database."
                ),
            },
        )

    def _build_server_table_checks(
        self,
        detected_tables: dict[str, DetectedTable | None],
    ) -> list[CheckResult]:
        checks: list[CheckResult] = []
        for table_name in SERVER_TABLES:
            table = detected_tables[table_name]
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
        detected_tables: dict[str, DetectedTable | None],
    ) -> list[CheckResult]:
        album_asset_table = detected_tables["album_asset"]
        album_table = detected_tables["album"]
        asset_table = detected_tables["asset"]

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

        checks: list[CheckResult] = []
        foreign_keys = self.postgres.list_foreign_keys(
            dsn,
            timeout,
            table_schema=album_asset_table.schema,
            table_name=album_asset_table.name,
        )
        checks.append(
            CheckResult(
                name="album_asset_fk_metadata",
                status=CheckStatus.PASS if foreign_keys else CheckStatus.SKIP,
                message=(
                    "Foreign key metadata for `album_asset` was collected."
                    if foreign_keys
                    else "No foreign key metadata was found for `album_asset`."
                ),
                details={
                    "severity": "info",
                    "count": len(foreign_keys),
                    "impacted_tables": [album_asset_table.qualified_name],
                },
            )
        )

        album_fk = self._resolve_foreign_key_mapping(
            foreign_keys=foreign_keys,
            source_table=album_asset_table,
            target_table=album_table,
            finding_name="album_asset_album_fk_resolution",
            target_label="album",
        )
        asset_fk = self._resolve_foreign_key_mapping(
            foreign_keys=foreign_keys,
            source_table=album_asset_table,
            target_table=asset_table,
            finding_name="album_asset_asset_fk_resolution",
            target_label="asset",
        )
        checks.append(album_fk["check"])
        checks.append(asset_fk["check"])

        if album_fk["mapping"] is None:
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
                        "impacted_tables": [album_asset_table.qualified_name],
                        "expected_table": "album",
                    },
                )
            )
        else:
            sample_columns = self._sample_columns(album_fk["mapping"], asset_fk["mapping"])
            checks.append(
                self._build_orphan_check(
                    dsn=dsn,
                    timeout=timeout,
                    finding_name="album_asset_missing_albums",
                    message_prefix="Server-side `album_asset` rows with missing albums",
                    mapping=album_fk["mapping"],
                    sample_columns=sample_columns,
                )
            )

        if asset_fk["mapping"] is None:
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
                        "impacted_tables": [album_asset_table.qualified_name],
                        "expected_table": "asset",
                    },
                )
            )
        else:
            sample_columns = self._sample_columns(album_fk["mapping"], asset_fk["mapping"])
            checks.append(
                self._build_orphan_check(
                    dsn=dsn,
                    timeout=timeout,
                    finding_name="album_asset_missing_assets",
                    message_prefix="Server-side `album_asset` rows with missing assets",
                    mapping=asset_fk["mapping"],
                    sample_columns=sample_columns,
                )
            )

        return checks

    def _resolve_foreign_key_mapping(
        self,
        *,
        foreign_keys: list[dict[str, object]],
        source_table: DetectedTable,
        target_table: DetectedTable | None,
        finding_name: str,
        target_label: str,
    ) -> dict[str, CheckResult | ForeignKeyMapping | None]:
        if target_table is None:
            return {
                "mapping": None,
                "check": CheckResult(
                    name=finding_name,
                    status=CheckStatus.SKIP,
                    message=(
                        f"Foreign key discovery for `album_asset` -> `{target_label}` was skipped "
                        f"because `{target_label}` is missing from PostgreSQL."
                    ),
                    details={
                        "severity": "info",
                        "expected_table": target_label,
                        "impacted_tables": [source_table.qualified_name],
                    },
                ),
            }

        matching = [
            row
            for row in foreign_keys
            if row["referenced_table_schema"] == target_table.schema
            and row["referenced_table_name"] == target_table.name
        ]

        if len(matching) != 1:
            return {
                "mapping": None,
                "check": CheckResult(
                    name=finding_name,
                    status=CheckStatus.SKIP,
                    message=(
                        f"Foreign key discovery for `album_asset` -> `{target_label}` could not "
                        f"be resolved safely. Expected exactly one FK, found {len(matching)}."
                    ),
                    details={
                        "severity": "info",
                        "count": len(matching),
                        "impacted_tables": [
                            source_table.qualified_name,
                            target_table.qualified_name,
                        ],
                    },
                ),
            }

        row = matching[0]
        source_columns = [str(item) for item in row["column_names"]]
        target_columns = [str(item) for item in row["referenced_column_names"]]
        if len(source_columns) != 1 or len(target_columns) != 1:
            return {
                "mapping": None,
                "check": CheckResult(
                    name=finding_name,
                    status=CheckStatus.SKIP,
                    message=(
                        f"Foreign key discovery for `album_asset` -> `{target_label}` found "
                        "a multi-column relationship that is outside this check's safe scope."
                    ),
                    details={
                        "severity": "info",
                        "impacted_tables": [
                            source_table.qualified_name,
                            target_table.qualified_name,
                        ],
                        "detected_columns": source_columns,
                    },
                ),
            }

        mapping = ForeignKeyMapping(
            constraint_name=str(row["constraint_name"]),
            source_table=source_table,
            target_table=target_table,
            source_column=source_columns[0],
            target_column=target_columns[0],
        )
        return {
            "mapping": mapping,
            "check": CheckResult(
                name=finding_name,
                status=CheckStatus.PASS,
                message=(
                    f"Foreign key discovery for `album_asset` -> `{target_label}` resolved "
                    f"{mapping.source_column} -> {mapping.target_column} via "
                    f"`{mapping.constraint_name}`."
                ),
                details={
                    "severity": "info",
                    "impacted_tables": [
                        source_table.qualified_name,
                        target_table.qualified_name,
                    ],
                    "detected_columns": [mapping.source_column, mapping.target_column],
                },
            ),
        }

    def _sample_columns(
        self,
        album_fk: ForeignKeyMapping | None,
        asset_fk: ForeignKeyMapping | None,
    ) -> tuple[str, ...]:
        columns: list[str] = []
        for mapping in [album_fk, asset_fk]:
            if mapping is None:
                continue
            if mapping.source_column not in columns:
                columns.append(mapping.source_column)
        return tuple(columns)

    def _build_orphan_check(
        self,
        *,
        dsn: str,
        timeout: int,
        finding_name: str,
        message_prefix: str,
        mapping: ForeignKeyMapping,
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
        samples = list(result["samples"])

        if count == 0:
            return CheckResult(
                name=finding_name,
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
            name=finding_name,
            status=CheckStatus.FAIL,
            message=(
                f"{message_prefix}: found {count} orphan references in "
                f"{mapping.source_table.qualified_name}."
            ),
            details={
                "severity": "error",
                "count": count,
                "samples": samples,
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
