from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from time import sleep

from immich_doctor.consistency.missing_asset_models import (
    MissingAssetBlockingSeverity,
    MissingAssetOperationStatus,
    MissingAssetReferenceStatus,
    MissingAssetRepairBlockerType,
    RepairReadinessStatus,
)
from immich_doctor.consistency.missing_asset_service import MissingAssetReferenceService
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus


@dataclass
class _FakePostgres:
    connection_status: CheckStatus = CheckStatus.PASS
    tables: list[dict[str, object]] = field(default_factory=list)
    columns_by_table: dict[tuple[str, str], list[dict[str, object]]] = field(default_factory=dict)
    foreign_keys_by_table: dict[tuple[str, str], list[dict[str, object]]] = field(
        default_factory=dict
    )
    rows_by_table: dict[tuple[str, str], list[dict[str, object]]] = field(default_factory=dict)

    def validate_connection(self, dsn: str, timeout_seconds: int) -> CheckResult:
        return CheckResult(
            name="postgres_connection",
            status=self.connection_status,
            message="PostgreSQL connection established.",
        )

    def list_tables(self, dsn: str, timeout_seconds: int) -> list[dict[str, object]]:
        return list(self.tables)

    def list_columns(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        table_schema: str,
        table_name: str,
    ) -> list[dict[str, object]]:
        return list(self.columns_by_table.get((table_schema, table_name), []))

    def list_foreign_keys(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        table_schema: str,
        table_name: str,
    ) -> list[dict[str, object]]:
        return list(self.foreign_keys_by_table.get((table_schema, table_name), []))

    def list_assets_for_missing_references(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        limit: int,
        offset: int,
        optional_columns: tuple[str, ...] = (),
    ) -> list[dict[str, object]]:
        rows = self.rows_by_table.get(("public", "asset"), [])[offset : offset + limit]
        selected = []
        for row in rows:
            item = {"id": row["id"], "type": row["type"], "originalPath": row["originalPath"]}
            for column in optional_columns:
                item[column] = row.get(column)
            selected.append(item)
        return selected

    def count_assets(self, dsn: str, timeout_seconds: int) -> int:
        return len(self.rows_by_table.get(("public", "asset"), []))

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
        rows = [
            dict(row)
            for row in self.rows_by_table.get((table_schema, table_name), [])
            if str(row.get(column_name)) in values
        ]
        if order_columns:
            rows.sort(key=lambda row: tuple(str(row.get(column)) for column in order_columns))
        return rows

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
        deleted: list[dict[str, object]] = []
        remaining: list[dict[str, object]] = []
        for row in self.rows_by_table.get((table_schema, table_name), []):
            if str(row.get(column_name)) in values:
                deleted.append(dict(row))
            else:
                remaining.append(row)
        self.rows_by_table[(table_schema, table_name)] = remaining
        return deleted

    def insert_rows(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        table_schema: str,
        table_name: str,
        rows: list[dict[str, object]],
    ) -> int:
        existing = self.rows_by_table.setdefault((table_schema, table_name), [])
        existing.extend(dict(row) for row in rows)
        return len(rows)

    def delete_asset_reference_records(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        asset_id: str,
        relations: tuple[dict[str, str], ...],
    ) -> list[dict[str, object]]:
        deleted: list[dict[str, object]] = []
        for relation in relations:
            rows = self.delete_rows_by_column_values_returning_all(
                dsn,
                timeout_seconds,
                table_schema=relation["table_schema"],
                table_name=relation["table_name"],
                column_name=relation["column_name"],
                values=(asset_id,),
            )
            if rows:
                deleted.append(
                    {
                        "table": f"{relation['table_schema']}.{relation['table_name']}",
                        "deleted_count": len(rows),
                    }
                )
        asset_rows = self.delete_rows_by_column_values_returning_all(
            dsn,
            timeout_seconds,
            table_schema="public",
            table_name="asset",
            column_name="id",
            values=(asset_id,),
        )
        if asset_rows:
            deleted.append({"table": "public.asset", "deleted_count": len(asset_rows)})
        return deleted

    def restore_asset_reference_records(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        records: list[dict[str, object]],
    ) -> int:
        inserted = 0
        for record in records:
            schema, table = str(record["table"]).split(".", maxsplit=1)
            inserted += self.insert_rows(
                dsn,
                timeout_seconds,
                table_schema=schema,
                table_name=table,
                rows=list(record.get("rows", [])),
            )
        return inserted


