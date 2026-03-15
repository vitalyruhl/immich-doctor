from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus, RepairItemStatus
from immich_doctor.remote.sync.repair_service import RemoteSyncRepairService


@dataclass
class FakePostgresAdapter:
    connection_status: CheckStatus = CheckStatus.PASS
    tables: list[dict[str, object]] = field(default_factory=list)
    foreign_keys_by_table: dict[tuple[str, str], list[dict[str, object]]] = field(
        default_factory=dict
    )
    orphan_results: dict[str, dict[str, object]] = field(default_factory=dict)

    def validate_connection(self, dsn: str, timeout_seconds: int) -> CheckResult:
        return CheckResult(
            name="postgres_connection",
            status=self.connection_status,
            message="PostgreSQL connection established."
            if self.connection_status == CheckStatus.PASS
            else "PostgreSQL connection failed.",
        )

    def list_tables(self, dsn: str, timeout_seconds: int) -> list[dict[str, object]]:
        return self.tables

    def list_foreign_keys(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        table_schema: str,
        table_name: str,
    ) -> list[dict[str, object]]:
        return self.foreign_keys_by_table.get((table_schema, table_name), [])

    def find_missing_foreign_key_rows(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        link_schema: str,
        link_table: str,
        reference_schema: str,
        reference_table: str,
        link_column: str,
        reference_column: str,
        sample_columns: tuple[str, ...],
        sample_limit: int,
    ) -> dict[str, object]:
        return self.orphan_results.get(link_column, {"count": 0, "samples": []})

    def delete_missing_foreign_key_rows(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        link_schema: str,
        link_table: str,
        reference_schema: str,
        reference_table: str,
        link_column: str,
        reference_column: str,
        sample_columns: tuple[str, ...],
        sample_limit: int,
    ) -> dict[str, object]:
        result = self.orphan_results.get(link_column, {"count": 0, "samples": []})
        self.orphan_results[link_column] = {"count": 0, "samples": []}
        return result


def _settings() -> AppSettings:
    return AppSettings(
        _env_file=None,
        DB_HOST="postgres",
        DB_PORT="5432",
        DB_NAME="immich",
        DB_USER="immich",
        DB_PASSWORD="secret",
    )


def _server_tables() -> list[dict[str, object]]:
    return [
        {"table_schema": "public", "table_name": "album"},
        {"table_schema": "public", "table_name": "asset"},
        {"table_schema": "public", "table_name": "album_asset"},
    ]


def _album_asset_foreign_keys() -> dict[tuple[str, str], list[dict[str, object]]]:
    return {
        ("public", "album_asset"): [
            {
                "table_schema": "public",
                "table_name": "album_asset",
                "constraint_name": "FK_album_asset_album",
                "referenced_table_schema": "public",
                "referenced_table_name": "album",
                "column_names": ["albumId"],
                "referenced_column_names": ["id"],
            },
            {
                "table_schema": "public",
                "table_name": "album_asset",
                "constraint_name": "FK_album_asset_asset",
                "referenced_table_schema": "public",
                "referenced_table_name": "asset",
                "column_names": ["assetsId"],
                "referenced_column_names": ["id"],
            },
        ]
    }


def test_remote_sync_repair_dry_run_noop_without_orphans() -> None:
    service = RemoteSyncRepairService(
        postgres=FakePostgresAdapter(
            tables=_server_tables(),
            foreign_keys_by_table=_album_asset_foreign_keys(),
        )
    )

    result = service.run(_settings(), apply=False)

    assert result.overall_status == CheckStatus.PASS
    assert all(plan.row_count == 0 for plan in result.plans)
    assert all(plan.applied is False for plan in result.plans)


