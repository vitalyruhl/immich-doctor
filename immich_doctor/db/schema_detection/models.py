from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DetectionConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ProductVersionSource(StrEnum):
    VERSION_HISTORY = "version_history"
    UNKNOWN = "unknown"


class DatabaseSchemaSupportStatus(StrEnum):
    SUPPORTED = "supported"
    DRIFTED = "drifted"
    PARTIAL_MIGRATION = "partial_migration"
    UNSUPPORTED = "unsupported"


class AssetDependencyRiskClass(StrEnum):
    CASCADE_LOSS = "cascade_loss"
    SET_NULL_MUTATION = "set_null_mutation"
    RESTRICT_OR_NO_ACTION_BLOCK = "restrict_or_no_action_block"
    ORPHAN_RISK = "orphan_risk"
    INFORMATIONAL = "informational_dependency"
    UNKNOWN = "unknown"


class AssetDependencyCoverageStatus(StrEnum):
    COVERED_SAFE_FOR_ANALYSIS = "covered_safe_for_analysis"
    COVERED_BLOCKING_FOR_APPLY = "covered_blocking_for_apply"
    UNSUPPORTED_BLOCKING = "unsupported_blocking"
    INFORMATIONAL_ONLY = "informational_only"


@dataclass(frozen=True, slots=True)
class ProductVersionEntry:
    version: str
    created_at: str | None = None
    entry_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "created_at": self.created_at,
            "entry_id": self.entry_id,
        }


@dataclass(frozen=True, slots=True)
class ColumnMetadata:
    name: str
    ordinal_position: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ordinal_position": self.ordinal_position,
        }


@dataclass(frozen=True, slots=True)
class ForeignKeyMetadata:
    constraint_name: str
    source_schema: str
    source_table: str
    source_columns: tuple[str, ...]
    target_schema: str
    target_table: str
    target_columns: tuple[str, ...]
    delete_action: str | None = None

    @property
    def source_qualified_name(self) -> str:
        return f"{self.source_schema}.{self.source_table}"

    @property
    def target_qualified_name(self) -> str:
        return f"{self.target_schema}.{self.target_table}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "constraint_name": self.constraint_name,
            "source_table": self.source_qualified_name,
            "source_columns": list(self.source_columns),
            "target_table": self.target_qualified_name,
            "target_columns": list(self.target_columns),
            "delete_action": self.delete_action,
        }


@dataclass(frozen=True, slots=True)
class TableSchemaState:
    schema: str
    name: str
    columns: tuple[ColumnMetadata, ...] = ()
    foreign_keys: tuple[ForeignKeyMetadata, ...] = ()

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.name}"

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    def has_column(self, column_name: str) -> bool:
        return column_name in self.column_names

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "columns": [column.to_dict() for column in self.columns],
            "foreign_keys": [foreign_key.to_dict() for foreign_key in self.foreign_keys],
        }


@dataclass(frozen=True, slots=True)
class AssetDependencyState:
    constraint_name: str
    source_schema: str
    source_table: str
    source_columns: tuple[str, ...]
    target_schema: str
    target_table: str
    target_columns: tuple[str, ...]
    delete_action: str | None
    risk_class: AssetDependencyRiskClass
    coverage_status: AssetDependencyCoverageStatus
    blocks_apply: bool
    reason: str
    notes: tuple[str, ...] = ()

    @property
    def qualified_name(self) -> str:
        return f"{self.source_schema}.{self.source_table}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "constraint_name": self.constraint_name,
            "table": self.qualified_name,
            "column_names": list(self.source_columns),
            "referenced_table": f"{self.target_schema}.{self.target_table}",
            "referenced_column_names": list(self.target_columns),
            "delete_action": self.delete_action,
            "risk_class": self.risk_class.value,
            "coverage_status": self.coverage_status.value,
            "blocks_apply": self.blocks_apply,
            "reason": self.reason,
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class DetectedDatabaseState:
    product_version_current: str | None
    product_version_history: tuple[ProductVersionEntry, ...]
    product_version_confidence: DetectionConfidence
    product_version_source: ProductVersionSource
    schema_generation_key: str
    schema_fingerprint: str
    support_status: DatabaseSchemaSupportStatus
    capabilities: dict[str, bool] = field(default_factory=dict)
    asset_dependencies: tuple[AssetDependencyState, ...] = ()
    risk_flags: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    available_tables: tuple[str, ...] = ()
    inspected_tables: tuple[TableSchemaState, ...] = ()

    def has_capability(self, name: str) -> bool:
        return bool(self.capabilities.get(name, False))

    def table(self, table_name: str, schema: str = "public") -> TableSchemaState | None:
        for table in self.inspected_tables:
            if table.schema == schema and table.name == table_name:
                return table
        return None

    def album_asset_asset_reference_column(self) -> str | None:
        has_asset_id = self.has_capability("album_asset_assetId")
        has_assets_id = self.has_capability("album_asset_assetsId")
        if has_asset_id and not has_assets_id:
            return "assetId"
        if has_assets_id and not has_asset_id:
            return "assetsId"
        return None

    def asset_reference_foreign_keys(self) -> tuple[ForeignKeyMetadata, ...]:
        return tuple(
            foreign_key
            for table in self.inspected_tables
            for foreign_key in table.foreign_keys
            if foreign_key.target_schema == "public" and foreign_key.target_table == "asset"
        )

    def blocking_asset_dependencies(self) -> tuple[AssetDependencyState, ...]:
        return tuple(
            dependency for dependency in self.asset_dependencies if dependency.blocks_apply
        )

    def to_dict(self) -> dict[str, Any]:
        key_capabilities = {
            name: value
            for name, value in sorted(self.capabilities.items())
            if value
            and (
                name.startswith("can_")
                or name.startswith("album_asset_")
                or name.startswith("has_asset")
                or name.startswith("has_album")
                or name.startswith("has_memory")
                or name.startswith("has_stack")
                or name
                in {
                    "has_blocking_asset_dependency_semantics",
                    "has_unsupported_asset_dependency_tables",
                    "has_version_history",
                }
            )
        }
        return {
            "product_version_current": self.product_version_current,
            "product_version_history": [entry.to_dict() for entry in self.product_version_history],
            "product_version_confidence": self.product_version_confidence.value,
            "product_version_source": self.product_version_source.value,
            "schema_generation_key": self.schema_generation_key,
            "schema_fingerprint": self.schema_fingerprint,
            "support_status": self.support_status.value,
            "capabilities": key_capabilities,
            "asset_dependencies": [dependency.to_dict() for dependency in self.asset_dependencies],
            "risk_flags": list(self.risk_flags),
            "notes": list(self.notes),
            "available_tables": list(self.available_tables),
            "inspected_tables": [table.to_dict() for table in self.inspected_tables],
        }
