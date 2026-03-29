from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.db.schema_detection import (
    DatabaseSchemaSupportStatus,
    DatabaseStateDetector,
)


@dataclass
class FakePostgresAdapter:
    tables: list[dict[str, object]] = field(default_factory=list)
    columns_by_table: dict[tuple[str, str], list[dict[str, object]]] = field(default_factory=dict)
    foreign_keys_by_table: dict[tuple[str, str], list[dict[str, object]]] = field(
        default_factory=dict
    )
    version_history_entries: list[dict[str, object]] = field(default_factory=list)

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
        return self.version_history_entries[:limit]


def _tables(include_version_history: bool = True) -> list[dict[str, object]]:
    tables = [
        {"table_schema": "public", "table_name": "asset"},
        {"table_schema": "public", "table_name": "album"},
        {"table_schema": "public", "table_name": "album_asset"},
        {"table_schema": "public", "table_name": "asset_file"},
        {"table_schema": "public", "table_name": "asset_job_status"},
        {"table_schema": "public", "table_name": "memory"},
        {"table_schema": "public", "table_name": "memory_asset"},
        {"table_schema": "public", "table_name": "stack"},
    ]
    if include_version_history:
        tables.append({"table_schema": "public", "table_name": "version_history"})
    return tables


def _columns(
    *,
    asset_reference_column: str = "assetId",
    include_version_history: bool = True,
) -> dict[tuple[str, str], list[dict[str, object]]]:
    values = {
        ("public", "asset"): ["id", "originalPath", "livePhotoVideoId"],
        ("public", "album"): ["id", "albumThumbnailAssetId"],
        ("public", "album_asset"): ["albumId", asset_reference_column],
        (
            "public",
            "asset_file",
        ): [
            "id",
            "assetId",
            "type",
            "path",
            "createdAt",
            "updatedAt",
            "updateId",
            "isEdited",
            "isProgressive",
        ],
        ("public", "asset_job_status"): ["assetId", "metadataExtractedAt"],
        ("public", "memory"): ["id"],
        ("public", "memory_asset"): ["memoriesId", "assetId"],
        ("public", "stack"): ["id", "primaryAssetId"],
    }
    if include_version_history:
        values[("public", "version_history")] = ["id", "createdAt", "version"]
    return {
        key: [
            {
                "table_schema": key[0],
                "table_name": key[1],
                "column_name": value,
                "ordinal_position": index + 1,
            }
            for index, value in enumerate(columns)
        ]
        for key, columns in values.items()
    }


def _foreign_keys(
    *,
    asset_reference_column: str = "assetId",
) -> dict[tuple[str, str], list[dict[str, object]]]:
    return {
        ("public", "album"): [
            {
                "constraint_name": "album_albumThumbnailAssetId_fkey",
                "table_schema": "public",
                "table_name": "album",
                "referenced_table_schema": "public",
                "referenced_table_name": "asset",
                "delete_action": "SET NULL",
                "column_names": ["albumThumbnailAssetId"],
                "referenced_column_names": ["id"],
            }
        ],
        ("public", "album_asset"): [
            {
                "constraint_name": "album_asset_albumId_fkey",
                "table_schema": "public",
                "table_name": "album_asset",
                "referenced_table_schema": "public",
                "referenced_table_name": "album",
                "delete_action": "CASCADE",
                "column_names": ["albumId"],
                "referenced_column_names": ["id"],
            },
            {
                "constraint_name": "album_asset_asset_fkey",
                "table_schema": "public",
                "table_name": "album_asset",
                "referenced_table_schema": "public",
                "referenced_table_name": "asset",
                "delete_action": "CASCADE",
                "column_names": [asset_reference_column],
                "referenced_column_names": ["id"],
            },
        ],
        ("public", "asset_file"): [
            {
                "constraint_name": "asset_file_assetId_fkey",
                "table_schema": "public",
                "table_name": "asset_file",
                "referenced_table_schema": "public",
                "referenced_table_name": "asset",
                "delete_action": "CASCADE",
                "column_names": ["assetId"],
                "referenced_column_names": ["id"],
            }
        ],
        ("public", "asset_job_status"): [
            {
                "constraint_name": "asset_job_status_assetId_fkey",
                "table_schema": "public",
                "table_name": "asset_job_status",
                "referenced_table_schema": "public",
                "referenced_table_name": "asset",
                "delete_action": "CASCADE",
                "column_names": ["assetId"],
                "referenced_column_names": ["id"],
            }
        ],
        ("public", "memory_asset"): [
            {
                "constraint_name": "memory_asset_assetId_fkey",
                "table_schema": "public",
                "table_name": "memory_asset",
                "referenced_table_schema": "public",
                "referenced_table_name": "asset",
                "delete_action": "CASCADE",
                "column_names": ["assetId"],
                "referenced_column_names": ["id"],
            },
            {
                "constraint_name": "memory_asset_memoriesId_fkey",
                "table_schema": "public",
                "table_name": "memory_asset",
                "referenced_table_schema": "public",
                "referenced_table_name": "memory",
                "delete_action": "CASCADE",
                "column_names": ["memoriesId"],
                "referenced_column_names": ["id"],
            },
        ],
        ("public", "stack"): [
            {
                "constraint_name": "stack_primaryAssetId_fkey",
                "table_schema": "public",
                "table_name": "stack",
                "referenced_table_schema": "public",
                "referenced_table_name": "asset",
                "delete_action": "NO ACTION",
                "column_names": ["primaryAssetId"],
                "referenced_column_names": ["id"],
            }
        ],
    }


