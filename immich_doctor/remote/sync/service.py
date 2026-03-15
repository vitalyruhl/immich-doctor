from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport

REMOTE_ALBUM_ASSET_LINK_TABLE_CANDIDATES = ("remote_album_asset_entity",)
ASSET_TABLE_CANDIDATES = ("asset_entity", "assets")
REMOTE_ALBUM_TABLE_CANDIDATES = ("remote_album_entity", "remote_albums")
DEFAULT_SAMPLE_LIMIT = 5


@dataclass(frozen=True, slots=True)
class DetectedTable:
    schema: str
    name: str

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.name}"


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
                summary="Remote sync validation failed.",
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
                summary="Remote sync validation failed.",
                checks=[connection_check],
                metadata={"environment": settings.environment},
            )

        available_tables = self.postgres.list_tables(dsn, timeout)
        link_table = self._select_table(available_tables, REMOTE_ALBUM_ASSET_LINK_TABLE_CANDIDATES)
        asset_table = self._select_table(available_tables, ASSET_TABLE_CANDIDATES)
        remote_album_table = self._select_table(available_tables, REMOTE_ALBUM_TABLE_CANDIDATES)

        checks = [
            connection_check,
            self._table_check(
                name="remote_album_asset_link_table",
                label="Remote album asset link table",
                table=link_table,
                candidates=REMOTE_ALBUM_ASSET_LINK_TABLE_CANDIDATES,
            ),
            self._table_check(
                name="asset_reference_table",
                label="Asset reference table",
                table=asset_table,
                candidates=ASSET_TABLE_CANDIDATES,
            ),
            self._table_check(
                name="remote_album_reference_table",
                label="Remote album reference table",
                table=remote_album_table,
                candidates=REMOTE_ALBUM_TABLE_CANDIDATES,
            ),
        ]

        checks.append(
            self._build_finding_check(
                dsn=dsn,
                timeout=timeout,
                finding_name="remote_album_asset_missing_assets",
                message_prefix="Remote album asset rows with missing asset references",
                link_table=link_table,
                reference_table=asset_table,
                link_column="asset_id",
                candidates=(
                    *REMOTE_ALBUM_ASSET_LINK_TABLE_CANDIDATES,
                    *ASSET_TABLE_CANDIDATES,
                ),
            )
        )
        checks.append(
            self._build_finding_check(
                dsn=dsn,
                timeout=timeout,
                finding_name="remote_album_asset_missing_albums",
                message_prefix="Remote album asset rows with missing album references",
                link_table=link_table,
                reference_table=remote_album_table,
                link_column="album_id",
                candidates=(
                    *REMOTE_ALBUM_ASSET_LINK_TABLE_CANDIDATES,
                    *REMOTE_ALBUM_TABLE_CANDIDATES,
                ),
            )
        )

        summary = self._build_summary(checks)
        recommendations = [
            check.details["remediation_hint"]
            for check in checks
            if check.status == CheckStatus.FAIL and "remediation_hint" in check.details
        ]

        return ValidationReport(
            domain="remote.sync",
            action="validate",
            summary=summary,
            checks=checks,
            recommendations=recommendations,
            metadata={
                "environment": settings.environment,
                "detected_tables": {
                    "remote_album_asset_link": (
                        link_table.qualified_name if link_table is not None else None
                    ),
                    "asset_reference": (
                        asset_table.qualified_name if asset_table is not None else None
                    ),
                    "remote_album_reference": (
                        remote_album_table.qualified_name
                        if remote_album_table is not None
                        else None
                    ),
                },
            },
        )

    def _select_table(
        self,
        available_tables: list[dict[str, object]],
        candidates: tuple[str, ...],
    ) -> DetectedTable | None:
        for candidate in candidates:
            for table in available_tables:
                if table["table_name"] == candidate:
                    return DetectedTable(
                        schema=str(table["table_schema"]),
                        name=str(table["table_name"]),
                    )
        return None

    def _table_check(
        self,
        *,
        name: str,
        label: str,
        table: DetectedTable | None,
        candidates: tuple[str, ...],
    ) -> CheckResult:
        if table is None:
            return CheckResult(
                name=name,
                status=CheckStatus.SKIP,
                message=f"{label} was not found. Validation will skip dependent checks.",
                details={
                    "severity": "info",
                    "candidates": list(candidates),
                },
            )

        return CheckResult(
            name=name,
            status=CheckStatus.PASS,
            message=f"{label} detected at {table.qualified_name}.",
            details={
                "severity": "info",
                "impacted_tables": [table.qualified_name],
            },
        )

    def _build_finding_check(
        self,
        *,
        dsn: str,
        timeout: int,
        finding_name: str,
        message_prefix: str,
        link_table: DetectedTable | None,
        reference_table: DetectedTable | None,
        link_column: str,
        candidates: tuple[str, ...],
    ) -> CheckResult:
        if link_table is None or reference_table is None:
            missing_roles: list[str] = []
            if link_table is None:
                missing_roles.append("remote album asset link table")
            if reference_table is None:
                missing_roles.append("reference table")

            return CheckResult(
                name=finding_name,
                status=CheckStatus.SKIP,
                message=(
                    f"{message_prefix} skipped because required tables are missing: "
                    + ", ".join(missing_roles)
                    + "."
                ),
                details={
                    "severity": "info",
                    "candidates": list(candidates),
                },
            )

        result = self.postgres.find_missing_foreign_key_rows(
            dsn,
            timeout,
            link_schema=link_table.schema,
            link_table=link_table.name,
            reference_schema=reference_table.schema,
            reference_table=reference_table.name,
            link_column=link_column,
            sample_limit=self.sample_limit,
        )
        count = int(result["count"])
        samples = list(result["samples"])

        if count == 0:
            return CheckResult(
                name=finding_name,
                status=CheckStatus.PASS,
                message=(
                    f"{message_prefix}: no inconsistencies found between "
                    f"{link_table.qualified_name} and {reference_table.qualified_name}."
                ),
                details={
                    "severity": "info",
                    "count": 0,
                    "samples": [],
                    "impacted_tables": [
                        link_table.qualified_name,
                        reference_table.qualified_name,
                    ],
                },
            )

        return CheckResult(
            name=finding_name,
            status=CheckStatus.FAIL,
            message=(
                f"{message_prefix}: found {count} broken references between "
                f"{link_table.qualified_name} and {reference_table.qualified_name}."
            ),
            details={
                "severity": "error",
                "count": count,
                "samples": samples,
                "impacted_tables": [
                    link_table.qualified_name,
                    reference_table.qualified_name,
                ],
                "remediation_hint": (
                    "Investigate remote sync state in Immich before changing data manually. "
                    "This command is read-only and only reports orphaned references."
                ),
            },
        )

    def _build_summary(self, checks: list[CheckResult]) -> str:
        if any(check.status == CheckStatus.FAIL for check in checks):
            return "Remote sync validation found foreign key inconsistencies."
        if any(check.status == CheckStatus.SKIP for check in checks):
            return "Remote sync validation completed with skipped checks."
        return "Remote sync validation completed with no foreign key inconsistencies."
