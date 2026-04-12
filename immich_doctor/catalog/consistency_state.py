from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.catalog.service import CatalogRootRegistry
from immich_doctor.catalog.store import CatalogStore
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.storage.path_mapping import ImmichStoragePathResolver

ZERO_BYTE_SECTION = "ZERO_BYTE_FILES"
DB_MISSING_SECTION = "DB_ORIGINALS_MISSING_ON_STORAGE"
STORAGE_MISSING_SECTION = "STORAGE_ORIGINALS_MISSING_IN_DB"
ORPHAN_SECTION = "ORPHAN_DERIVATIVES_WITHOUT_ORIGINAL"
UNMAPPED_SECTION = "UNMAPPED_DATABASE_PATHS"
SOURCE_ROOT_SLUG = "uploads"
DERIVATIVE_ROOT_SLUGS = {"thumbs", "profile", "video"}
SIDECAR_EXTENSION = ".xmp"
FUSE_HIDDEN_PREFIX = ".fuse_hidden"
IMMICH_MARKER_FILE = ".immich"


def truthy_path(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def parse_timestamp(value: object) -> datetime | None:
    text = truthy_path(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


@dataclass(slots=True, frozen=True)
class CatalogSnapshotState:
    synced_roots: list[dict[str, object]]
    effective_root_slugs: list[str]
    latest_snapshots: list[dict[str, object]]
    snapshot_by_slug: dict[str, dict[str, object]]
    stale_root_slugs: list[str]
    missing_root_slugs: list[str]
    checks: list[CheckResult]
    ready: bool
    metadata: dict[str, object]
    comparison_window_started_at: str | None = None
    comparison_window_committed_at: str | None = None


@dataclass(slots=True)
class CatalogConsistencyState:
    checks: list[CheckResult]
    latest_snapshots: list[dict[str, object]]
    latest_files: list[dict[str, object]]
    asset_rows: list[dict[str, object]]
    asset_file_rows: list[dict[str, object]]
    zero_byte_rows: list[dict[str, object]]
    db_missing_rows: list[dict[str, object]]
    storage_missing_rows: list[dict[str, object]]
    orphan_rows: list[dict[str, object]]
    unmapped_rows: list[dict[str, object]]
    uploads_rows: list[dict[str, object]]
    uploads_index: set[str]
    db_original_index: set[str]
    original_by_asset: dict[str, str]
    derivative_indexes: dict[str, set[str]]
    snapshot_basis: list[dict[str, object]]
    latest_scan_committed_at: str | None
    comparison_window_started_at: str | None
    comparison_window_committed_at: str | None
    configured_root_slugs: list[str]
    total_assets_scanned: int = 0
    valid_motion_video_components: int = 0
    progress_metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class CatalogConsistencyStateCollector:
    store: CatalogStore = field(default_factory=CatalogStore)
    registry: CatalogRootRegistry = field(default_factory=CatalogRootRegistry)
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)

    def prepare_snapshot_state(self, settings: AppSettings) -> CatalogSnapshotState:
        synced_roots = self.registry.sync(settings)
        effective_root_slugs = [root.slug for root in self.registry.scan_roots(settings)]
        latest_snapshots = self.store.list_latest_snapshots(settings)
        snapshot_by_slug = {
            str(row["root_slug"]): row
            for row in latest_snapshots
            if row.get("snapshot_id") is not None and bool(row.get("snapshot_current"))
        }
        stale_root_slugs = sorted(
            [
                str(row["root_slug"])
                for row in latest_snapshots
                if row.get("snapshot_id") is not None
                and not bool(row.get("snapshot_current"))
                and str(row["root_slug"]) in effective_root_slugs
            ]
        )
        missing_root_slugs = [
            slug
            for slug in effective_root_slugs
            if slug not in snapshot_by_slug and slug not in stale_root_slugs
        ]
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
        current_snapshots = [
            snapshot_by_slug[slug]
            for slug in effective_root_slugs
            if slug in snapshot_by_slug
        ]
        comparison_window_started_at_dt = min(
            (
                value
                for value in (
                    parse_timestamp(row.get("started_at")) for row in current_snapshots
                )
                if value is not None
            ),
            default=None,
        )
        comparison_window_committed_at_dt = max(
            (
                value
                for value in (
                    parse_timestamp(row.get("committed_at")) for row in current_snapshots
                )
                if value is not None
            ),
            default=None,
        )
        comparison_window_started_at = (
            comparison_window_started_at_dt.isoformat()
            if comparison_window_started_at_dt is not None
            else None
        )
        comparison_window_committed_at = (
            comparison_window_committed_at_dt.isoformat()
            if comparison_window_committed_at_dt is not None
            else None
        )
        ready = not (missing_root_slugs or stale_root_slugs)
        metadata = {
            "configuredRoots": effective_root_slugs,
            "latestSnapshots": latest_snapshots,
            "staleRootSlugs": stale_root_slugs,
            "missingRootSlugs": missing_root_slugs,
            "requiresCurrentScan": not ready,
            "comparisonWindowStartedAt": comparison_window_started_at,
            "comparisonWindowCommittedAt": comparison_window_committed_at,
        }
        if not ready:
            checks.append(
                CheckResult(
                    name="catalog_current_snapshots",
                    status=CheckStatus.FAIL,
                    message=(
                        "Current committed catalog snapshots are not available for every "
                        "effective storage root. Run a catalog scan first."
                    ),
                    details={
                        "effective_root_slugs": effective_root_slugs,
                        "missing_root_slugs": missing_root_slugs,
                        "stale_root_slugs": stale_root_slugs,
                    },
                )
            )
        return CatalogSnapshotState(
            synced_roots=synced_roots,
            effective_root_slugs=effective_root_slugs,
            latest_snapshots=latest_snapshots,
            snapshot_by_slug=snapshot_by_slug,
            stale_root_slugs=stale_root_slugs,
            missing_root_slugs=missing_root_slugs,
            checks=checks,
            ready=ready,
            metadata=metadata,
            comparison_window_started_at=comparison_window_started_at,
            comparison_window_committed_at=comparison_window_committed_at,
        )

    def collect(
        self,
        settings: AppSettings,
        *,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> CatalogConsistencyState:
        snapshot_state = self.prepare_snapshot_state(settings)
        if not snapshot_state.ready:
            raise ValueError("Catalog consistency state requires current committed snapshots.")

        dsn = settings.postgres_dsn_value()
        if not dsn:
            raise ValueError("Database DSN is required to collect catalog consistency state.")

        timeout = settings.postgres_connect_timeout_seconds
        checks = list(snapshot_state.checks)
        connection_check = self.postgres.validate_connection(dsn, timeout)
        checks.append(connection_check)
        if connection_check.status == CheckStatus.FAIL:
            raise ValueError(
                "PostgreSQL connection is required to collect catalog consistency state."
            )

        resolver = ImmichStoragePathResolver(settings)
        comparison_window_started_at = snapshot_state.comparison_window_started_at
        zero_byte_rows = [
            row
            for row in self.store.list_zero_byte_files(settings, limit=10_000)
            if self._row_within_snapshot_window(
                row,
                comparison_window_started_at,
                timestamp_field="modified_at_fs",
            )
        ]
        latest_files = [
            row
            for row in self.store.list_latest_snapshot_files(settings)
            if self._row_within_snapshot_window(
                row,
                comparison_window_started_at,
                timestamp_field="modified_at_fs",
            )
        ]
        files_by_root: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in latest_files:
            files_by_root[str(row["root_slug"])].append(row)

        uploads_rows = files_by_root.get(SOURCE_ROOT_SLUG, [])
        uploads_index = {str(row["relative_path"]) for row in uploads_rows}
        source_only_rows = [row for row in uploads_rows if self._is_original_candidate(row)]
        derivative_indexes = {
            slug: {str(row["relative_path"]) for row in rows}
            for slug, rows in files_by_root.items()
            if slug in DERIVATIVE_ROOT_SLUGS or slug == SOURCE_ROOT_SLUG
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

        asset_rows = [
            row
            for row in self.postgres.list_all_assets_for_catalog_consistency(dsn, timeout)
            if self._asset_within_snapshot_window(row, comparison_window_started_at)
        ]
        stable_asset_ids = {str(row["id"]) for row in asset_rows}
        asset_file_rows = [
            row
            for row in self.postgres.list_all_asset_files_for_catalog_consistency(dsn, timeout)
            if str(row.get("assetId")) in stable_asset_ids
        ]
        live_photo_video_ids = {
            str(value)
            for asset in asset_rows
            for value in [asset.get("livePhotoVideoId")]
            if truthy_path(value) is not None
        }

        db_missing_rows: list[dict[str, object]] = []
        storage_missing_rows: list[dict[str, object]] = []
        orphan_rows: list[dict[str, object]] = []
        unmapped_rows: list[dict[str, object]] = []
        db_original_index: set[str] = set()
        original_by_asset: dict[str, str] = {}
        derivative_rows_by_asset: dict[str, list[dict[str, object]]] = defaultdict(list)
        total_assets_scanned = 0
        valid_motion_video_components = 0

        for row in asset_file_rows:
            derivative_rows_by_asset[str(row["assetId"])].append(row)

        for index, asset in enumerate(asset_rows, start=1):
            asset_id = str(asset["id"])
            original_path = truthy_path(asset.get("originalPath"))
            if not original_path:
                continue
            total_assets_scanned += 1
            asset_name = truthy_path(asset.get("originalFileName"))

            resolved_original = resolver.resolve(original_path)
            if resolved_original is None:
                unmapped_rows.append(
                    {
                        "asset_id": asset_id,
                        "asset_name": asset_name,
                        "path_kind": "original",
                        "database_path": original_path,
                        "mapping_status": (
                            "legacy_path_unmapped"
                            if resolver.looks_like_legacy_immich_path(original_path)
                            else "unrecognized_path"
                        ),
                    }
                )
                continue

            if resolved_original.root_slug != SOURCE_ROOT_SLUG:
                if self._is_valid_motion_video_component(
                    asset,
                    original_path=original_path,
                    resolved_root=resolved_original.root_slug,
                    live_photo_video_ids=live_photo_video_ids,
                ):
                    if resolved_original.relative_path in derivative_indexes.get(
                        resolved_original.root_slug,
                        set(),
                    ):
                        valid_motion_video_components += 1
                        continue
                    db_missing_rows.append(
                        {
                            "asset_id": asset_id,
                            "asset_name": asset_name,
                            "asset_type": asset.get("type"),
                            "database_path": original_path,
                            "resolved_root": resolved_original.root_slug,
                            "relative_path": resolved_original.relative_path,
                            "mapping_mode": resolved_original.mapping_mode,
                            "classification": "valid_motion_video_component_missing_on_storage",
                        }
                    )
                    continue
                unmapped_rows.append(
                    {
                        "asset_id": asset_id,
                        "asset_name": asset_name,
                        "path_kind": "original",
                        "database_path": original_path,
                        "mapping_status": "unexpected_root",
                        "resolved_root": resolved_original.root_slug,
                        "mapping_mode": resolved_original.mapping_mode,
                    }
                )
                continue

            db_original_index.add(resolved_original.relative_path)
            original_by_asset[asset_id] = resolved_original.relative_path
            if resolved_original.relative_path not in uploads_index:
                db_missing_rows.append(
                    {
                        "asset_id": asset_id,
                        "asset_name": asset_name,
                        "asset_type": asset.get("type"),
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
                        "message": "Compared DB original paths against the cached uploads index.",
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
                    "absolute_path": str(
                        settings.immich_uploads_path.joinpath(*relative_path.split("/"))
                    )
                    if settings.immich_uploads_path is not None
                    else None,
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
                    "message": "Compared cached storage originals against DB original paths.",
                    "storageMissingCount": len(storage_missing_rows),
                }
            )

        orphan_keys: set[tuple[str, str, str]] = set()
        for asset in asset_rows:
            asset_id = str(asset["id"])
            original_relative_path = original_by_asset.get(asset_id)
            if original_relative_path is None or original_relative_path in uploads_index:
                continue

            encoded_video_path = truthy_path(asset.get("encodedVideoPath"))
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
            for slug in snapshot_state.snapshot_by_slug
            if slug in DERIVATIVE_ROOT_SLUGS or slug == SOURCE_ROOT_SLUG
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
                    f"{len(unmapped_rows)} database paths could not be mapped "
                    "into configured runtime roots."
                    if unmapped_rows
                    else "Database paths mapped cleanly into configured runtime roots."
                ),
            )
        )

        snapshot_basis = [
            {
                "rootSlug": str(row["root_slug"]),
                "snapshotId": row["snapshot_id"],
                "generation": row["generation"],
                "startedAt": row.get("started_at"),
                "committedAt": row["committed_at"],
                "absolutePath": row["absolute_path"],
            }
            for row in snapshot_state.latest_snapshots
            if row.get("snapshot_id") is not None
            and bool(row.get("snapshot_current"))
            and str(row["root_slug"]) in snapshot_state.effective_root_slugs
        ]
        latest_scan_committed_at = max(
            (
                str(row["committed_at"])
                for row in snapshot_state.latest_snapshots
                if row.get("committed_at")
                and bool(row.get("snapshot_current"))
                and str(row["root_slug"]) in snapshot_state.effective_root_slugs
            ),
            default=None,
        )

        return CatalogConsistencyState(
            checks=checks,
            latest_snapshots=snapshot_state.latest_snapshots,
            latest_files=latest_files,
            asset_rows=asset_rows,
            asset_file_rows=asset_file_rows,
            zero_byte_rows=zero_byte_rows,
            db_missing_rows=db_missing_rows,
            storage_missing_rows=storage_missing_rows,
            orphan_rows=orphan_rows,
            unmapped_rows=unmapped_rows,
            uploads_rows=uploads_rows,
            uploads_index=uploads_index,
            db_original_index=db_original_index,
            original_by_asset=original_by_asset,
            derivative_indexes=derivative_indexes,
            snapshot_basis=snapshot_basis,
            latest_scan_committed_at=latest_scan_committed_at,
            comparison_window_started_at=comparison_window_started_at,
            comparison_window_committed_at=snapshot_state.comparison_window_committed_at,
            configured_root_slugs=[row["slug"] for row in snapshot_state.synced_roots],
            total_assets_scanned=total_assets_scanned,
            valid_motion_video_components=valid_motion_video_components,
            progress_metadata=snapshot_state.metadata,
        )

    def _asset_within_snapshot_window(
        self,
        row: dict[str, object],
        comparison_window_started_at: str | None,
    ) -> bool:
        cutoff = parse_timestamp(comparison_window_started_at)
        if cutoff is None:
            return True
        created_at = parse_timestamp(row.get("createdAt"))
        updated_at = parse_timestamp(row.get("updatedAt"))
        for candidate in (created_at, updated_at):
            if candidate is not None and candidate > cutoff:
                return False
        return True

    def _row_within_snapshot_window(
        self,
        row: dict[str, object],
        comparison_window_started_at: str | None,
        *,
        timestamp_field: str,
    ) -> bool:
        cutoff = parse_timestamp(comparison_window_started_at)
        if cutoff is None:
            return True
        row_timestamp = parse_timestamp(row.get(timestamp_field))
        if row_timestamp is None:
            return True
        return row_timestamp <= cutoff

    def _is_original_candidate(self, row: dict[str, object]) -> bool:
        extension = str(row.get("extension") or "").lower()
        relative_path = str(row.get("relative_path") or "")
        file_name = str(row.get("file_name") or "")
        if extension == SIDECAR_EXTENSION:
            return False
        if file_name == IMMICH_MARKER_FILE or file_name.startswith(FUSE_HIDDEN_PREFIX):
            return False
        return not relative_path.endswith(SIDECAR_EXTENSION)

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
                "absolute_path": str(resolved.absolute_path),
                "database_path": path_text,
                "original_relative_path": original_relative_path,
            }
        )

    def _is_valid_motion_video_component(
        self,
        asset: dict[str, object],
        *,
        original_path: str,
        resolved_root: str,
        live_photo_video_ids: set[str],
    ) -> bool:
        asset_id = str(asset.get("id") or "").strip()
        asset_type = str(asset.get("type") or "").strip().upper()
        normalized_path = original_path.replace("\\", "/")
        return (
            resolved_root == "video"
            and asset_type == "VIDEO"
            and "/encoded-video/" in normalized_path
            and asset_id in live_photo_video_ids
        )
