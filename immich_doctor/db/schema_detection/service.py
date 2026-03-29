from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.db.schema_detection.models import (
    ColumnMetadata,
    DatabaseSchemaSupportStatus,
    DetectedDatabaseState,
    DetectionConfidence,
    ForeignKeyMetadata,
    ProductVersionEntry,
    ProductVersionSource,
    TableSchemaState,
)

DEFAULT_SCHEMA_DETECTION_TABLES = (
    "version_history",
    "asset",
    "album",
    "album_asset",
    "asset_file",
    "asset_job_status",
    "memory",
    "memory_asset",
    "stack",
)
SUPPORTED_DIRECT_ASSET_RELATION_TABLES = {
    ("public", "album_asset"),
    ("public", "asset_file"),
    ("public", "asset_job_status"),
}


@dataclass(slots=True)
class DatabaseStateDetector:
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)

    def detect(self, dsn: str, timeout: int) -> DetectedDatabaseState:
        available_tables_raw = self.postgres.list_tables(dsn, timeout)
        available_tables = tuple(
            sorted(
                f"{table['table_schema']}.{table['table_name']}" for table in available_tables_raw
            )
        )
        table_states = [
            self._table_state(
                dsn,
                timeout,
                table_schema=str(table["table_schema"]),
                table_name=str(table["table_name"]),
            )
            for table in available_tables_raw
        ]
        table_states.sort(key=lambda item: item.qualified_name)

        (
            product_version_current,
            product_version_history,
            version_confidence,
            version_source,
            notes,
        ) = self._detect_product_version(dsn, timeout, table_states)
        capabilities = self._derive_capabilities(table_states)
        risk_flags = self._derive_risk_flags(
            capabilities=capabilities,
            product_version_current=product_version_current,
        )
        support_status = self._derive_support_status(risk_flags)
        schema_generation_key = self._schema_generation_key(capabilities)
        schema_fingerprint = self._schema_fingerprint(table_states)

        return DetectedDatabaseState(
            product_version_current=product_version_current,
            product_version_history=product_version_history,
            product_version_confidence=version_confidence,
            product_version_source=version_source,
            schema_generation_key=schema_generation_key,
            schema_fingerprint=schema_fingerprint,
            support_status=support_status,
            capabilities=capabilities,
            risk_flags=risk_flags,
            notes=notes,
            available_tables=available_tables,
            inspected_tables=tuple(table_states),
        )

    def _table_state(
        self,
        dsn: str,
        timeout: int,
        *,
        table_schema: str,
        table_name: str,
    ) -> TableSchemaState:
        raw_columns = self.postgres.list_columns(
            dsn,
            timeout,
            table_schema=table_schema,
            table_name=table_name,
        )
        columns = tuple(
            ColumnMetadata(
                name=str(column["column_name"]),
                ordinal_position=int(column.get("ordinal_position") or index),
            )
            for index, column in enumerate(raw_columns, start=1)
        )
        foreign_keys = tuple(
            ForeignKeyMetadata(
                constraint_name=str(row["constraint_name"]),
                source_schema=str(row.get("table_schema") or table_schema),
                source_table=str(row.get("table_name") or table_name),
                source_columns=tuple(str(item) for item in row["column_names"]),
                target_schema=str(row["referenced_table_schema"]),
                target_table=str(row["referenced_table_name"]),
                target_columns=tuple(str(item) for item in row["referenced_column_names"]),
                delete_action=(
                    str(row["delete_action"])
                    if row.get("delete_action") is not None
                    else None
                ),
            )
            for row in self.postgres.list_foreign_keys(
                dsn,
                timeout,
                table_schema=table_schema,
                table_name=table_name,
            )
        )
        return TableSchemaState(
            schema=table_schema,
            name=table_name,
            columns=columns,
            foreign_keys=foreign_keys,
        )

    def _detect_product_version(
        self,
        dsn: str,
        timeout: int,
        table_states: list[TableSchemaState],
    ) -> tuple[
        str | None,
        tuple[ProductVersionEntry, ...],
        DetectionConfidence,
        ProductVersionSource,
        tuple[str, ...],
    ]:
        version_table = self._table(table_states, "version_history")
        if version_table is None:
            return (
                None,
                (),
                DetectionConfidence.UNKNOWN,
                ProductVersionSource.UNKNOWN,
                ("Product version metadata table `public.version_history` was not found.",),
            )

        if not version_table.has_column("version"):
            return (
                None,
                (),
                DetectionConfidence.LOW,
                ProductVersionSource.VERSION_HISTORY,
                (
                    "`public.version_history` exists but does not expose a readable "
                    "`version` column.",
                ),
            )

        entries_raw = self.postgres.list_version_history_entries(
            dsn,
            timeout,
            table_schema="public",
            table_name="version_history",
            version_column="version",
            created_at_column=(
                "createdAt" if version_table.has_column("createdAt") else None
            ),
            entry_id_column=("id" if version_table.has_column("id") else None),
        )
        entries = tuple(
            ProductVersionEntry(
                version=str(row["version"]),
                created_at=(
                    str(row["created_at"]) if row.get("created_at") is not None else None
                ),
                entry_id=(str(row["entry_id"]) if row.get("entry_id") is not None else None),
            )
            for row in entries_raw
            if row.get("version")
        )
        if not entries:
            return (
                None,
                (),
                DetectionConfidence.MEDIUM,
                ProductVersionSource.VERSION_HISTORY,
                ("`public.version_history` exists but contains no readable version entries.",),
            )

        return (
            entries[0].version,
            entries,
            DetectionConfidence.HIGH,
            ProductVersionSource.VERSION_HISTORY,
            (),
        )

    def _derive_capabilities(self, table_states: list[TableSchemaState]) -> dict[str, bool]:
        capabilities: dict[str, bool] = {}

        def has_table(name: str) -> bool:
            return self._table(table_states, name) is not None

        def has_column(table_name: str, column_name: str) -> bool:
            table = self._table(table_states, table_name)
            return table.has_column(column_name) if table is not None else False

        def has_fk(
            source_table: str,
            target_table: str,
            *,
            source_column: str | None = None,
            target_column: str | None = None,
        ) -> bool:
            table = self._table(table_states, source_table)
            if table is None:
                return False
            for foreign_key in table.foreign_keys:
                if (
                    foreign_key.target_schema != "public"
                    or foreign_key.target_table != target_table
                ):
                    continue
                if source_column is not None and foreign_key.source_columns != (source_column,):
                    continue
                if target_column is not None and foreign_key.target_columns != (target_column,):
                    continue
                return True
            return False

        capabilities["has_version_history"] = has_table("version_history")
        capabilities["has_asset"] = has_table("asset")
        capabilities["has_asset_originalPath"] = has_column("asset", "originalPath")
        capabilities["has_album"] = has_table("album")
        capabilities["has_album_thumbnail_asset_reference"] = has_column(
            "album", "albumThumbnailAssetId"
        )
        capabilities["has_album_thumbnail_asset_fk"] = has_fk(
            "album",
            "asset",
            source_column="albumThumbnailAssetId",
            target_column="id",
        )
        capabilities["has_album_asset"] = has_table("album_asset")
        capabilities["album_asset_albumId"] = has_column("album_asset", "albumId")
        capabilities["album_asset_assetId"] = has_column("album_asset", "assetId")
        capabilities["album_asset_assetsId"] = has_column("album_asset", "assetsId")
        capabilities["album_asset_album_fk"] = has_fk(
            "album_asset",
            "album",
            source_column="albumId",
            target_column="id",
        )
        capabilities["album_asset_asset_fk_assetId"] = has_fk(
            "album_asset",
            "asset",
            source_column="assetId",
            target_column="id",
        )
        capabilities["album_asset_asset_fk_assetsId"] = has_fk(
            "album_asset",
            "asset",
            source_column="assetsId",
            target_column="id",
        )
        capabilities["has_asset_file"] = has_table("asset_file")
        capabilities["has_asset_file_asset_fk"] = has_fk(
            "asset_file",
            "asset",
            source_column="assetId",
            target_column="id",
        )
        capabilities["has_asset_job_status"] = has_table("asset_job_status")
        capabilities["has_asset_job_status_asset_fk"] = has_fk(
            "asset_job_status",
            "asset",
            source_column="assetId",
            target_column="id",
        )
        capabilities["has_memory"] = has_table("memory")
        capabilities["has_memory_asset"] = has_table("memory_asset")
        capabilities["has_memory_asset_memory_fk"] = has_fk(
            "memory_asset",
            "memory",
            source_column="memoriesId",
            target_column="id",
        )
        capabilities["has_memory_asset_asset_fk"] = has_fk(
            "memory_asset",
            "asset",
            source_column="assetId",
            target_column="id",
        )
        capabilities["has_stack"] = has_table("stack")
        capabilities["has_stack_primaryAssetId"] = has_column("stack", "primaryAssetId")
        capabilities["has_stack_primary_asset_fk"] = has_fk(
            "stack",
            "asset",
            source_column="primaryAssetId",
            target_column="id",
        )

        album_asset_has_single_asset_column = (
            capabilities["album_asset_assetId"] ^ capabilities["album_asset_assetsId"]
        )
        capabilities["can_validate_album_asset_missing_asset"] = (
            capabilities["has_asset"]
            and capabilities["has_album"]
            and capabilities["has_album_asset"]
            and capabilities["album_asset_albumId"]
            and album_asset_has_single_asset_column
        )
        capabilities["can_validate_album_asset_missing_album"] = (
            capabilities["can_validate_album_asset_missing_asset"]
        )
        capabilities["can_validate_asset_file_paths"] = (
            capabilities["has_asset_file"]
            and has_column("asset_file", "path")
            and has_column("asset_file", "type")
        )
        capabilities["can_validate_missing_asset_reference"] = (
            capabilities["has_asset"] and capabilities["has_asset_originalPath"]
        )
        capabilities["can_evaluate_asset_delete_dependency_risk"] = capabilities["has_asset"]

        asset_reference_foreign_keys = [
            foreign_key
            for table in table_states
            for foreign_key in table.foreign_keys
            if foreign_key.target_schema == "public" and foreign_key.target_table == "asset"
        ]
        capabilities["has_unsupported_asset_dependency_tables"] = any(
            (foreign_key.source_schema, foreign_key.source_table)
            not in SUPPORTED_DIRECT_ASSET_RELATION_TABLES
            for foreign_key in asset_reference_foreign_keys
        )
        return capabilities

    def _derive_risk_flags(
        self,
        *,
        capabilities: dict[str, bool],
        product_version_current: str | None,
    ) -> tuple[str, ...]:
        flags: list[str] = []
        if product_version_current is None:
            flags.append("unknown_product_version")
        if (
            not capabilities["has_asset"]
            or not capabilities["has_album"]
            or not capabilities["has_album_asset"]
        ):
            flags.append("missing_required_dependency_table")
        if capabilities["album_asset_assetId"] and capabilities["album_asset_assetsId"]:
            flags.append("partial_migration_state")
        if not (
            capabilities["album_asset_assetId"] or capabilities["album_asset_assetsId"]
        ) and capabilities["has_album_asset"]:
            flags.append("unsupported_schema_shape")
        if capabilities["has_album_asset"] and not capabilities["album_asset_albumId"]:
            flags.append("schema_drift")
        if capabilities["has_album_asset"] and not (
            capabilities["album_asset_asset_fk_assetId"]
            or capabilities["album_asset_asset_fk_assetsId"]
        ):
            flags.append("schema_drift")
        if capabilities["has_unsupported_asset_dependency_tables"]:
            flags.append("unsupported_asset_dependency_tables")
        if not capabilities["can_validate_album_asset_missing_asset"]:
            flags.append("unsupported_schema_shape")
        return tuple(dict.fromkeys(flags))

    def _derive_support_status(
        self,
        risk_flags: tuple[str, ...],
    ) -> DatabaseSchemaSupportStatus:
        if "partial_migration_state" in risk_flags:
            return DatabaseSchemaSupportStatus.PARTIAL_MIGRATION
        if {
            "missing_required_dependency_table",
            "unsupported_schema_shape",
        }.intersection(risk_flags):
            return DatabaseSchemaSupportStatus.UNSUPPORTED
        if "schema_drift" in risk_flags:
            return DatabaseSchemaSupportStatus.DRIFTED
        return DatabaseSchemaSupportStatus.SUPPORTED

    def _schema_generation_key(self, capabilities: dict[str, bool]) -> str:
        if capabilities["album_asset_assetId"] and not capabilities["album_asset_assetsId"]:
            album_asset_variant = "album_asset.assetId"
        elif capabilities["album_asset_assetsId"] and not capabilities["album_asset_assetId"]:
            album_asset_variant = "album_asset.assetsId"
        elif capabilities["album_asset_assetId"] and capabilities["album_asset_assetsId"]:
            album_asset_variant = "album_asset.dual_asset_columns"
        else:
            album_asset_variant = "album_asset.unknown_asset_column"

        traits = [
            album_asset_variant,
            "memory_asset" if capabilities["has_memory_asset"] else "no_memory_asset",
            (
                "album_thumbnail_asset"
                if capabilities["has_album_thumbnail_asset_reference"]
                else "no_album_thumbnail_asset"
            ),
            (
                "stack_primary_asset"
                if capabilities["has_stack_primaryAssetId"]
                else "no_stack_primary_asset"
            ),
            "version_history" if capabilities["has_version_history"] else "no_version_history",
        ]
        return "immich_schema:" + "+".join(traits)

    def _schema_fingerprint(self, table_states: list[TableSchemaState]) -> str:
        relevant_tables = [
            table.to_dict()
            for table in table_states
            if table.name in DEFAULT_SCHEMA_DETECTION_TABLES
            or any(
                foreign_key.target_schema == "public" and foreign_key.target_table == "asset"
                for foreign_key in table.foreign_keys
            )
        ]
        payload = json.dumps(relevant_tables, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _table(
        self,
        table_states: list[TableSchemaState],
        table_name: str,
        schema: str = "public",
    ) -> TableSchemaState | None:
        for table in table_states:
            if table.schema == schema and table.name == table_name:
                return table
        return None
