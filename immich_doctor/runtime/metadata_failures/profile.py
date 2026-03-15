from __future__ import annotations

from dataclasses import dataclass

from immich_doctor.adapters.postgres import PostgresAdapter

RUNTIME_METADATA_PROFILE_NAME = "immich_runtime_metadata_profile"


@dataclass(frozen=True, slots=True)
class RuntimeMetadataProfile:
    name: str
    required_tables: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class RuntimeMetadataProfileResult:
    profile: RuntimeMetadataProfile
    supported: bool
    detected_tables: dict[str, str | None]
    missing_tables: tuple[str, ...]
    missing_columns: dict[str, tuple[str, ...]]


CURRENT_RUNTIME_METADATA_PROFILE = RuntimeMetadataProfile(
    name=RUNTIME_METADATA_PROFILE_NAME,
    required_tables={
        "asset": ("id", "type", "originalPath"),
        "asset_file": ("id", "assetId", "type", "path"),
        "asset_job_status": ("assetId", "metadataExtractedAt"),
    },
)


class RuntimeMetadataProfileDetector:
    def __init__(self, postgres: PostgresAdapter) -> None:
        self.postgres = postgres

    def detect(self, dsn: str, timeout: int) -> RuntimeMetadataProfileResult:
        tables = self.postgres.list_tables(dsn, timeout)
        table_lookup = {
            str(table["table_name"]): f"{table['table_schema']}.{table['table_name']}"
            for table in tables
        }
        missing_tables: list[str] = []
        missing_columns: dict[str, tuple[str, ...]] = {}

        required_tables = CURRENT_RUNTIME_METADATA_PROFILE.required_tables.items()
        for table_name, required_columns in required_tables:
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

        return RuntimeMetadataProfileResult(
            profile=CURRENT_RUNTIME_METADATA_PROFILE,
            supported=not missing_tables and not missing_columns,
            detected_tables={
                name: table_lookup.get(name)
                for name in CURRENT_RUNTIME_METADATA_PROFILE.required_tables
            },
            missing_tables=tuple(missing_tables),
            missing_columns=missing_columns,
        )