class _FakeFilesystem:
    def __init__(self, states: dict[str, str]) -> None:
        self.states = {key.replace("\\", "/"): value for key, value in states.items()}

    def stat_path(self, path: Path):
        state = self.states.get(str(path).replace("\\", "/"), "missing")
        if state == "missing":
            raise FileNotFoundError(str(path))
        if state == "denied":
            raise PermissionError(str(path))
        if state == "unreadable":
            raise OSError("cannot inspect")
        return object()

    def read_probe(self, path: Path, size: int = 8192) -> bytes:
        state = self.states.get(str(path).replace("\\", "/"), "missing")
        if state == "missing":
            raise FileNotFoundError(str(path))
        if state == "denied":
            raise PermissionError(str(path))
        if state == "unreadable":
            raise OSError("cannot inspect")
        return b"probe"


class _TrackingFilesystem(_FakeFilesystem):
    def __init__(self, states: dict[str, str], *, delay_seconds: float = 0.02) -> None:
        super().__init__(states)
        self.delay_seconds = delay_seconds
        self._lock = Lock()
        self.active_operations = 0
        self.max_active_operations = 0

    def stat_path(self, path: Path):
        with self._lock:
            self.active_operations += 1
            self.max_active_operations = max(self.max_active_operations, self.active_operations)
        try:
            sleep(self.delay_seconds)
            return super().stat_path(path)
        finally:
            with self._lock:
                self.active_operations -= 1


class _ExplodingFilesystem(_FakeFilesystem):
    def __init__(self, states: dict[str, str], *, exploding_paths: set[str]) -> None:
        super().__init__(states)
        self.exploding_paths = {item.replace("\\", "/") for item in exploding_paths}

    def stat_path(self, path: Path):
        normalized = str(path).replace("\\", "/")
        if normalized in self.exploding_paths:
            raise RuntimeError("worker exploded")
        return super().stat_path(path)


class _RecordingExecutor:
    def __init__(self, *, max_workers: int, delegate_factory) -> None:
        self.max_workers = max_workers
        self.delegate = delegate_factory(max_workers=max_workers)

    def __enter__(self):
        self.delegate.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self.delegate.__exit__(exc_type, exc, tb)

    def submit(self, fn, *args, **kwargs):
        return self.delegate.submit(fn, *args, **kwargs)


def _settings(
    tmp_path: Path,
    *,
    immich_library_root: Path | None = None,
    missing_asset_scan_concurrency: int = 20,
) -> AppSettings:
    return AppSettings(
        _env_file=None,
        DB_HOST="postgres",
        DB_NAME="immich",
        DB_USER="immich",
        DB_PASSWORD="secret",
        immich_library_root=immich_library_root,
        MISSING_ASSET_SCAN_CONCURRENCY=missing_asset_scan_concurrency,
        MANIFESTS_PATH=tmp_path / "manifests",
        QUARANTINE_PATH=tmp_path / "quarantine",
    )


def _tables() -> list[dict[str, object]]:
    return [
        {"table_schema": "public", "table_name": "asset"},
        {"table_schema": "public", "table_name": "asset_file"},
        {"table_schema": "public", "table_name": "album_asset"},
        {"table_schema": "public", "table_name": "asset_job_status"},
    ]


def _columns() -> dict[tuple[str, str], list[dict[str, object]]]:
    values = {
        ("public", "asset"): ["id", "type", "originalPath", "createdAt", "ownerId"],
        ("public", "asset_file"): ["id", "assetId", "type", "path"],
        ("public", "album_asset"): ["albumId", "assetsId"],
        ("public", "asset_job_status"): ["assetId", "metadataExtractedAt"],
    }
    return {
        key: [
            {"table_schema": key[0], "table_name": key[1], "column_name": column}
            for column in columns
        ]
        for key, columns in values.items()
    }


