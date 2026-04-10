from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.catalog.consistency_state import (
    DB_MISSING_SECTION,
    ORPHAN_SECTION,
    STORAGE_MISSING_SECTION,
    UNMAPPED_SECTION,
    ZERO_BYTE_SECTION,
    CatalogConsistencyStateCollector,
)
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import (
    CheckResult,
    CheckStatus,
    ValidationReport,
    ValidationSection,
)

_DEFAULT_SAMPLE_LIMIT = 200


def _section_status(rows: list[dict[str, object]]) -> CheckStatus:
    return CheckStatus.FAIL if rows else CheckStatus.PASS


@dataclass(slots=True)
class CatalogConsistencyValidationService:
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)
    sample_limit: int = _DEFAULT_SAMPLE_LIMIT

    def run(
        self,
        settings: AppSettings,
        *,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> ValidationReport:
        collector = CatalogConsistencyStateCollector(postgres=self.postgres)
        snapshot_state = collector.prepare_snapshot_state(settings)
        checks = list(snapshot_state.checks)
        if not snapshot_state.ready:
            return ValidationReport(
                domain="consistency.catalog",
                action="validate",
                summary=(
                    "Catalog-backed consistency is waiting for a current committed storage index."
                ),
                checks=checks,
                metadata=snapshot_state.metadata,
                recommendations=[
                    "Run a catalog scan from the Storage page before starting the "
                    "consistency validation.",
                ],
            )

        dsn = settings.postgres_dsn_value()
        if not dsn:
            return ValidationReport(
                domain="consistency.catalog",
                action="validate",
                summary=(
                    "Catalog-backed consistency failed because database access is not configured."
                ),
                checks=[
                    *checks,
                    CheckResult(
                        name="postgres_connection",
                        status=CheckStatus.FAIL,
                        message="Database DSN is not configured.",
                    ),
                ],
                metadata={"latestSnapshots": snapshot_state.latest_snapshots},
            )

        timeout = settings.postgres_connect_timeout_seconds
        connection_check = self.postgres.validate_connection(dsn, timeout)
        if connection_check.status == CheckStatus.FAIL:
            return ValidationReport(
                domain="consistency.catalog",
                action="validate",
                summary=(
                    "Catalog-backed consistency failed because PostgreSQL could not be reached."
                ),
                checks=[*checks, connection_check],
                metadata={"latestSnapshots": snapshot_state.latest_snapshots},
            )

        state = collector.collect(settings, progress_callback=progress_callback)
        sampled_db_missing = state.db_missing_rows[: self.sample_limit]
        sampled_storage_missing = state.storage_missing_rows[: self.sample_limit]
        sampled_orphans = state.orphan_rows[: self.sample_limit]
        sampled_unmapped = state.unmapped_rows[: self.sample_limit]
        real_issue_count = (
            len(state.db_missing_rows)
            + len(state.storage_missing_rows)
            + len(state.orphan_rows)
            + len(state.zero_byte_rows)
            + len(state.unmapped_rows)
        )

        summary = (
            "Catalog-backed consistency compared the cached storage inventory "
            "against the live database and reports only actionable inconsistencies: "
            f"{len(state.db_missing_rows)} DB originals not found in the current storage snapshot, "
            f"{len(state.storage_missing_rows)} storage originals missing in DB, "
            f"{len(state.orphan_rows)} orphan derivatives, and "
            f"{len(state.zero_byte_rows)} zero-byte findings. "
            f"Suppressed {state.valid_motion_video_components} valid motion video components; "
            f"{real_issue_count} real issues remain."
        )

        return ValidationReport(
            domain="consistency.catalog",
            action="validate",
            summary=summary,
            checks=state.checks,
            sections=[
                ValidationSection(
                    name=DB_MISSING_SECTION,
                    status=_section_status(state.db_missing_rows),
                    rows=sampled_db_missing,
                ),
                ValidationSection(
                    name=STORAGE_MISSING_SECTION,
                    status=_section_status(state.storage_missing_rows),
                    rows=sampled_storage_missing,
                ),
                ValidationSection(
                    name=ORPHAN_SECTION,
                    status=_section_status(state.orphan_rows),
                    rows=sampled_orphans,
                ),
                ValidationSection(
                    name=ZERO_BYTE_SECTION,
                    status=_section_status(state.zero_byte_rows[: self.sample_limit]),
                    rows=state.zero_byte_rows[: self.sample_limit],
                ),
                ValidationSection(
                    name=UNMAPPED_SECTION,
                    status=CheckStatus.WARN if state.unmapped_rows else CheckStatus.PASS,
                    rows=sampled_unmapped,
                ),
            ],
            metrics=[
                {
                    "name": "db_originals_missing_on_storage",
                    "value": len(state.db_missing_rows),
                },
                {
                    "name": "storage_originals_missing_in_db",
                    "value": len(state.storage_missing_rows),
                },
                {
                    "name": "orphan_derivatives_without_original",
                    "value": len(state.orphan_rows),
                },
                {"name": "zero_byte_files", "value": len(state.zero_byte_rows)},
                {"name": "unmapped_database_paths", "value": len(state.unmapped_rows)},
            ],
            metadata={
                "configuredRoots": state.configured_root_slugs,
                "latestSnapshots": state.latest_snapshots,
                "snapshotBasis": state.snapshot_basis,
                "latestScanCommittedAt": state.latest_scan_committed_at,
                "sampleLimit": self.sample_limit,
                "totals": {
                    "totalAssetsScanned": state.total_assets_scanned,
                    "dbOriginalsMissingOnStorage": len(state.db_missing_rows),
                    "storageOriginalsMissingInDb": len(state.storage_missing_rows),
                    "orphanDerivativesWithoutOriginal": len(state.orphan_rows),
                    "zeroByteFiles": len(state.zero_byte_rows),
                    "unmappedDatabasePaths": len(state.unmapped_rows),
                    "filteredNoiseRemoved": state.valid_motion_video_components,
                    "validMotionVideoComponents": state.valid_motion_video_components,
                    "realIssuesRemaining": real_issue_count,
                },
                "truncated": {
                    DB_MISSING_SECTION: len(state.db_missing_rows) > self.sample_limit,
                    STORAGE_MISSING_SECTION: len(state.storage_missing_rows) > self.sample_limit,
                    ORPHAN_SECTION: len(state.orphan_rows) > self.sample_limit,
                    UNMAPPED_SECTION: len(state.unmapped_rows) > self.sample_limit,
                },
            },
            recommendations=[
                "Run a catalog rescan from the Storage page when the mounted storage has changed.",
                "Use the catalog-backed counts as cached storage truth before "
                "starting any destructive workflow.",
            ],
        )
