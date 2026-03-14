from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport, ValidationSection


@dataclass(slots=True)
class DbPerformanceIndexesCheckService:
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)

    def run(self, settings: AppSettings) -> ValidationReport:
        dsn = settings.postgres_dsn_value()
        if not dsn:
            return ValidationReport(
                domain="db.performance.indexes",
                action="check",
                summary="Database index checks failed.",
                checks=[
                    CheckResult(
                        name="postgres_connection",
                        status=CheckStatus.FAIL,
                        message="Database DSN is not configured.",
                    )
                ],
                sections=[
                    ValidationSection(name="INDEX_LIST", status=CheckStatus.FAIL),
                    ValidationSection(name="INVALID_INDEXES", status=CheckStatus.FAIL),
                    ValidationSection(name="UNUSED_INDEXES", status=CheckStatus.FAIL),
                    ValidationSection(name="LARGE_INDEXES", status=CheckStatus.FAIL),
                    ValidationSection(name="MISSING_FK_INDEXES", status=CheckStatus.FAIL),
                ],
            )

        timeout = settings.postgres_connect_timeout_seconds
        index_list = self.postgres.list_indexes(dsn, timeout)
        invalid_indexes = self.postgres.list_invalid_indexes(dsn, timeout)
        usage_stats = self.postgres.list_index_usage_stats(dsn, timeout)
        unused_indexes = [row for row in usage_stats if row["idx_scan"] == 0]
        index_sizes = self.postgres.list_index_sizes(dsn, timeout)
        missing_fk_indexes = self.postgres.list_missing_fk_indexes(dsn, timeout)

        return ValidationReport(
            domain="db.performance.indexes",
            action="check",
            summary="Database index checks completed.",
            checks=[],
            sections=[
                ValidationSection(
                    name="INDEX_LIST",
                    status=CheckStatus.PASS,
                    rows=index_list,
                ),
                ValidationSection(
                    name="INVALID_INDEXES",
                    status=CheckStatus.FAIL if invalid_indexes else CheckStatus.PASS,
                    rows=invalid_indexes,
                ),
                ValidationSection(
                    name="UNUSED_INDEXES",
                    status=CheckStatus.WARN if unused_indexes else CheckStatus.PASS,
                    rows=unused_indexes,
                ),
                ValidationSection(
                    name="LARGE_INDEXES",
                    status=CheckStatus.PASS,
                    rows=index_sizes,
                ),
                ValidationSection(
                    name="MISSING_FK_INDEXES",
                    status=CheckStatus.WARN if missing_fk_indexes else CheckStatus.PASS,
                    rows=missing_fk_indexes,
                ),
            ],
            metadata={"environment": settings.environment},
        )