def _foreign_keys() -> dict[tuple[str, str], list[dict[str, object]]]:
    return {
        ("public", "asset_file"): [
            {
                "constraint_name": "fk_asset_file_asset",
                "referenced_table_schema": "public",
                "referenced_table_name": "asset",
                "delete_action": "CASCADE",
                "column_names": ["assetId"],
                "referenced_column_names": ["id"],
            }
        ],
        ("public", "album_asset"): [
            {
                "constraint_name": "fk_album_asset_asset",
                "referenced_table_schema": "public",
                "referenced_table_name": "asset",
                "delete_action": "CASCADE",
                "column_names": ["assetsId"],
                "referenced_column_names": ["id"],
            }
        ],
        ("public", "asset_job_status"): [
            {
                "constraint_name": "fk_asset_job_status_asset",
                "referenced_table_schema": "public",
                "referenced_table_name": "asset",
                "delete_action": "CASCADE",
                "column_names": ["assetId"],
                "referenced_column_names": ["id"],
            }
        ],
    }


def _rows() -> dict[tuple[str, str], list[dict[str, object]]]:
    return {
        ("public", "asset"): [
            {
                "id": "asset-missing",
                "type": "image",
                "originalPath": "C:/library/missing.jpg",
                "createdAt": "2026-03-28T10:00:00+00:00",
                "ownerId": "user-1",
            },
            {
                "id": "asset-ok",
                "type": "image",
                "originalPath": "C:/library/ok.jpg",
                "createdAt": "2026-03-28T10:05:00+00:00",
                "ownerId": "user-1",
            },
        ],
        ("public", "asset_file"): [
            {"id": "file-1", "assetId": "asset-missing", "type": "preview", "path": "/thumb.jpg"}
        ],
        ("public", "album_asset"): [{"albumId": "album-1", "assetsId": "asset-missing"}],
        ("public", "asset_job_status"): [{"assetId": "asset-missing", "metadataExtractedAt": None}],
    }


def test_scan_detects_missing_asset_reference(tmp_path: Path) -> None:
    service = MissingAssetReferenceService(
        postgres=_FakePostgres(
            tables=_tables(),
            columns_by_table=_columns(),
            foreign_keys_by_table=_foreign_keys(),
            rows_by_table=_rows(),
        ),
        filesystem=_FakeFilesystem(
            {"C:/library/missing.jpg": "missing", "C:/library/ok.jpg": "present"}
        ),
    )

    result = service.scan(_settings(tmp_path))

    assert result.findings[0].asset_id == "asset-missing"
    assert result.findings[0].status == MissingAssetReferenceStatus.MISSING_ON_DISK
    assert result.findings[0].resolved_physical_path.replace("\\", "/") == "C:/library/missing.jpg"
    assert result.findings[0].repair_readiness == RepairReadinessStatus.READY
    assert result.findings[0].repair_blocker_details == ()
    assert result.metadata["supportedScope"]["scanBlockers"] == []
    assert result.metadata["supportedScope"]["repairCoveredDependencyTables"] == [
        "public.album_asset",
        "public.asset_file",
        "public.asset_job_status",
    ]


def test_scan_all_walks_entire_asset_set_and_reports_progress(tmp_path: Path) -> None:
    progress_updates: list[dict[str, object]] = []
    service = MissingAssetReferenceService(
        postgres=_FakePostgres(
            tables=_tables(),
            columns_by_table=_columns(),
            foreign_keys_by_table=_foreign_keys(),
            rows_by_table=_rows(),
        ),
        filesystem=_FakeFilesystem(
            {"C:/library/missing.jpg": "missing", "C:/library/ok.jpg": "present"}
        ),
        batch_limit=1,
    )

    result = service.scan_all(
        _settings(tmp_path),
        progress_callback=lambda payload: progress_updates.append(dict(payload)),
    )

    assert result.metadata["scannedAssetCount"] == 2
    assert result.metadata["totalAssetCount"] == 2
    assert result.metadata["findingCount"] == 1
    assert [finding.asset_id for finding in result.findings] == ["asset-missing", "asset-ok"]
    assert progress_updates[-1]["scanned_asset_count"] == 2
    assert progress_updates[-1]["finding_count"] == 1
    assert progress_updates[-1]["total_asset_count"] == 2


