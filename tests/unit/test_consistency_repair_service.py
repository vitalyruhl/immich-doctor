from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from immich_doctor.consistency.models import ConsistencyRepairStatus
from immich_doctor.consistency.repair_service import ConsistencyRepairService
from immich_doctor.consistency.service import (
    MISSING_ASSET_CATEGORY,
    MISSING_PREVIEW_PATH_CATEGORY,
)
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus


@dataclass
class FakePostgresAdapter:
    connection_status: CheckStatus = CheckStatus.PASS
    tables: list[dict[str, object]] = field(default_factory=list)
    columns_by_table: dict[tuple[str, str], list[dict[str, object]]] = field(default_factory=dict)
    foreign_keys_by_table: dict[tuple[str, str], list[dict[str, object]]] = field(
        default_factory=dict
    )
    orphan_rows_by_target: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    asset_files_by_type: dict[str, list[dict[str, object]]] = field(default_factory=dict)

    def validate_connection(self, dsn: str, timeout_seconds: int) -> CheckResult:
        return CheckResult(
            name="postgres_connection",
            status=self.connection_status,
            message="PostgreSQL connection established.",
        )

    def list_tables(self, dsn: str, timeout_seconds: int) -> list[dict[str, object]]:
        return self.tables

    def list_columns(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        table_schema: str,
        table_name: str,
    ) -> list[dict[str, object]]:
        return self.columns_by_table.get((table_schema, table_name), [])

    def list_foreign_keys(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        table_schema: str,
        table_name: str,
    ) -> list[dict[str, object]]:
        return self.foreign_keys_by_table.get((table_schema, table_name), [])

    def list_version_history_entries(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        table_schema: str,
        table_name: str,
        version_column: str,
        created_at_column: str | None = None,
        entry_id_column: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        return []

    def list_grouped_album_asset_orphans(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        missing_target_table: str,
        asset_reference_column: str,
    ) -> list[dict[str, object]]:
        return list(self.orphan_rows_by_target.get(missing_target_table, []))

    def list_asset_files_by_type(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        file_type: str,
    ) -> list[dict[str, object]]:
        return list(self.asset_files_by_type.get(file_type, []))

    def delete_album_asset_rows_by_keys(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        album_id: str,
        asset_id: str,
        missing_target_table: str,
        asset_reference_column: str,
    ) -> int:
        rows = self.orphan_rows_by_target.get(missing_target_table, [])
        deleted = 0
        remaining = []
        for row in rows:
            if row["albumId"] == album_id and row["assetId"] == asset_id:
                deleted += int(row["row_count"])
                continue
            remaining.append(row)
        self.orphan_rows_by_target[missing_target_table] = remaining
        return deleted


@dataclass
class FakeFilesystemAdapter:
    existing_paths: set[str] = field(default_factory=set)

    def path_exists(self, path: Path) -> bool:
        return str(path) in self.existing_paths


def _settings() -> AppSettings:
    return AppSettings(
        _env_file=None,
        DB_HOST="postgres",
        DB_PORT="5432",
        DB_NAME="immich",
        DB_USER="immich",
        DB_PASSWORD="secret",
    )


def _supported_tables() -> list[dict[str, object]]:
    return [
        {"table_schema": "public", "table_name": "album"},
        {"table_schema": "public", "table_name": "asset"},
        {"table_schema": "public", "table_name": "album_asset"},
        {"table_schema": "public", "table_name": "asset_file"},
    ]


def _supported_columns() -> dict[tuple[str, str], list[dict[str, object]]]:
    base = {
        ("public", "album"): ["id"],
        ("public", "asset"): ["id", "originalPath"],
        ("public", "album_asset"): ["albumId", "assetId"],
        (
            "public",
            "asset_file",
        ): [
            "id",
            "assetId",
            "createdAt",
            "updatedAt",
            "type",
            "path",
            "updateId",
            "isEdited",
            "isProgressive",
        ],
    }
    return {
        key: [
            {
                "table_schema": key[0],
                "table_name": key[1],
                "column_name": column,
                "ordinal_position": index + 1,
            }
            for index, column in enumerate(values)
        ]
        for key, values in base.items()
    }


def _supported_foreign_keys() -> dict[tuple[str, str], list[dict[str, object]]]:
    return {
        ("public", "album_asset"): [
            {
                "constraint_name": "fk_album_asset_album",
                "table_schema": "public",
                "table_name": "album_asset",
                "referenced_table_schema": "public",
                "referenced_table_name": "album",
                "delete_action": "CASCADE",
                "column_names": ["albumId"],
                "referenced_column_names": ["id"],
            },
            {
                "constraint_name": "fk_album_asset_asset",
                "table_schema": "public",
                "table_name": "album_asset",
                "referenced_table_schema": "public",
                "referenced_table_name": "asset",
                "delete_action": "CASCADE",
                "column_names": ["assetId"],
                "referenced_column_names": ["id"],
            },
        ]
    }


def test_consistency_repair_dry_run_by_category_plans_only() -> None:
    service = ConsistencyRepairService(
        postgres=FakePostgresAdapter(
            tables=_supported_tables(),
            columns_by_table=_supported_columns(),
            foreign_keys_by_table=_supported_foreign_keys(),
            orphan_rows_by_target={
                "asset": [{"albumId": "album-1", "assetId": "asset-missing-1", "row_count": 2}]
            },
        ),
        filesystem=FakeFilesystemAdapter(),
    )

    result = service.run(
        _settings(),
        categories=(MISSING_ASSET_CATEGORY,),
        finding_ids=(),
        all_safe=False,
        apply=False,
    )

    action = result.repair_plan.actions[0]
    assert action.status == ConsistencyRepairStatus.WOULD_REPAIR
    assert action.row_count == 2


def test_consistency_repair_dry_run_by_id_plans_single_finding() -> None:
    service = ConsistencyRepairService(
        postgres=FakePostgresAdapter(
            tables=_supported_tables(),
            columns_by_table=_supported_columns(),
            foreign_keys_by_table=_supported_foreign_keys(),
            orphan_rows_by_target={
                "asset": [
                    {"albumId": "album-1", "assetId": "asset-missing-1", "row_count": 1},
                    {"albumId": "album-2", "assetId": "asset-missing-2", "row_count": 1},
                ]
            },
        ),
        filesystem=FakeFilesystemAdapter(),
    )

    result = service.run(
        _settings(),
        categories=(),
        finding_ids=("album_asset:missing_asset:album-2:asset-missing-2",),
        all_safe=False,
        apply=False,
    )

    action = result.repair_plan.actions[0]
    assert action.finding_ids == ("album_asset:missing_asset:album-2:asset-missing-2",)
    assert action.row_count == 1


def test_consistency_repair_apply_by_category_deletes_confirmed_orphans() -> None:
    postgres = FakePostgresAdapter(
        tables=_supported_tables(),
        columns_by_table=_supported_columns(),
        foreign_keys_by_table=_supported_foreign_keys(),
        orphan_rows_by_target={
            "asset": [{"albumId": "album-1", "assetId": "asset-missing-1", "row_count": 1}]
        },
    )
    service = ConsistencyRepairService(postgres=postgres, filesystem=FakeFilesystemAdapter())

    result = service.run(
        _settings(),
        categories=(MISSING_ASSET_CATEGORY,),
        finding_ids=(),
        all_safe=False,
        apply=True,
    )

    assert result.repair_plan.actions[0].status == ConsistencyRepairStatus.REPAIRED
    assert postgres.orphan_rows_by_target["asset"] == []


def test_consistency_repair_apply_by_id_deletes_exact_matching_orphan_only() -> None:
    postgres = FakePostgresAdapter(
        tables=_supported_tables(),
        columns_by_table=_supported_columns(),
        foreign_keys_by_table=_supported_foreign_keys(),
        orphan_rows_by_target={
            "asset": [
                {"albumId": "album-1", "assetId": "asset-missing-1", "row_count": 1},
                {"albumId": "album-2", "assetId": "asset-missing-2", "row_count": 1},
            ]
        },
    )
    service = ConsistencyRepairService(postgres=postgres, filesystem=FakeFilesystemAdapter())

    result = service.run(
        _settings(),
        categories=(),
        finding_ids=("album_asset:missing_asset:album-2:asset-missing-2",),
        all_safe=False,
        apply=True,
    )

    assert result.repair_plan.actions[0].row_count == 1
    assert postgres.orphan_rows_by_target["asset"] == [
        {"albumId": "album-1", "assetId": "asset-missing-1", "row_count": 1}
    ]


def test_consistency_repair_all_safe_selects_only_safe_delete_categories() -> None:
    service = ConsistencyRepairService(
        postgres=FakePostgresAdapter(
            tables=_supported_tables(),
            columns_by_table=_supported_columns(),
            foreign_keys_by_table=_supported_foreign_keys(),
            orphan_rows_by_target={
                "asset": [{"albumId": "album-1", "assetId": "asset-missing-1", "row_count": 1}]
            },
            asset_files_by_type={
                "preview": [
                    {
                        "id": "af-1",
                        "assetId": "asset-1",
                        "type": "preview",
                        "path": "/missing/preview.jpg",
                    }
                ]
            },
        ),
        filesystem=FakeFilesystemAdapter(),
    )

    result = service.run(
        _settings(),
        categories=(),
        finding_ids=(),
        all_safe=True,
        apply=False,
    )

    assert all(
        action.category != MISSING_PREVIEW_PATH_CATEGORY for action in result.repair_plan.actions
    )


def test_consistency_repair_selected_inspect_only_category_is_skipped_not_error() -> None:
    service = ConsistencyRepairService(
        postgres=FakePostgresAdapter(
            tables=_supported_tables(),
            columns_by_table=_supported_columns(),
            foreign_keys_by_table=_supported_foreign_keys(),
            asset_files_by_type={
                "preview": [
                    {
                        "id": "af-1",
                        "assetId": "asset-1",
                        "type": "preview",
                        "path": "/missing/preview.jpg",
                    }
                ]
            },
        ),
        filesystem=FakeFilesystemAdapter(),
    )

    result = service.run(
        _settings(),
        categories=(MISSING_PREVIEW_PATH_CATEGORY,),
        finding_ids=(),
        all_safe=False,
        apply=True,
    )

    assert result.repair_plan.actions[0].status == ConsistencyRepairStatus.SKIPPED


def test_consistency_repair_never_writes_without_apply() -> None:
    postgres = FakePostgresAdapter(
        tables=_supported_tables(),
        columns_by_table=_supported_columns(),
        foreign_keys_by_table=_supported_foreign_keys(),
        orphan_rows_by_target={
            "asset": [{"albumId": "album-1", "assetId": "asset-missing-1", "row_count": 1}]
        },
    )
    service = ConsistencyRepairService(postgres=postgres, filesystem=FakeFilesystemAdapter())

    service.run(
        _settings(),
        categories=(MISSING_ASSET_CATEGORY,),
        finding_ids=(),
        all_safe=False,
        apply=False,
    )

    assert postgres.orphan_rows_by_target["asset"] == [
        {"albumId": "album-1", "assetId": "asset-missing-1", "row_count": 1}
    ]
