from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from immich_doctor.consistency.service import (
    MISSING_ALBUM_CATEGORY,
    MISSING_ASSET_CATEGORY,
    MISSING_PREVIEW_PATH_CATEGORY,
    MISSING_THUMBNAIL_PATH_CATEGORY,
    ConsistencyValidationService,
)
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus


@dataclass
class FakePostgresAdapter:
    connection_status: CheckStatus = CheckStatus.PASS
    tables: list[dict[str, object]] = field(default_factory=list)
    columns_by_table: dict[tuple[str, str], list[dict[str, object]]] = field(default_factory=dict)
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

    def list_grouped_album_asset_orphans(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        missing_target_table: str,
    ) -> list[dict[str, object]]:
        return self.orphan_rows_by_target.get(missing_target_table, [])

    def list_asset_files_by_type(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        file_type: str,
    ) -> list[dict[str, object]]:
        return self.asset_files_by_type.get(file_type, [])


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
    columns = {
        ("public", "album"): ["id"],
        ("public", "asset"): ["id"],
        ("public", "album_asset"): ["albumId", "assetsId"],
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
                "column_name": value,
                "ordinal_position": index + 1,
            }
            for index, value in enumerate(values)
        ]
        for key, values in columns.items()
    }


def test_consistency_validation_groups_findings_by_category() -> None:
    service = ConsistencyValidationService(
        postgres=FakePostgresAdapter(
            tables=_supported_tables(),
            columns_by_table=_supported_columns(),
            orphan_rows_by_target={
                "asset": [{"albumId": "album-1", "assetsId": "asset-missing-1", "row_count": 2}],
                "album": [{"albumId": "album-missing-1", "assetsId": "asset-1", "row_count": 1}],
            },
        ),
        filesystem=FakeFilesystemAdapter(),
    )

    result = service.run(_settings())

    categories = {category.name: category for category in result.categories}
    assert categories[MISSING_ASSET_CATEGORY].count == 2
    assert categories[MISSING_ALBUM_CATEGORY].count == 1
    assert categories[MISSING_ASSET_CATEGORY].repairable is True


def test_consistency_validation_skips_on_unsupported_schema() -> None:
    service = ConsistencyValidationService(
        postgres=FakePostgresAdapter(
            tables=[{"table_schema": "public", "table_name": "album"}],
            columns_by_table={("public", "album"): _supported_columns()[("public", "album")]},
        ),
        filesystem=FakeFilesystemAdapter(),
    )

    result = service.run(_settings())

    assert result.consistency_summary.profile_supported is False
    assert all(category.status == CheckStatus.SKIP for category in result.categories)


def test_consistency_validation_detects_missing_asset_orphans() -> None:
    service = ConsistencyValidationService(
        postgres=FakePostgresAdapter(
            tables=_supported_tables(),
            columns_by_table=_supported_columns(),
            orphan_rows_by_target={
                "asset": [{"albumId": "album-1", "assetsId": "asset-missing-1", "row_count": 1}]
            },
        ),
        filesystem=FakeFilesystemAdapter(),
    )

    result = service.run(_settings())

    finding = next(
        finding for finding in result.findings if finding.category == MISSING_ASSET_CATEGORY
    )
    assert finding.finding_id == "album_asset:missing_asset:album-1:asset-missing-1"


def test_consistency_validation_detects_missing_album_orphans() -> None:
    service = ConsistencyValidationService(
        postgres=FakePostgresAdapter(
            tables=_supported_tables(),
            columns_by_table=_supported_columns(),
            orphan_rows_by_target={
                "album": [{"albumId": "album-missing-1", "assetsId": "asset-1", "row_count": 1}]
            },
        ),
        filesystem=FakeFilesystemAdapter(),
    )

    result = service.run(_settings())

    finding = next(
        finding for finding in result.findings if finding.category == MISSING_ALBUM_CATEGORY
    )
    assert finding.finding_id == "album_asset:missing_album:album-missing-1:asset-1"


def test_consistency_validation_checks_asset_file_paths_exactly_as_stored(tmp_path) -> None:
    actual_file = tmp_path / "thumb.jpg"
    actual_file.write_text("x", encoding="utf-8")
    service = ConsistencyValidationService(
        postgres=FakePostgresAdapter(
            tables=_supported_tables(),
            columns_by_table=_supported_columns(),
            asset_files_by_type={
                "preview": [
                    {
                        "id": "af-1",
                        "assetId": "asset-1",
                        "type": "preview",
                        "path": str(tmp_path / "different-prefix" / "thumb.jpg"),
                    }
                ],
                "thumbnail": [
                    {
                        "id": "af-2",
                        "assetId": "asset-2",
                        "type": "thumbnail",
                        "path": str(actual_file),
                    }
                ],
            },
        ),
        filesystem=FakeFilesystemAdapter(existing_paths={str(actual_file)}),
    )

    result = service.run(_settings())

    preview_finding = next(
        finding for finding in result.findings if finding.category == MISSING_PREVIEW_PATH_CATEGORY
    )
    assert (
        preview_finding.affected_paths[0].replace("\\", "/").endswith("different-prefix/thumb.jpg")
    )
    assert all(finding.category != MISSING_THUMBNAIL_PATH_CATEGORY for finding in result.findings)
