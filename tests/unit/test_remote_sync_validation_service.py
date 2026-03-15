from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.remote.sync.service import RemoteSyncValidationService


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


def test_remote_sync_validation_passes_with_valid_server_fk_data() -> None:
    service = RemoteSyncValidationService(
        postgres=FakePostgresAdapter(
            tables=_server_tables(),
            foreign_keys_by_table=_album_asset_foreign_keys(),
        )
    )

    result = service.run(_settings())
    album_check = next(
        check for check in result.checks if check.name == "album_asset_missing_albums"
    )
    asset_check = next(
        check for check in result.checks if check.name == "album_asset_missing_assets"
    )

    assert result.domain == "remote.sync"
    assert result.action == "validate"
    assert result.overall_status == CheckStatus.PASS
    assert album_check.status == CheckStatus.PASS
    assert asset_check.status == CheckStatus.PASS


def test_remote_sync_validation_fails_for_missing_album_references() -> None:
    service = RemoteSyncValidationService(
        postgres=FakePostgresAdapter(
            tables=_server_tables(),
            foreign_keys_by_table=_album_asset_foreign_keys(),
            orphan_results={
                "albumId": {
                    "count": 1,
                    "samples": [{"albumId": "album-missing-1", "assetsId": "asset-1"}],
                }
            },
        )
    )

    result = service.run(_settings())
    finding = next(check for check in result.checks if check.name == "album_asset_missing_albums")

    assert result.overall_status == CheckStatus.FAIL
    assert finding.status == CheckStatus.FAIL
    assert finding.details["count"] == 1
    assert finding.details["samples"][0]["albumId"] == "album-missing-1"


def test_remote_sync_validation_fails_for_missing_asset_references() -> None:
    service = RemoteSyncValidationService(
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

    result = service.run(_settings())
    finding = next(check for check in result.checks if check.name == "album_asset_missing_assets")

    assert result.overall_status == CheckStatus.FAIL
    assert finding.status == CheckStatus.FAIL
    assert finding.details["count"] == 2
    assert finding.details["samples"][0]["assetsId"] == "asset-missing-1"


def test_remote_sync_validation_skips_when_album_asset_table_is_missing() -> None:
    service = RemoteSyncValidationService(
        postgres=FakePostgresAdapter(
            tables=[
                {"table_schema": "public", "table_name": "album"},
                {"table_schema": "public", "table_name": "asset"},
            ],
        )
    )

    result = service.run(_settings())
    finding = next(
        check for check in result.checks if check.name == "album_asset_server_consistency"
    )

    assert finding.status == CheckStatus.SKIP
    assert "`album_asset` is missing" in finding.message


def test_remote_sync_validation_skips_when_fk_metadata_is_not_safe() -> None:
    service = RemoteSyncValidationService(
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

    result = service.run(_settings())
    album_check = next(
        check for check in result.checks if check.name == "album_asset_album_fk_resolution"
    )
    orphan_check = next(
        check for check in result.checks if check.name == "album_asset_missing_albums"
    )

    assert album_check.status == CheckStatus.SKIP
    assert orphan_check.status == CheckStatus.SKIP
    assert "could not be resolved safely" in orphan_check.message.lower()
