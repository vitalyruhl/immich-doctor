from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckStatus
from immich_doctor.remote.sync.service import RemoteSyncValidationService


@dataclass
class FakePostgresAdapter:
    connection_status: CheckStatus = CheckStatus.PASS
    tables: list[dict[str, object]] = field(default_factory=list)
    orphan_results: dict[str, dict[str, object]] = field(default_factory=dict)

    def validate_connection(self, dsn: str, timeout_seconds: int):
        from immich_doctor.core.models import CheckResult

        return CheckResult(
            name="postgres_connection",
            status=self.connection_status,
            message="PostgreSQL connection established."
            if self.connection_status == CheckStatus.PASS
            else "PostgreSQL connection failed.",
        )

    def list_tables(self, dsn: str, timeout_seconds: int) -> list[dict[str, object]]:
        return self.tables

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


def _base_tables() -> list[dict[str, object]]:
    return [
        {"table_schema": "public", "table_name": "remote_album_asset_entity"},
        {"table_schema": "public", "table_name": "asset_entity"},
        {"table_schema": "public", "table_name": "remote_album_entity"},
    ]


def test_remote_sync_validation_passes_with_valid_dataset() -> None:
    service = RemoteSyncValidationService(
        postgres=FakePostgresAdapter(
            tables=_base_tables(),
        )
    )

    result = service.run(_settings())

    assert result.domain == "remote.sync"
    assert result.action == "validate"
    assert result.overall_status == CheckStatus.PASS
    assert any(check.name == "remote_album_asset_missing_assets" for check in result.checks)
    assert any(check.name == "remote_album_asset_missing_albums" for check in result.checks)


def test_remote_sync_validation_fails_for_missing_asset_references() -> None:
    service = RemoteSyncValidationService(
        postgres=FakePostgresAdapter(
            tables=_base_tables(),
            orphan_results={
                "asset_id": {
                    "count": 2,
                    "samples": [
                        {"asset_id": "asset-missing-1", "album_id": "album-1"},
                        {"asset_id": "asset-missing-2", "album_id": "album-2"},
                    ],
                }
            },
        )
    )

    result = service.run(_settings())
    finding = next(
        check for check in result.checks if check.name == "remote_album_asset_missing_assets"
    )

    assert result.overall_status == CheckStatus.FAIL
    assert finding.status == CheckStatus.FAIL
    assert finding.details["count"] == 2
    assert finding.details["samples"][0]["asset_id"] == "asset-missing-1"


def test_remote_sync_validation_fails_for_missing_album_references() -> None:
    service = RemoteSyncValidationService(
        postgres=FakePostgresAdapter(
            tables=_base_tables(),
            orphan_results={
                "album_id": {
                    "count": 1,
                    "samples": [
                        {"asset_id": "asset-1", "album_id": "album-missing-1"},
                    ],
                }
            },
        )
    )

    result = service.run(_settings())
    finding = next(
        check for check in result.checks if check.name == "remote_album_asset_missing_albums"
    )

    assert result.overall_status == CheckStatus.FAIL
    assert finding.status == CheckStatus.FAIL
    assert finding.details["count"] == 1
    assert finding.details["samples"][0]["album_id"] == "album-missing-1"


def test_remote_sync_validation_skips_when_required_table_is_missing() -> None:
    service = RemoteSyncValidationService(
        postgres=FakePostgresAdapter(
            tables=[
                {"table_schema": "public", "table_name": "asset_entity"},
                {"table_schema": "public", "table_name": "remote_album_entity"},
            ],
        )
    )

    result = service.run(_settings())
    finding = next(
        check for check in result.checks if check.name == "remote_album_asset_missing_assets"
    )

    assert result.overall_status == CheckStatus.PASS
    assert "skipped" in result.summary.lower()
    assert finding.status == CheckStatus.SKIP
    assert "missing" in finding.message.lower()
