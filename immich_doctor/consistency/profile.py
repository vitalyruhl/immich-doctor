from __future__ import annotations

from dataclasses import dataclass

from immich_doctor.adapters.postgres import PostgresAdapter

CURRENT_PROFILE_NAME = "immich_current_postgres_profile"


@dataclass(frozen=True, slots=True)
class SupportedSchemaProfile:
    name: str
    required_tables: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class SchemaProfileResult:
    profile: SupportedSchemaProfile
    supported: bool
    detected_tables: dict[str, str | None]
    missing_tables: tuple[str, ...]
    missing_columns: dict[str, tuple[str, ...]]


CURRENT_POSTGRES_PROFILE = SupportedSchemaProfile(
    name=CURRENT_PROFILE_NAME,
    required_tables={
        "album": ("id",),
        "asset": ("id",),
        "album_asset": ("albumId", "assetsId"),
        "asset_file": (
            "id",
            "assetId",
            "createdAt",
            "updatedAt",
            "type",
            "path",
            "updateId",
            "isEdited",
            "isProgressive",
        ),
    },
)


class SchemaProfileDetector:
    def __init__(self, postgres: PostgresAdapter) -> None:
        self.postgres = postgres

    def detect_current_profile(self, dsn: str, timeout: int) -> SchemaProfileResult:
        tables = self.postgres.list_tables(dsn, timeout)
        table_lookup = {
            str(table["table_name"]): f"{table['table_schema']}.{table['table_name']}"
            for table in tables
        }
        missing_tables: list[str] = []
        missing_columns: dict[str, tuple[str, ...]] = {}

        for table_name, required_columns in CURRENT_POSTGRES_PROFILE.required_tables.items():
            qualified_name = table_lookup.get(table_name)
            if qualified_name is None:
                missing_tables.append(table_name)
                continue

            table_schema, resolved_table_name = qualified_name.split(".", maxsplit=1)
            columns = self.postgres.list_columns(
                dsn,
                timeout,
                table_schema=table_schema,
                table_name=resolved_table_name,
            )
            detected_columns = {str(column["column_name"]) for column in columns}
            absent = tuple(column for column in required_columns if column not in detected_columns)
            if absent:
                missing_columns[table_name] = absent

        return SchemaProfileResult(
            profile=CURRENT_POSTGRES_PROFILE,
            supported=not missing_tables and not missing_columns,
            detected_tables={
                name: table_lookup.get(name) for name in CURRENT_POSTGRES_PROFILE.required_tables
            },
            missing_tables=tuple(missing_tables),
            missing_columns=missing_columns,
        )