def test_parallel_scan_matches_sequential_results(tmp_path: Path) -> None:
    rows_by_table = {
        ("public", "asset"): [
            {
                "id": f"asset-{index:02d}",
                "type": "image",
                "originalPath": f"C:/library/asset-{index:02d}.jpg",
                "createdAt": "2026-03-28T10:00:00+00:00",
                "ownerId": "user-1",
            }
            for index in range(6)
        ]
    }
    states = {
        "C:/library/asset-00.jpg": "missing",
        "C:/library/asset-01.jpg": "present",
        "C:/library/asset-02.jpg": "denied",
        "C:/library/asset-03.jpg": "present",
        "C:/library/asset-04.jpg": "missing",
        "C:/library/asset-05.jpg": "unreadable",
    }
    postgres = _FakePostgres(
        tables=_tables(),
        columns_by_table=_columns(),
        foreign_keys_by_table=_foreign_keys(),
        rows_by_table=rows_by_table,
    )
    sequential = MissingAssetReferenceService(
        postgres=postgres,
        filesystem=_FakeFilesystem(states),
        batch_limit=3,
    ).scan_all(_settings(tmp_path, missing_asset_scan_concurrency=1))
    parallel = MissingAssetReferenceService(
        postgres=_FakePostgres(
            tables=_tables(),
            columns_by_table=_columns(),
            foreign_keys_by_table=_foreign_keys(),
            rows_by_table=rows_by_table,
        ),
        filesystem=_FakeFilesystem(states),
        batch_limit=3,
    ).scan_all(_settings(tmp_path, missing_asset_scan_concurrency=4))

    assert [finding.asset_id for finding in parallel.findings] == [
        finding.asset_id for finding in sequential.findings
    ]
    assert [finding.status for finding in parallel.findings] == [
        finding.status for finding in sequential.findings
    ]
    assert parallel.metadata["findingCount"] == sequential.metadata["findingCount"]


def test_scan_respects_configured_concurrency_limit(tmp_path: Path) -> None:
    recorded_max_workers: list[int] = []

    def recording_executor_factory(*, max_workers: int):
        recorded_max_workers.append(max_workers)
        return _RecordingExecutor(max_workers=max_workers, delegate_factory=ThreadPoolExecutor)

    service = MissingAssetReferenceService(
        postgres=_FakePostgres(
            tables=_tables(),
            columns_by_table=_columns(),
            foreign_keys_by_table=_foreign_keys(),
            rows_by_table=_rows(),
        ),
        filesystem=_FakeFilesystem(
            {"C:/library/missing.jpg": "missing", "C:/library/ok.jpg": "present"}
        ),
        executor_factory=recording_executor_factory,
    )

    service.scan_all(_settings(tmp_path, missing_asset_scan_concurrency=7))

    assert recorded_max_workers == [7]


def test_parallel_scan_progress_counters_stay_correct(tmp_path: Path) -> None:
    progress_updates: list[dict[str, object]] = []
    filesystem = _TrackingFilesystem(
        {
            "C:/library/missing.jpg": "missing",
            "C:/library/ok.jpg": "present",
        }
    )
    service = MissingAssetReferenceService(
        postgres=_FakePostgres(
            tables=_tables(),
            columns_by_table=_columns(),
            foreign_keys_by_table=_foreign_keys(),
            rows_by_table=_rows(),
        ),
        filesystem=filesystem,
        batch_limit=2,
    )

    result = service.scan_all(
        _settings(tmp_path, missing_asset_scan_concurrency=2),
        progress_callback=lambda payload: progress_updates.append(dict(payload)),
    )

    assert result.metadata["scannedAssetCount"] == 2
    assert result.metadata["findingCount"] == 1
    assert progress_updates[0]["scanned_asset_count"] == 0
    assert progress_updates[-1]["scanned_asset_count"] == 2
    assert progress_updates[-1]["finding_count"] == 1
    assert filesystem.max_active_operations <= 2