def test_remote_sync_repair_dry_run_plans_orphan_asset_deletions_only() -> None:
    service = RemoteSyncRepairService(
        postgres=FakePostgresAdapter(
            tables=_server_tables(),
            foreign_keys_by_table=_album_asset_foreign_keys(),
            orphan_results={
                "assetsId": {
                    "count": 2,
                    "samples": [
                        {"albumId": "album-1", "assetsId": "asset-missing-1"},
                        {"albumId": "album-2", "assetsId": "asset-missing-2"},
                    ],
                }
            },
        )
    )

    result = service.run(_settings(), apply=False)
    plan = next(plan for plan in result.plans if "asset references" in plan.reason)

    assert plan.status == RepairItemStatus.PLANNED
    assert plan.row_count == 2
    assert plan.applied is False
    assert plan.backup_sql is not None


def test_remote_sync_repair_apply_deletes_orphan_asset_links_and_revalidates() -> None:
    postgres = FakePostgresAdapter(
        tables=_server_tables(),
        foreign_keys_by_table=_album_asset_foreign_keys(),
        orphan_results={
            "assetsId": {
                "count": 1,
                "samples": [{"albumId": "album-1", "assetsId": "asset-missing-1"}],
            }
        },
    )
    service = RemoteSyncRepairService(postgres=postgres)

    result = service.run(_settings(), apply=True)
    plan = next(plan for plan in result.plans if "asset references" in plan.reason)
    post_check = next(check for check in result.checks if check.name == "post_repair_validation")

    assert plan.status == RepairItemStatus.REPAIRED
    assert plan.applied is True
    assert plan.row_count == 1
    assert post_check.status == CheckStatus.PASS


def test_remote_sync_repair_apply_deletes_orphan_album_links() -> None:
    postgres = FakePostgresAdapter(
        tables=_server_tables(),
        foreign_keys_by_table=_album_asset_foreign_keys(),
        orphan_results={
            "albumId": {
                "count": 1,
                "samples": [{"albumId": "album-missing-1", "assetsId": "asset-1"}],
            }
        },
    )
    service = RemoteSyncRepairService(postgres=postgres)

    result = service.run(_settings(), apply=True)
    plan = next(plan for plan in result.plans if "album references" in plan.reason)

    assert plan.status == RepairItemStatus.REPAIRED
    assert plan.row_count == 1


def test_remote_sync_repair_skips_when_schema_is_missing() -> None:
    service = RemoteSyncRepairService(
        postgres=FakePostgresAdapter(
            tables=[
                {"table_schema": "public", "table_name": "album"},
                {"table_schema": "public", "table_name": "asset"},
            ]
        )
    )

    result = service.run(_settings(), apply=False)

    assert all(plan.status == RepairItemStatus.SKIPPED for plan in result.plans)


def test_remote_sync_repair_never_writes_without_apply() -> None:
    postgres = FakePostgresAdapter(
        tables=_server_tables(),
        foreign_keys_by_table=_album_asset_foreign_keys(),
        orphan_results={
            "assetsId": {
                "count": 1,
                "samples": [{"albumId": "album-1", "assetsId": "asset-missing-1"}],
            }
        },
    )
    service = RemoteSyncRepairService(postgres=postgres)

    result = service.run(_settings(), apply=False)
    plan = next(plan for plan in result.plans if "asset references" in plan.reason)

    assert plan.applied is False
    assert postgres.orphan_results["assetsId"]["count"] == 1


def test_remote_sync_repair_skips_when_fk_metadata_is_unsafe() -> None:
    service = RemoteSyncRepairService(
        postgres=FakePostgresAdapter(
            tables=_server_tables(),
            foreign_keys_by_table={
                ("public", "album_asset"): [
                    {
                        "table_schema": "public",
                        "table_name": "album_asset",
                        "constraint_name": "FK_album_asset_album_composite",
                        "referenced_table_schema": "public",
                        "referenced_table_name": "album",
                        "column_names": ["albumId", "order"],
                        "referenced_column_names": ["id", "id"],
                    }
                ]
            },
        )
    )

    result = service.run(_settings(), apply=False)

    assert any(plan.status == RepairItemStatus.SKIPPED for plan in result.plans)
