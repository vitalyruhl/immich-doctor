from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.db.corruption import DbCorruptionRepairService, DbCorruptionScanService


@dataclass
class FakePostgresAdapter:
    database_name: str = "immich"
    toast: dict[str, object] = field(
        default_factory=lambda: {
            "detected": False,
            "exception_text": None,
            "read_ok": True,
        }
    )
    invalid_system_indexes: list[dict[str, object]] = field(default_factory=list)
    invalid_user_indexes: list[dict[str, object]] = field(default_factory=list)
    duplicate_groups: list[dict[str, object]] = field(default_factory=list)
    duplicate_rows: list[dict[str, object]] = field(default_factory=list)
    fk_constraints: list[dict[str, object]] = field(default_factory=list)
    active_sessions: int = 0
    is_superuser: bool = True
    executed: list[str] = field(default_factory=list)

    def validate_connection(self, dsn: str, timeout_seconds: int) -> CheckResult:
        return CheckResult(
            name="postgres_connection",
            status=CheckStatus.PASS,
            message="PostgreSQL connection established.",
        )

    def fetch_current_database_name(self, dsn: str, timeout_seconds: int) -> str:
        return self.database_name

    def read_pg_statistic_toast_health(self, dsn: str, timeout_seconds: int) -> dict[str, object]:
        return dict(self.toast)

    def list_invalid_system_indexes(
        self, dsn: str, timeout_seconds: int
    ) -> list[dict[str, object]]:
        return [dict(item) for item in self.invalid_system_indexes]

    def list_invalid_user_indexes(self, dsn: str, timeout_seconds: int) -> list[dict[str, object]]:
        return [dict(item) for item in self.invalid_user_indexes]

    def list_duplicate_asset_checksum_groups(
        self,
        dsn: str,
        timeout_seconds: int,
    ) -> list[dict[str, object]]:
        return [dict(item) for item in self.duplicate_groups]

    def list_duplicate_asset_checksum_rows(
        self,
        dsn: str,
        timeout_seconds: int,
    ) -> list[dict[str, object]]:
        return [dict(item) for item in self.duplicate_rows]

    def list_asset_referencing_foreign_keys(
        self,
        dsn: str,
        timeout_seconds: int,
    ) -> list[dict[str, object]]:
        return [dict(item) for item in self.fk_constraints]

    def current_role_capabilities(self, dsn: str, timeout_seconds: int) -> dict[str, object]:
        return {
            "current_user": "postgres",
            "session_user": "postgres",
            "is_superuser": self.is_superuser,
        }

    def count_active_non_idle_sessions(self, dsn: str, timeout_seconds: int) -> int:
        return self.active_sessions

    def list_rows_by_column_values(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        table_schema: str,
        table_name: str,
        column_name: str,
        values: tuple[str, ...],
        order_columns: tuple[str, ...] = (),
    ) -> list[dict[str, object]]:
        if table_name == "memory_asset":
            return [{"assetId": value} for value in values]
        return []

    def execute_statement(self, dsn: str, timeout_seconds: int, query: str) -> None:
        self.executed.append(query)
        if "DELETE FROM pg_catalog.pg_statistic" in query:
            self.toast = {"detected": False, "exception_text": None, "read_ok": True}
        if "REINDEX SYSTEM" in query:
            self.invalid_system_indexes = []
        if "REINDEX INDEX" in query:
            index_name = query.split("REINDEX INDEX ", maxsplit=1)[1].split(";", maxsplit=1)[0]
            self.invalid_user_indexes = [
                item
                for item in self.invalid_user_indexes
                if f"{item['schema_name']}.{item['index_name']}" != index_name
            ]

    def execute_statement_composed(self, dsn: str, timeout_seconds: int, query, params=()) -> None:
        text = str(query)
        self.executed.append(text)
        if "REINDEX SYSTEM" in text:
            self.invalid_system_indexes = []
        if "REINDEX INDEX" in text:
            index_name = text.split("REINDEX INDEX ", maxsplit=1)[1].split(";", maxsplit=1)[0]
            self.invalid_user_indexes = [
                item
                for item in self.invalid_user_indexes
                if f"{item['schema_name']}.{item['index_name']}" != index_name
            ]

    def delete_rows_by_column_values_returning_all(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        table_schema: str,
        table_name: str,
        column_name: str,
        values: tuple[str, ...],
    ) -> list[dict[str, object]]:
        self.executed.append(f"DELETE {table_schema}.{table_name} {list(values)}")
        value_set = set(values)
        self.duplicate_rows = [
            row for row in self.duplicate_rows if str(row["id"]) not in value_set
        ]
        remaining_groups: list[dict[str, object]] = []
        for group in self.duplicate_groups:
            matching = [
                row
                for row in self.duplicate_rows
                if row["owner_id"] == group["owner_id"]
                and row["checksum_hex"] == group["checksum_hex"]
            ]
            if len(matching) > 1:
                remaining_groups.append(
                    {
                        **group,
                        "row_count": len(matching),
                        "excess_row_count": max(len(matching) - 1, 0),
                    }
                )
        self.duplicate_groups = remaining_groups
        return [{"id": value} for value in values]


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        manifests_path=tmp_path / "manifests",
        quarantine_path=tmp_path / "quarantine",
        postgres_dsn="postgresql://postgres:secret@localhost/immich",
    )