def test_worker_failure_is_reported_as_unreadable_without_aborting_scan(tmp_path: Path) -> None:
    rows_by_table = {
        ("public", "asset"): [
            {
                "id": "asset-boom",
                "type": "image",
                "originalPath": "C:/library/boom.jpg",
                "createdAt": "2026-03-28T10:00:00+00:00",
                "ownerId": "user-1",
            },
            {
                "id": "asset-ok",
                "type": "image",
                "originalPath": "C:/library/ok.jpg",
                "createdAt": "2026-03-28T10:05:00+00:00",
                "ownerId": "user-1",
            },
        ]
    }
    service = MissingAssetReferenceService(
        postgres=_FakePostgres(
            tables=_tables(),
            columns_by_table=_columns(),
            foreign_keys_by_table=_foreign_keys(),
            rows_by_table=rows_by_table,
        ),
        filesystem=_ExplodingFilesystem(
            {"C:/library/boom.jpg": "present", "C:/library/ok.jpg": "present"},
            exploding_paths={"C:/library/boom.jpg"},
        ),
        batch_limit=2,
    )

    result = service.scan_all(_settings(tmp_path, missing_asset_scan_concurrency=2))

    assert [finding.asset_id for finding in result.findings] == ["asset-boom", "asset-ok"]
    assert result.findings[0].status == MissingAssetReferenceStatus.UNREADABLE_PATH
    assert result.findings[1].status == MissingAssetReferenceStatus.PRESENT
    assert result.metadata["findingCount"] == 1


def test_scan_keeps_directly_accessible_logical_original_path(tmp_path: Path) -> None:
    direct_path = tmp_path / "storage" / "upload" / "user" / "aa" / "bb" / "asset.jpg"
    postgres = _FakePostgres(
        tables=_tables(),
        columns_by_table=_columns(),
        foreign_keys_by_table=_foreign_keys(),
        rows_by_table={
            ("public", "asset"): [
                {
                    "id": "asset-direct",
                    "type": "image",
                    "originalPath": str(direct_path),
                    "createdAt": "2026-03-28T10:00:00+00:00",
                    "ownerId": "user-1",
                }
            ]
        },
    )
    service = MissingAssetReferenceService(
        postgres=postgres,
        filesystem=_FakeFilesystem({str(direct_path): "present"}),
    )

    result = service.scan(_settings(tmp_path, immich_library_root=tmp_path / "storage"))

    assert result.findings[0].status == MissingAssetReferenceStatus.PRESENT
    assert result.findings[0].logical_path == str(direct_path)
    assert result.findings[0].resolved_physical_path == str(direct_path)


def test_scan_resolves_immich_logical_path_via_library_root(tmp_path: Path) -> None:
    logical_path = "/usr/src/app/upload/upload/user/aa/bb/asset.jpg"
    resolved_path = tmp_path / "storage" / "upload" / "user" / "aa" / "bb" / "asset.jpg"
    postgres = _FakePostgres(
        tables=_tables(),
        columns_by_table=_columns(),
        foreign_keys_by_table=_foreign_keys(),
        rows_by_table={
            ("public", "asset"): [
                {
                    "id": "asset-mapped",
                    "type": "image",
                    "originalPath": logical_path,
                    "createdAt": "2026-03-28T10:00:00+00:00",
                    "ownerId": "user-1",
                }
            ]
        },
    )
    service = MissingAssetReferenceService(
        postgres=postgres,
        filesystem=_FakeFilesystem(
            {
                logical_path: "missing",
                str(resolved_path): "present",
            }
        ),
    )

    result = service.scan(_settings(tmp_path, immich_library_root=tmp_path / "storage"))

    assert result.findings[0].status == MissingAssetReferenceStatus.PRESENT
    assert result.findings[0].logical_path == logical_path
    assert result.findings[0].resolved_physical_path == str(resolved_path)


def test_scan_reports_missing_only_after_mapped_path_check_fails(tmp_path: Path) -> None:
    logical_path = "/usr/src/app/upload/upload/user/aa/bb/asset.jpg"
    resolved_path = tmp_path / "storage" / "upload" / "user" / "aa" / "bb" / "asset.jpg"
    postgres = _FakePostgres(
        tables=_tables(),
        columns_by_table=_columns(),
        foreign_keys_by_table=_foreign_keys(),
        rows_by_table={
            ("public", "asset"): [
                {
                    "id": "asset-mapped-missing",
                    "type": "image",
                    "originalPath": logical_path,
                    "createdAt": "2026-03-28T10:00:00+00:00",
                    "ownerId": "user-1",
                }
            ]
        },
    )
    service = MissingAssetReferenceService(
        postgres=postgres,
        filesystem=_FakeFilesystem(
            {
                logical_path: "missing",
                str(resolved_path): "missing",
            }
        ),
    )

    result = service.scan(_settings(tmp_path, immich_library_root=tmp_path / "storage"))

    assert result.findings[0].status == MissingAssetReferenceStatus.MISSING_ON_DISK
    assert result.findings[0].logical_path == logical_path
    assert result.findings[0].resolved_physical_path == str(resolved_path)