def _version_history_entries() -> list[dict[str, object]]:
    return [
        {
            "entry_id": "vh-1",
            "created_at": "2026-03-07T23:06:01+00:00",
            "version": "2.5.6",
        },
        {
            "entry_id": "vh-0",
            "created_at": "2025-11-21T15:28:34+00:00",
            "version": "2.3.1",
        },
    ]


def test_database_state_detector_reads_version_history_when_present() -> None:
    detector = DatabaseStateDetector(
        postgres=FakePostgresAdapter(
            tables=_tables(),
            columns_by_table=_columns(),
            foreign_keys_by_table=_foreign_keys(),
            version_history_entries=_version_history_entries(),
        )
    )

    state = detector.detect("dsn", 5)

    assert state.product_version_current == "2.5.6"
    assert state.product_version_confidence.value == "high"
    assert len(state.product_version_history) == 2
    assert state.support_status == DatabaseSchemaSupportStatus.SUPPORTED


def test_database_state_detector_returns_unknown_version_without_version_table() -> None:
    detector = DatabaseStateDetector(
        postgres=FakePostgresAdapter(
            tables=_tables(include_version_history=False),
            columns_by_table=_columns(include_version_history=False),
            foreign_keys_by_table=_foreign_keys(),
        )
    )

    state = detector.detect("dsn", 5)

    assert state.product_version_current is None
    assert "unknown_product_version" in state.risk_flags


def test_database_state_detector_supports_assets_id_schema_generation() -> None:
    detector = DatabaseStateDetector(
        postgres=FakePostgresAdapter(
            tables=_tables(),
            columns_by_table=_columns(asset_reference_column="assetsId"),
            foreign_keys_by_table=_foreign_keys(asset_reference_column="assetsId"),
            version_history_entries=_version_history_entries(),
        )
    )

    state = detector.detect("dsn", 5)

    assert state.album_asset_asset_reference_column() == "assetsId"
    assert "album_asset.assetsId" in state.schema_generation_key
    assert state.has_capability("can_validate_album_asset_missing_asset") is True


def test_database_state_detector_flags_partial_migration_when_both_columns_exist() -> None:
    columns = _columns(asset_reference_column="assetId")
    columns[("public", "album_asset")] = [
        {
            "table_schema": "public",
            "table_name": "album_asset",
            "column_name": column_name,
            "ordinal_position": index + 1,
        }
        for index, column_name in enumerate(("albumId", "assetId", "assetsId"))
    ]
    detector = DatabaseStateDetector(
        postgres=FakePostgresAdapter(
            tables=_tables(),
            columns_by_table=columns,
            foreign_keys_by_table=_foreign_keys(asset_reference_column="assetId"),
            version_history_entries=_version_history_entries(),
        )
    )

    state = detector.detect("dsn", 5)

    assert state.support_status == DatabaseSchemaSupportStatus.PARTIAL_MIGRATION
    assert "partial_migration_state" in state.risk_flags
    assert state.album_asset_asset_reference_column() is None
