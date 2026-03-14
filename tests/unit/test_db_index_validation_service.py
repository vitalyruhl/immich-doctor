from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckStatus
from immich_doctor.db.performance.indexes.service import DbPerformanceIndexesCheckService


@dataclass
class FakePostgresAdapter:
    indexes: list[dict[str, object]] = field(default_factory=list)
    invalid_indexes: list[dict[str, object]] = field(default_factory=list)
    usage_stats: list[dict[str, object]] = field(default_factory=list)
    index_sizes: list[dict[str, object]] = field(default_factory=list)
    missing_fk_indexes: list[dict[str, object]] = field(default_factory=list)

    def list_indexes(self, dsn: str, timeout_seconds: int) -> list[dict[str, object]]:
        return self.indexes

    def list_invalid_indexes(self, dsn: str, timeout_seconds: int) -> list[dict[str, object]]:
        return self.invalid_indexes

    def list_index_usage_stats(self, dsn: str, timeout_seconds: int) -> list[dict[str, object]]:
        return self.usage_stats

    def list_index_sizes(self, dsn: str, timeout_seconds: int) -> list[dict[str, object]]:
        return self.index_sizes

    def list_missing_fk_indexes(self, dsn: str, timeout_seconds: int) -> list[dict[str, object]]:
        return self.missing_fk_indexes


def test_db_index_validation_warns_for_unused_and_missing_fk_indexes() -> None:
    settings = AppSettings(
        _env_file=None,
        DB_HOST="postgres",
        DB_PORT="5432",
        DB_NAME="immich",
        DB_USER="immich",
        DB_PASSWORD="secret",
    )
    service = DbPerformanceIndexesCheckService(
        postgres=FakePostgresAdapter(
            indexes=[
                {
                    "schemaname": "public",
                    "tablename": "assets",
                    "indexname": "assets_pkey",
                    "indexdef": "CREATE UNIQUE INDEX assets_pkey ON public.assets USING btree (id)",
                }
            ],
            usage_stats=[
                {
                    "table_name": "assets",
                    "index_name": "assets_pkey",
                    "idx_scan": 0,
                    "idx_tup_read": 0,
                    "idx_tup_fetch": 0,
                }
            ],
            index_sizes=[
                {
                    "index_name": "assets_pkey",
                    "table_name": "assets",
                    "index_size": "16 kB",
                }
            ],
            missing_fk_indexes=[
                {
                    "table_name": "assets",
                    "conname": "assets_ownerid_fkey",
                    "constraint_definition": "FOREIGN KEY (ownerId) REFERENCES users(id)",
                }
            ],
        )
    )

    result = service.run(settings)

    assert result.domain == "db.performance.indexes"
    assert result.action == "check"
    assert result.overall_status == CheckStatus.WARN
    assert [section.name for section in result.sections] == [
        "INDEX_LIST",
        "INVALID_INDEXES",
        "UNUSED_INDEXES",
        "LARGE_INDEXES",
        "MISSING_FK_INDEXES",
    ]
    assert result.sections[2].status == CheckStatus.WARN
    assert result.sections[4].status == CheckStatus.WARN


def test_db_index_validation_fails_without_database_configuration() -> None:
    result = DbPerformanceIndexesCheckService().run(AppSettings(_env_file=None))

    assert result.overall_status == CheckStatus.FAIL
    assert all(section.status == CheckStatus.FAIL for section in result.sections)