def test_scan_blocks_repair_for_unsupported_asset_dependency(tmp_path: Path) -> None:
    postgres = _FakePostgres(
        tables=[*_tables(), {"table_schema": "public", "table_name": "person_asset"}],
        columns_by_table=_columns(),
        foreign_keys_by_table={
            **_foreign_keys(),
            ("public", "person_asset"): [
                {
                    "constraint_name": "fk_person_asset_asset",
                    "referenced_table_schema": "public",
                    "referenced_table_name": "asset",
                    "column_names": ["assetId"],
                    "referenced_column_names": ["id"],
                }
            ],
        },
        rows_by_table=_rows(),
    )
    service = MissingAssetReferenceService(
        postgres=postgres,
        filesystem=_FakeFilesystem(
            {"C:/library/missing.jpg": "missing", "C:/library/ok.jpg": "present"}
        ),
    )

    result = service.scan(_settings(tmp_path))

    assert result.findings[0].repair_readiness == RepairReadinessStatus.BLOCKED
    assert "public.person_asset blocks apply" in result.findings[0].repair_blockers[0]
    blocker = result.findings[0].repair_blocker_details[0]
    assert blocker.blocker_code == "asset_dependency:public.person_asset"
    assert blocker.blocker_type == MissingAssetRepairBlockerType.SCHEMA
    assert blocker.summary == "public.person_asset blocks apply: unknown"
    assert blocker.details["blocks_apply"] is True
    assert blocker.details["coverage_status"] == "unsupported_blocking"
    assert blocker.details["risk_class"] == "unknown"
    assert blocker.affected_tables == ("public.person_asset",)
    assert blocker.repair_covered_tables == (
        "public.album_asset",
        "public.asset_file",
        "public.asset_job_status",
    )
    assert blocker.blocking_severity == MissingAssetBlockingSeverity.ERROR
    assert blocker.is_repairable is False
    assert result.metadata["blockingIssues"] == ["public.person_asset blocks apply: unknown"]
    assert result.metadata["supportedScope"]["applyBlocked"] is True
    assert (
        result.metadata["supportedScope"]["assetDependencies"][-1]["table"] == "public.person_asset"
    )
    assert result.metadata["supportedScope"]["scanBlockers"] == [blocker.to_dict()]


def test_scan_reports_semantic_set_null_blocker(tmp_path: Path) -> None:
    postgres = _FakePostgres(
        tables=[*_tables(), {"table_schema": "public", "table_name": "album"}],
        columns_by_table={
            **_columns(),
            ("public", "album"): [
                {"table_schema": "public", "table_name": "album", "column_name": "id"},
                {
                    "table_schema": "public",
                    "table_name": "album",
                    "column_name": "albumThumbnailAssetId",
                },
            ],
        },
        foreign_keys_by_table={
            **_foreign_keys(),
            ("public", "album"): [
                {
                    "constraint_name": "album_albumThumbnailAssetId_fkey",
                    "referenced_table_schema": "public",
                    "referenced_table_name": "asset",
                    "delete_action": "SET NULL",
                    "column_names": ["albumThumbnailAssetId"],
                    "referenced_column_names": ["id"],
                }
            ],
        },
        rows_by_table=_rows(),
    )
    service = MissingAssetReferenceService(
        postgres=postgres,
        filesystem=_FakeFilesystem(
            {"C:/library/missing.jpg": "missing", "C:/library/ok.jpg": "present"}
        ),
    )

    result = service.scan(_settings(tmp_path))

    blocker = result.findings[0].repair_blocker_details[0]
    assert blocker.summary == "public.album blocks apply: set_null_mutation"
    assert blocker.details["delete_action"] == "SET NULL"
    assert blocker.details["coverage_status"] == "covered_blocking_for_apply"
    assert blocker.details["risk_class"] == "set_null_mutation"
    assert result.metadata["blockingIssues"] == ["public.album blocks apply: set_null_mutation"]