def test_scan_detects_toast_invalid_indexes_and_duplicate_groups(tmp_path: Path) -> None:
    adapter = FakePostgresAdapter(
        toast={
            "detected": True,
            "exception_text": "missing chunk number 0 for toast value 208628 in pg_toast_2619",
            "read_ok": False,
        },
        invalid_system_indexes=[
            {
                "schema_name": "pg_catalog",
                "index_name": "pg_statistic_relid_att_inh_index",
                "table_name": "pg_statistic",
                "indisvalid": False,
                "indisready": False,
            }
        ],
        invalid_user_indexes=[
            {
                "schema_name": "public",
                "index_name": "memory_asset_pkey",
                "table_name": "memory_asset",
                "indisvalid": False,
                "indisready": False,
            }
        ],
        duplicate_groups=[
            {
                "owner_id": "owner-1",
                "checksum_hex": "abc123",
                "row_count": 2,
                "excess_row_count": 1,
            }
        ],
        duplicate_rows=[
            {
                "id": "asset-1",
                "owner_id": "owner-1",
                "checksum_hex": "abc123",
                "original_path": "/a.jpg",
                "original_file_name": "a.jpg",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "id": "asset-2",
                "owner_id": "owner-1",
                "checksum_hex": "abc123",
                "original_path": "/b.jpg",
                "original_file_name": "b.jpg",
                "created_at": "2026-01-02T00:00:00+00:00",
                "updated_at": "2026-01-02T00:00:00+00:00",
            },
        ],
        fk_constraints=[
            {
                "constraint_name": "memory_asset_assetid_fkey",
                "referencing_schema": "public",
                "referencing_table": "memory_asset",
                "referencing_column": "assetId",
                "cascade_rule": "CASCADE",
            }
        ],
    )

    report = DbCorruptionScanService(postgres=adapter).run(_settings(tmp_path))

    assert report.overall_status == CheckStatus.FAIL
    assert report.sections[0].rows[0]["detected"] is True
    assert report.sections[1].rows[0]["index_name"] == "pg_statistic_relid_att_inh_index"
    assert report.sections[2].rows[0]["index_name"] == "memory_asset_pkey"
    assert report.sections[3].rows[0]["candidate_rows"][0]["id"] == "asset-1"


def test_preview_does_not_offer_clear_pg_statistic_when_only_user_indexes_are_invalid(
    tmp_path: Path,
) -> None:
    adapter = FakePostgresAdapter(
        invalid_user_indexes=[
            {
                "schema_name": "public",
                "index_name": "memory_asset_pkey",
                "table_name": "memory_asset",
                "indisvalid": False,
                "indisready": False,
            }
        ],
    )
    service = DbCorruptionRepairService(
        postgres=adapter,
        scan_service=DbCorruptionScanService(postgres=adapter),
    )

    report = service.preview(
        _settings(tmp_path),
        selected_delete_ids=(),
        backup_confirmed=True,
        override_backup_requirement=False,
        maintenance_mode_confirmed=True,
        system_index_duplicate_error_text=None,
        high_risk_clear_pg_statistic_approval=False,
        force_reindex_database=False,
    )

    plan_rows = report.sections[1].rows
    assert not any(row["step_key"] == "clear_pg_statistic" for row in plan_rows)
    assert any("reindex_invalid_user_index" in row["step_key"] for row in plan_rows)


