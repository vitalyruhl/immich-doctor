from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.catalog.service import CatalogRootRegistry
from immich_doctor.catalog.store import CatalogStore
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import (
    CheckResult,
    CheckStatus,
    ValidationReport,
    ValidationSection,
)
from immich_doctor.storage.path_mapping import ImmichStoragePathResolver

_ZERO_BYTE_SECTION = "ZERO_BYTE_FILES"
_DB_MISSING_SECTION = "DB_ORIGINALS_MISSING_ON_STORAGE"
_STORAGE_MISSING_SECTION = "STORAGE_ORIGINALS_MISSING_IN_DB"
_ORPHAN_SECTION = "ORPHAN_DERIVATIVES_WITHOUT_ORIGINAL"
_UNMAPPED_SECTION = "UNMAPPED_DATABASE_PATHS"
_SOURCE_ROOT_SLUG = "uploads"
_DERIVATIVE_ROOT_SLUGS = {"thumbs", "profile", "video"}
_SIDECAR_EXTENSION = ".xmp"
_DEFAULT_SAMPLE_LIMIT = 200


def _truthy_path(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _section_status(rows: list[dict[str, object]]) -> CheckStatus:
    return CheckStatus.FAIL if rows else CheckStatus.PASS


@dataclass(slots=True)
class CatalogConsistencyValidationService:
    store: CatalogStore = field(default_factory=CatalogStore)
    registry: CatalogRootRegistry = field(default_factory=CatalogRootRegistry)
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)
    sample_limit: int = _DEFAULT_SAMPLE_LIMIT

    def run(
        self,
        settings: AppSettings,
        *,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> ValidationReport:
        synced_roots = self.registry.sync(settings)
        latest_snapshots = self.store.list_latest_snapshots(settings)
        snapshot_by_slug = {
            str(row["root_slug"]): row
            for row in latest_snapshots
            if row.get("snapshot_id") is not None
        }
        checks = [
            CheckResult(
                name="catalog_configured_roots",
                status=CheckStatus.PASS if synced_roots else CheckStatus.FAIL,
                message=(
                    f"Found {len(synced_roots)} configured catalog roots."
                    if synced_roots
                    else "No catalog roots are configured."
                ),
            )
        ]
        if _SOURCE_ROOT_SLUG not in snapshot_by_slug:
            checks.append(
                CheckResult(
                    name="catalog_source_snapshot",
                    status=CheckStatus.FAIL,
                    message=(
                        "No committed uploads catalog snapshot exists yet. "
                        "Run a catalog scan first."
                    ),
                )
            )
            return ValidationReport(
                domain="consistency.catalog",
                action="validate",
                summary=("Catalog-backed consistency is waiting for a committed uploads snapshot."),
                checks=checks,
                metadata={
                    "configuredRoots": [row["slug"] for row in synced_roots],
                    "latestSnapshots": latest_snapshots,
                },
                recommendations=[
                    "Run a catalog scan from the Storage page before starting "
                    "the consistency validation.",
                ],
            )

        dsn = settings.postgres_dsn_value()
        if not dsn:
            checks.append(
                CheckResult(
                    name="postgres_connection",
                    status=CheckStatus.FAIL,
                    message="Database DSN is not configured.",
                )
            )
            return ValidationReport(
                domain="consistency.catalog",
                action="validate",
                summary=(
                    "Catalog-backed consistency failed because database access is not configured."
                ),
                checks=checks,
                metadata={"latestSnapshots": latest_snapshots},
            )

        timeout = settings.postgres_connect_timeout_seconds
        connection_check = self.postgres.validate_connection(dsn, timeout)
        checks.append(connection_check)
        if connection_check.status == CheckStatus.FAIL:
            return ValidationReport(
                domain="consistency.catalog",
                action="validate",
                summary=(
                    "Catalog-backed consistency failed because PostgreSQL could not be reached."
                ),
                checks=checks,
                metadata={"latestSnapshots": latest_snapshots},
            )

        resolver = ImmichStoragePathResolver(settings)
        zero_byte_rows = self.store.list_zero_byte_files(settings, limit=self.sample_limit)
        latest_files = self.store.list_latest_snapshot_files(settings)
        files_by_root: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in latest_files:
            files_by_root[str(row["root_slug"])].append(row)

        uploads_rows = files_by_root.get(_SOURCE_ROOT_SLUG, [])
        uploads_index = {str(row["relative_path"]) for row in uploads_rows}
        source_only_rows = [row for row in uploads_rows if self._is_original_candidate(row)]
        derivative_indexes = {
            slug: {str(row["relative_path"]) for row in rows}
            for slug, rows in files_by_root.items()
            if slug in _DERIVATIVE_ROOT_SLUGS or slug == _SOURCE_ROOT_SLUG
        }

        if progress_callback is not None:
            progress_callback(
                {
                    "phase": "catalog",
                    "current": 1,
                    "total": 4,
                    "percent": 25.0,
                    "message": "Loaded persisted catalog snapshots.",
                    "filesIndexed": len(latest_files),
                }
            )

        asset_rows = self.postgres.list_all_assets_for_catalog_consistency(dsn, timeout)
        asset_file_rows = self.postgres.list_all_asset_files_for_catalog_consistency(
            dsn,
            timeout,
        )

        db_missing_rows: list[dict[str, object]] = []
        storage_missing_rows: list[dict[str, object]] = []
        orphan_rows: list[dict[str, object]] = []
        unmapped_rows: list[dict[str, object]] = []
        db_original_index: set[str] = set()
        original_by_asset: dict[str, str] = {}
        derivative_rows_by_asset: dict[str, list[dict[str, object]]] = defaultdict(list)

        for row in asset_file_rows:
            derivative_rows_by_asset[str(row["assetId"])].append(row)

        for index, asset in enumerate(asset_rows, start=1):
            asset_id = str(asset["id"])
            original_path = _truthy_path(asset.get("originalPath"))
            if not original_path:
                continue

            resolved_original = resolver.resolve(original_path)
            if resolved_original is None and resolver.looks_like_legacy_immich_path(original_path):
                unmapped_rows.append(
                    {
                        "asset_id": asset_id,
                        "path_kind": "original",
                        "database_path": original_path,
                    }
                )
                continue

            if resolved_original is not None and resolved_original.root_slug == _SOURCE_ROOT_SLUG:
                db_original_index.add(resolved_original.relative_path)
                original_by_asset[asset_id] = resolved_original.relative_path
                if resolved_original.relative_path not in uploads_index:
                    db_missing_rows.append(
                        {
                            "asset_id": asset_id,
                            "asset_type": asset.get("type"),
                            "owner_id": asset.get("ownerId"),
                            "database_path": original_path,
                            "resolved_root": resolved_original.root_slug,
                            "relative_path": resolved_original.relative_path,
                            "mapping_mode": resolved_original.mapping_mode,
                        }
                    )

            if progress_callback is not None and index % 2500 == 0:
                progress_callback(
                    {
                        "phase": "database-originals",
                        "current": index,
                        "total": len(asset_rows),
                        "percent": round(25 + (index / max(len(asset_rows), 1)) * 25, 2),
                        "message": ("Compared DB original paths against the cached uploads index."),
                        "dbMissingCount": len(db_missing_rows),
                        "unmappedCount": len(unmapped_rows),
                    }
                )

        for row in source_only_rows:
            relative_path = str(row["relative_path"])
            if relative_path in db_original_index:
                continue
            storage_missing_rows.append(
                {
                    "root_slug": row["root_slug"],
                    "relative_path": relative_path,
                    "file_name": row["file_name"],
                    "size_bytes": row["size_bytes"],
                    "snapshot_id": row["snapshot_id"],
                    "generation": row["generation"],
                }
            )

        if progress_callback is not None:
            progress_callback(
                {
                    "phase": "storage-originals",
                    "current": len(source_only_rows),
                    "total": len(source_only_rows),
                    "percent": 75.0,
                    "message": ("Compared cached storage originals against DB original paths."),
                    "storageMissingCount": len(storage_missing_rows),
                }
            )

        orphan_keys: set[tuple[str, str, str]] = set()
        for asset in asset_rows:
            asset_id = str(asset["id"])
            original_relative_path = original_by_asset.get(asset_id)
            if original_relative_path is None or original_relative_path in uploads_index:
                continue

            encoded_video_path = _truthy_path(asset.get("encodedVideoPath"))
            if encoded_video_path:
                self._append_orphan_row(
                    orphan_rows,
                    orphan_keys,
                    asset_id=asset_id,
                    derivative_type="encoded_video",
                    resolver=resolver,
                    path_text=encoded_video_path,
                    derivative_indexes=derivative_indexes,
                    original_relative_path=original_relative_path,
                )

            for derivative in derivative_rows_by_asset.get(asset_id, []):
                self._append_orphan_row(
                    orphan_rows,
                    orphan_keys,
                    asset_id=asset_id,
                    derivative_type=str(derivative["type"]),
                    resolver=resolver,
                    path_text=str(derivative["path"]),
                    derivative_indexes=derivative_indexes,
                    original_relative_path=original_relative_path,
                )

        if progress_callback is not None:
            progress_callback(
                {
                    "phase": "orphans",
                    "current": len(orphan_rows),
                    "total": len(orphan_rows),
                    "percent": 100.0,
                    "message": (
                        "Derived orphan derivative findings from the cached catalog and DB graph."
                    ),
                    "orphanCount": len(orphan_rows),
                }
            )

        derivative_snapshot_coverage = sorted(
            slug
            for slug in snapshot_by_slug
            if slug in _DERIVATIVE_ROOT_SLUGS or slug == _SOURCE_ROOT_SLUG
        )
        checks.append(
            CheckResult(
                name="catalog_snapshot_coverage",
                status=CheckStatus.PASS if derivative_snapshot_coverage else CheckStatus.WARN,
                message=(
                    "Committed catalog snapshots are available for the required storage roots."
                    if derivative_snapshot_coverage
                    else "Only a partial set of catalog snapshots is available."
                ),
                details={"roots": derivative_snapshot_coverage},
            )
        )
        checks.append(
            CheckResult(
                name="catalog_path_mapping",
                status=CheckStatus.WARN if unmapped_rows else CheckStatus.PASS,
                message=(
                    (
                        f"{len(unmapped_rows)} database paths could not be "
                        "mapped into configured runtime roots."
                    )
                    if unmapped_rows
                    else "Database paths mapped cleanly into configured runtime roots."
                ),
            )
        )

        sampled_db_missing = db_missing_rows[: self.sample_limit]
        sampled_storage_missing = storage_missing_rows[: self.sample_limit]
        sampled_orphans = orphan_rows[: self.sample_limit]
        sampled_unmapped = unmapped_rows[: self.sample_limit]

        summary = (
            "Catalog-backed consistency compared the cached storage inventory "
            "against the live database: "
            f"{len(db_missing_rows)} DB originals missing on storage, "
            f"{len(storage_missing_rows)} storage originals missing in DB, "
            f"{len(orphan_rows)} orphan derivatives, and "
            f"{len(zero_byte_rows)} zero-byte findings."
        )

        return ValidationReport(
            domain="consistency.catalog",
            action="validate",
            summary=summary,
            checks=checks,
            sections=[
                ValidationSection(
                    name=_DB_MISSING_SECTION,
                    status=_section_status(db_missing_rows),
                    rows=sampled_db_missing,
                ),
                ValidationSection(
                    name=_STORAGE_MISSING_SECTION,
                    status=_section_status(storage_missing_rows),
                    rows=sampled_storage_missing,
                ),
                ValidationSection(
                    name=_ORPHAN_SECTION,
                    status=_section_status(orphan_rows),
                    rows=sampled_orphans,
                ),
                ValidationSection(
                    name=_ZERO_BYTE_SECTION,
                    status=_section_status(zero_byte_rows[: self.sample_limit]),
                    rows=zero_byte_rows[: self.sample_limit],
                ),
                ValidationSection(
                    name=_UNMAPPED_SECTION,
                    status=CheckStatus.WARN if unmapped_rows else CheckStatus.PASS,
                    rows=sampled_unmapped,
                ),
            ],
            metrics=[
                {"name": "db_originals_missing_on_storage", "value": len(db_missing_rows)},
                {
                    "name": "storage_originals_missing_in_db",
                    "value": len(storage_missing_rows),
                },
                {
                    "name": "orphan_derivatives_without_original",
                    "value": len(orphan_rows),
                },
                {"name": "zero_byte_files", "value": len(zero_byte_rows)},
                {"name": "unmapped_database_paths", "value": len(unmapped_rows)},
            ],
            metadata={
                "configuredRoots": [row["slug"] for row in synced_roots],
                "latestSnapshots": latest_snapshots,
                "sampleLimit": self.sample_limit,
                "totals": {
                    "dbOriginalsMissingOnStorage": len(db_missing_rows),
                    "storageOriginalsMissingInDb": len(storage_missing_rows),
                    "orphanDerivativesWithoutOriginal": len(orphan_rows),
                    "zeroByteFiles": len(zero_byte_rows),
                    "unmappedDatabasePaths": len(unmapped_rows),
                },
                "truncated": {
                    _DB_MISSING_SECTION: len(db_missing_rows) > self.sample_limit,
                    _STORAGE_MISSING_SECTION: len(storage_missing_rows) > self.sample_limit,
                    _ORPHAN_SECTION: len(orphan_rows) > self.sample_limit,
                    _UNMAPPED_SECTION: len(unmapped_rows) > self.sample_limit,
                },
            },
            recommendations=[
                "Run a catalog rescan from the Storage page when the mounted storage has changed.",
                "Use the catalog-backed counts as cached storage truth before "
                "starting any destructive workflow.",
            ],
        )

    def _is_original_candidate(self, row: dict[str, object]) -> bool:
        extension = str(row.get("extension") or "").lower()
        relative_path = str(row.get("relative_path") or "")
        if extension == _SIDECAR_EXTENSION:
            return False
        return not relative_path.endswith(_SIDECAR_EXTENSION)

    def _append_orphan_row(
        self,
        orphan_rows: list[dict[str, object]],
        orphan_keys: set[tuple[str, str, str]],
        *,
        asset_id: str,
        derivative_type: str,
        resolver: ImmichStoragePathResolver,
        path_text: str,
        derivative_indexes: dict[str, set[str]],
        original_relative_path: str,
    ) -> None:
        resolved = resolver.resolve(path_text)
        if resolved is None:
            return
        if resolved.relative_path not in derivative_indexes.get(resolved.root_slug, set()):
            return
        key = (asset_id, derivative_type, resolved.relative_path)
        if key in orphan_keys:
            return
        orphan_keys.add(key)
        orphan_rows.append(
            {
                "asset_id": asset_id,
                "derivative_type": derivative_type,
                "root_slug": resolved.root_slug,
                "relative_path": resolved.relative_path,
                "database_path": path_text,
                "original_relative_path": original_relative_path,
            }
        )