def test_preview_and_apply_create_restore_point_and_delete_rows(tmp_path: Path) -> None:
    postgres = _FakePostgres(
        tables=_tables(),
        columns_by_table=_columns(),
        foreign_keys_by_table=_foreign_keys(),
        rows_by_table=_rows(),
    )
    service = MissingAssetReferenceService(
        postgres=postgres,
        filesystem=_FakeFilesystem(
            {"C:/library/missing.jpg": "missing", "C:/library/ok.jpg": "present"}
        ),
    )
    settings = _settings(tmp_path)

    preview = service.preview(settings, asset_ids=("asset-missing",), select_all=False)
    apply_result = service.apply(settings, repair_run_id=preview.repair_run_id)

    assert apply_result.items[0].status == MissingAssetOperationStatus.APPLIED
    assert [row["id"] for row in postgres.rows_by_table[("public", "asset")]] == ["asset-ok"]
    assert service.list_restore_points(settings).items[0].asset_id == "asset-missing"


def test_apply_stops_on_drift(tmp_path: Path) -> None:
    postgres = _FakePostgres(
        tables=_tables(),
        columns_by_table=_columns(),
        foreign_keys_by_table=_foreign_keys(),
        rows_by_table=_rows(),
    )
    filesystem = _FakeFilesystem(
        {"C:/library/missing.jpg": "missing", "C:/library/ok.jpg": "present"}
    )
    service = MissingAssetReferenceService(postgres=postgres, filesystem=filesystem)
    settings = _settings(tmp_path)

    preview = service.preview(settings, asset_ids=("asset-missing",), select_all=False)
    filesystem.states["C:/library/missing.jpg"] = "present"
    result = service.apply(settings, repair_run_id=preview.repair_run_id)

    assert result.summary.startswith("Apply stopped")
    assert postgres.rows_by_table[("public", "asset")][0]["id"] == "asset-missing"


def test_restore_reinserts_deleted_rows(tmp_path: Path) -> None:
    postgres = _FakePostgres(
        tables=_tables(),
        columns_by_table=_columns(),
        foreign_keys_by_table=_foreign_keys(),
        rows_by_table=_rows(),
    )
    service = MissingAssetReferenceService(
        postgres=postgres,
        filesystem=_FakeFilesystem(
            {"C:/library/missing.jpg": "missing", "C:/library/ok.jpg": "present"}
        ),
    )
    settings = _settings(tmp_path)

    preview = service.preview(settings, asset_ids=("asset-missing",), select_all=False)
    service.apply(settings, repair_run_id=preview.repair_run_id)
    restore_point = service.list_restore_points(settings).items[0]
    restore_result = service.restore(
        settings,
        restore_point_ids=(restore_point.restore_point_id,),
        restore_all=False,
    )

    assert restore_result.items[0].status == MissingAssetOperationStatus.RESTORED
    assert any(row["id"] == "asset-missing" for row in postgres.rows_by_table[("public", "asset")])


def test_delete_restore_points_removes_manifest_entries(tmp_path: Path) -> None:
    postgres = _FakePostgres(
        tables=_tables(),
        columns_by_table=_columns(),
        foreign_keys_by_table=_foreign_keys(),
        rows_by_table=_rows(),
    )
    service = MissingAssetReferenceService(
        postgres=postgres,
        filesystem=_FakeFilesystem(
            {"C:/library/missing.jpg": "missing", "C:/library/ok.jpg": "present"}
        ),
    )
    settings = _settings(tmp_path)

    preview = service.preview(settings, asset_ids=("asset-missing",), select_all=False)
    service.apply(settings, repair_run_id=preview.repair_run_id)
    restore_point = service.list_restore_points(settings).items[0]

    delete_result = service.delete_restore_points(
        settings,
        restore_point_ids=(restore_point.restore_point_id,),
        delete_all=False,
    )

    assert delete_result.items[0]["status"] == "deleted"
    assert service.list_restore_points(settings).items == []