def test_preview_does_not_generate_delete_sql_without_selected_ids(tmp_path: Path) -> None:
    adapter = FakePostgresAdapter(
        duplicate_groups=[
            {
                "owner_id": "owner-1",
                "checksum_hex": "abc123",
                "row_count": 2,
                "excess_row_count": 1,
            }
        ],
        duplicate_rows=[
            {
                "id": "asset-1",
                "owner_id": "owner-1",
                "checksum_hex": "abc123",
                "original_path": "/a.jpg",
                "original_file_name": "a.jpg",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "id": "asset-2",
                "owner_id": "owner-1",
                "checksum_hex": "abc123",
                "original_path": "/b.jpg",
                "original_file_name": "b.jpg",
                "created_at": "2026-01-02T00:00:00+00:00",
                "updated_at": "2026-01-02T00:00:00+00:00",
            },
        ],
    )
    service = DbCorruptionRepairService(
        postgres=adapter,
        scan_service=DbCorruptionScanService(postgres=adapter),
    )

    report = service.preview(
        _settings(tmp_path),
        selected_delete_ids=(),
        backup_confirmed=True,
        override_backup_requirement=False,
        maintenance_mode_confirmed=True,
        system_index_duplicate_error_text=None,
        high_risk_clear_pg_statistic_approval=False,
        force_reindex_database=False,
    )

    plan_rows = report.sections[1].rows
    assert any(row["step_key"] == "present_duplicate_asset_groups" for row in plan_rows)
    assert not any(row["step_key"] == "delete_duplicate_assets" for row in plan_rows)


def test_apply_executes_previewed_steps_and_produces_before_after_diff(tmp_path: Path) -> None:
    adapter = FakePostgresAdapter(
        toast={
            "detected": True,
            "exception_text": "missing chunk number 0 for toast value 208628 in pg_toast_2619",
            "read_ok": False,
        },
        invalid_system_indexes=[
            {
                "schema_name": "pg_catalog",
                "index_name": "pg_statistic_relid_att_inh_index",
                "table_name": "pg_statistic",
                "indisvalid": False,
                "indisready": False,
            }
        ],
        invalid_user_indexes=[
            {
                "schema_name": "public",
                "index_name": "memory_asset_pkey",
                "table_name": "memory_asset",
                "indisvalid": False,
                "indisready": False,
            }
        ],
        duplicate_groups=[
            {
                "owner_id": "owner-1",
                "checksum_hex": "abc123",
                "row_count": 2,
                "excess_row_count": 1,
            }
        ],
        duplicate_rows=[
            {
                "id": "asset-1",
                "owner_id": "owner-1",
                "checksum_hex": "abc123",
                "original_path": "/a.jpg",
                "original_file_name": "a.jpg",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "id": "asset-2",
                "owner_id": "owner-1",
                "checksum_hex": "abc123",
                "original_path": "/b.jpg",
                "original_file_name": "b.jpg",
                "created_at": "2026-01-02T00:00:00+00:00",
                "updated_at": "2026-01-02T00:00:00+00:00",
            },
        ],
        fk_constraints=[
            {
                "constraint_name": "memory_asset_assetid_fkey",
                "referencing_schema": "public",
                "referencing_table": "memory_asset",
                "referencing_column": "assetId",
                "cascade_rule": "CASCADE",
            }
        ],
    )
    service = DbCorruptionRepairService(
        postgres=adapter,
        scan_service=DbCorruptionScanService(postgres=adapter),
    )

    preview = service.preview(
        _settings(tmp_path),
        selected_delete_ids=("asset-2",),
        backup_confirmed=True,
        override_backup_requirement=False,
        maintenance_mode_confirmed=True,
        system_index_duplicate_error_text="duplicate key in pg_statistic_relid_att_inh_index",
        high_risk_clear_pg_statistic_approval=True,
        force_reindex_database=False,
    )
    repair_run_id = str(preview.metadata["repair_run_id"])

    apply_report = service.apply(_settings(tmp_path), repair_run_id=repair_run_id)

    assert apply_report.overall_status in {CheckStatus.PASS, CheckStatus.WARN}
    executed = apply_report.sections[1].rows
    assert any(
        row["step_key"] == "clear_pg_statistic" and row["status"] == "applied" for row in executed
    )
    assert any(
        row["step_key"] == "delete_duplicate_assets" and row["status"] == "applied"
        for row in executed
    )
    diff_rows = apply_report.sections[2].rows
    assert any(row["metric"] == "invalid_system_indexes" and row["after"] == 0 for row in diff_rows)
    assert any(row["metric"] == "duplicate_asset_groups" and row["after"] == 0 for row in diff_rows)
