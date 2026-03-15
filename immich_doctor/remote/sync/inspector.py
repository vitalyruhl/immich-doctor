from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.adapters.postgres import PostgresAdapter

CLIENT_SIDE_REMOTE_TABLE = "remote_album_asset_entity"
SERVER_TABLES = ("album", "asset", "album_asset")


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


@dataclass(frozen=True, slots=True)
class MappingResolution:
    mapping: ForeignKeyMapping | None
    issue: str | None = None
    issue_kind: str | None = None
    matched_count: int = 0
    detected_columns: tuple[str, ...] = ()


@dataclass(slots=True)
class RemoteSyncInspection:
    available_tables: list[dict[str, object]]
    detected_tables: dict[str, DetectedTable | None]
    album_asset_foreign_keys: list[dict[str, object]] = field(default_factory=list)
    album_resolution: MappingResolution = field(default_factory=lambda: MappingResolution(None))
    asset_resolution: MappingResolution = field(default_factory=lambda: MappingResolution(None))

    @property
    def client_side_table_present_in_postgres(self) -> bool:
        return any(
            str(table["table_name"]) == CLIENT_SIDE_REMOTE_TABLE for table in self.available_tables
        )


@dataclass(slots=True)
class RemoteSyncPostgresInspector:
    postgres: PostgresAdapter

    def inspect(self, dsn: str, timeout: int) -> RemoteSyncInspection:
        available_tables = self.postgres.list_tables(dsn, timeout)
        detected_tables = {
            table_name: self._select_table(available_tables, table_name)
            for table_name in SERVER_TABLES
        }

        album_asset_table = detected_tables["album_asset"]
        if album_asset_table is None:
            return RemoteSyncInspection(
                available_tables=available_tables,
                detected_tables=detected_tables,
            )

        foreign_keys = self.postgres.list_foreign_keys(
            dsn,
            timeout,
            table_schema=album_asset_table.schema,
            table_name=album_asset_table.name,
        )

        return RemoteSyncInspection(
            available_tables=available_tables,
            detected_tables=detected_tables,
            album_asset_foreign_keys=foreign_keys,
            album_resolution=self._resolve_foreign_key_mapping(
                foreign_keys=foreign_keys,
                source_table=album_asset_table,
                target_table=detected_tables["album"],
                target_label="album",
            ),
            asset_resolution=self._resolve_foreign_key_mapping(
                foreign_keys=foreign_keys,
                source_table=album_asset_table,
                target_table=detected_tables["asset"],
                target_label="asset",
            ),
        )

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

    def _resolve_foreign_key_mapping(
        self,
        *,
        foreign_keys: list[dict[str, object]],
        source_table: DetectedTable,
        target_table: DetectedTable | None,
        target_label: str,
    ) -> MappingResolution:
        if target_table is None:
            return MappingResolution(
                mapping=None,
                issue=f"`{target_label}` is missing from PostgreSQL.",
                issue_kind="missing_target_table",
            )

        matching = [
            row
            for row in foreign_keys
            if row["referenced_table_schema"] == target_table.schema
            and row["referenced_table_name"] == target_table.name
        ]
        if len(matching) != 1:
            return MappingResolution(
                mapping=None,
                issue=(
                    f"Expected exactly one FK from `{source_table.name}` to `{target_label}`, "
                    f"found {len(matching)}."
                ),
                issue_kind="ambiguous_foreign_key",
                matched_count=len(matching),
            )

        row = matching[0]
        source_columns = tuple(str(item) for item in row["column_names"])
        target_columns = tuple(str(item) for item in row["referenced_column_names"])
        if len(source_columns) != 1 or len(target_columns) != 1:
            return MappingResolution(
                mapping=None,
                issue=(
                    f"FK `{row['constraint_name']}` is multi-column and outside the "
                    "safe repair scope."
                ),
                issue_kind="multi_column_foreign_key",
                matched_count=1,
                detected_columns=source_columns,
            )

        return MappingResolution(
            mapping=ForeignKeyMapping(
                constraint_name=str(row["constraint_name"]),
                source_table=source_table,
                target_table=target_table,
                source_column=source_columns[0],
                target_column=target_columns[0],
            ),
            matched_count=1,
            detected_columns=source_columns + target_columns,
        )
