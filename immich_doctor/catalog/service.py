from __future__ import annotations

import errno
import logging
import os
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.catalog.models import CatalogFileObservation, CatalogRootSpec
from immich_doctor.catalog.paths import catalog_database_path, catalog_root
from immich_doctor.catalog.store import CatalogStore
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport, ValidationSection
from immich_doctor.core.paths import configured_immich_paths

_ROOT_SPECS = {
    "immich_library_root": ("library", "library"),
    "immich_uploads_path": ("uploads", "source"),
    "immich_thumbs_path": ("thumbs", "derivative"),
    "immich_profile_path": ("profile", "metadata"),
    "immich_video_path": ("video", "derivative"),
}

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a"}
_SCAN_PRIORITY = {
    "uploads": 0,
    "thumbs": 1,
    "profile": 2,
    "video": 3,
    "library": 4,
}
_DISCOVERY_PROGRESS_INTERVAL = 250

logger = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class CatalogRootRegistry:
    store: CatalogStore = field(default_factory=CatalogStore)
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)

    def configured_roots(self, settings: AppSettings) -> list[CatalogRootSpec]:
        roots: list[CatalogRootSpec] = []
        for setting_name, path in configured_immich_paths(settings).items():
            slug, root_type = _ROOT_SPECS.get(setting_name, (setting_name, "unknown"))
            roots.append(
                CatalogRootSpec(
                    slug=slug,
                    setting_name=setting_name,
                    root_type=root_type,
                    path=path,
                )
            )
        roots.sort(key=lambda item: item.slug)
        return roots

    def sync(self, settings: AppSettings) -> list[dict[str, object]]:
        roots = self.configured_roots(settings)
        for root in roots:
            self.store.upsert_storage_root(settings, root)
        return self.store.list_storage_roots(settings)

    def scan_roots(self, settings: AppSettings) -> list[CatalogRootSpec]:
        roots = self.configured_roots(settings)
        effective_roots: list[CatalogRootSpec] = []
        for root in roots:
            is_parent_of_other = any(
                other.slug != root.slug and self.filesystem.is_child_path(root.path, other.path)
                for other in roots
            )
            if is_parent_of_other:
                continue
            effective_roots.append(root)
        effective_roots.sort(key=lambda item: (_SCAN_PRIORITY.get(item.slug, 99), item.slug))
        return effective_roots


@dataclass(slots=True)
class CatalogInventoryScanService:
    store: CatalogStore = field(default_factory=CatalogStore)
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    registry: CatalogRootRegistry = field(default_factory=CatalogRootRegistry)

    def run(
        self,
        settings: AppSettings,
        *,
        root_slug: str | None,
        resume_session_id: str | None,
        max_files: int | None,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
        control_state_provider: Callable[[], dict[str, bool]] | None = None,
    ) -> ValidationReport:
        catalog_path_check = self.filesystem.validate_creatable_directory(
            "catalog_path",
            catalog_root(settings),
        )
        checks = [catalog_path_check]
        if catalog_path_check.status == CheckStatus.FAIL:
            return ValidationReport(
                domain="analyze.catalog",
                action="scan",
                summary="Catalog scan failed because the catalog path is not writable.",
                checks=checks,
                metadata={"catalog_path": str(catalog_root(settings))},
            )

        synced_roots = self.registry.sync(settings)
        overlap_check = self._overlap_check(synced_roots)
        checks.append(overlap_check)
        if not synced_roots:
            checks.append(
                CheckResult(
                    name="configured_catalog_roots",
                    status=CheckStatus.FAIL,
                    message="No Immich storage roots are configured for catalog scanning.",
                )
            )
            return ValidationReport(
                domain="analyze.catalog",
                action="scan",
                summary="Catalog scan failed because no storage roots are configured.",
                checks=checks,
                metadata={"catalog_path": str(catalog_database_path(settings))},
            )

        try:
            selected_root, session = self._select_session_or_root(
                settings,
                synced_roots=synced_roots,
                root_slug=root_slug,
                resume_session_id=resume_session_id,
                max_files=max_files,
            )
        except ValueError as exc:
            checks.append(
                CheckResult(
                    name="catalog_scan_selection",
                    status=CheckStatus.FAIL,
                    message=str(exc),
                )
            )
            return ValidationReport(
                domain="analyze.catalog",
                action="scan",
                summary="Catalog scan could not start with the requested selection.",
                checks=checks,
                sections=[self._roots_section(synced_roots)],
                metadata={"catalog_path": str(catalog_database_path(settings))},
            )

        root_path = Path(str(selected_root["absolute_path"]))
        root_check = self.filesystem.validate_readable_directory("scan_root", root_path)
        checks.append(root_check)
        if root_check.status == CheckStatus.FAIL:
            failed_session = self.store.mark_session_failed(settings, str(session["id"]))
            return self._build_scan_report(
                settings,
                checks=checks,
                root_rows=synced_roots,
                session_row=failed_session or session,
                snapshot_row=self.store.get_snapshot(settings, int(session["snapshot_id"])),
                summary="Catalog scan failed because the selected root is not readable.",
            )

        scan_result = self._execute_scan(
            settings,
            root_row=selected_root,
            session_row=session,
            max_files=max_files,
            progress_callback=progress_callback,
            control_state_provider=control_state_provider,
        )
        checks.extend(scan_result["checks"])
        return self._build_scan_report(
            settings,
            checks=checks,
            root_rows=synced_roots,
            session_row=scan_result["session"],
            snapshot_row=scan_result["snapshot"],
            summary=scan_result["summary"],
            run_context=scan_result["run_context"],
        )

    def _select_session_or_root(
        self,
        settings: AppSettings,
        *,
        synced_roots: list[dict[str, object]],
        root_slug: str | None,
        resume_session_id: str | None,
        max_files: int | None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        roots_by_slug = {str(root["slug"]): root for root in synced_roots}
        if resume_session_id:
            session = self.store.reopen_scan_session(settings, resume_session_id)
            if session is None:
                raise ValueError(f"Resume session `{resume_session_id}` was not found.")
            root_row = next(
                (
                    root
                    for root in synced_roots
                    if int(root["id"]) == int(session["storage_root_id"])
                ),
                None,
            )
            if root_row is None:
                raise ValueError(
                    f"Resume session `{resume_session_id}` points to a root that is not configured."
                )
            return root_row, session

        if root_slug is None:
            if len(synced_roots) != 1:
                raise ValueError(
                    "Select exactly one root with `--root` when multiple storage roots "
                    "are configured."
                )
            selected = synced_roots[0]
        else:
            selected = roots_by_slug.get(root_slug)
            if selected is None:
                raise ValueError(f"Unknown catalog root `{root_slug}`.")

        session = self.store.create_scan_session(
            settings,
            storage_root_id=int(selected["id"]),
            max_files=max_files,
        )
        return selected, session

    def _execute_scan(
        self,
        settings: AppSettings,
        *,
        root_row: dict[str, object],
        session_row: dict[str, object],
        max_files: int | None,
        progress_callback: Callable[[dict[str, object]], None] | None,
        control_state_provider: Callable[[], dict[str, bool]] | None,
    ) -> dict[str, object]:
        checks: list[CheckResult] = []
        session_id = str(session_row["id"])
        root_path = Path(str(root_row["absolute_path"]))
        files_seen = int(session_row["files_seen"])
        worker_count = settings.catalog_scan_workers
        self._prepare_directory_queue(
            settings,
            session_id=session_id,
            root_slug=str(root_row["slug"]),
            root_path=root_path,
            worker_count=worker_count,
            progress_callback=progress_callback,
        )
        inflight: dict[Future[dict[str, object]], tuple[int, str]] = {}
        completed_by_order: dict[int, tuple[str, dict[str, object]]] = {}
        next_claim_order = 0
        next_apply_order = 0
        pause_requested = False
        stop_requested = False

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            while True:
                control_state = (
                    control_state_provider()
                    if control_state_provider is not None
                    else {"pauseRequested": False, "stopRequested": False}
                )
                pause_requested = pause_requested or bool(control_state.get("pauseRequested"))
                stop_requested = stop_requested or bool(control_state.get("stopRequested"))

                while not pause_requested and len(inflight) < worker_count:
                    relative_path = self.store.claim_next_directory(settings, session_id)
                    if relative_path is None:
                        break
                    future = executor.submit(self._observe_directory, root_path, relative_path)
                    inflight[future] = (next_claim_order, relative_path)
                    next_claim_order += 1

                if not inflight:
                    break

                done, _ = wait(set(inflight), return_when=FIRST_COMPLETED)
                for future in done:
                    claim_order, relative_path = inflight.pop(future)
                    try:
                        observed = future.result()
                    except Exception:
                        logger.exception(
                            "Catalog scan observation failed for root=%s relative_path=%s",
                            root_row["slug"],
                            relative_path,
                        )
                        observed = {
                            "subdirectories": [],
                            "files": [],
                            "error_count": 1,
                            "bytes_delta": 0,
                            "last_relative_path": relative_path,
                        }
                    completed_by_order[claim_order] = (relative_path, observed)

                while next_apply_order in completed_by_order:
                    relative_path, observed = completed_by_order.pop(next_apply_order)
                    next_apply_order += 1

                    self.store.apply_directory_observation(
                        settings,
                        session_id=session_id,
                        storage_root_id=int(root_row["id"]),
                        snapshot_id=int(session_row["snapshot_id"]),
                        relative_path=relative_path,
                        subdirectories=observed["subdirectories"],
                        file_observations=observed["files"],
                        error_count=observed["error_count"],
                        bytes_delta=observed["bytes_delta"],
                        last_relative_path=observed["last_relative_path"],
                    )
                    files_seen += len(observed["files"])
                    updated_session = self.store.get_scan_session(settings, session_id)
                    pending_directories = self.store.count_pending_directories(settings, session_id)
                    if progress_callback is not None and updated_session is not None:
                        total_directories = (
                            int(updated_session["directories_completed"]) + pending_directories
                        )
                        percent = (
                            round(
                                (int(updated_session["directories_completed"]) / total_directories)
                                * 100,
                                2,
                            )
                            if total_directories > 0
                            else 0.0
                        )
                        scan_state = (
                            "stopping"
                            if stop_requested
                            else "pausing"
                            if pause_requested
                            else "running"
                        )
                        progress_callback(
                            {
                                "phase": "scan",
                                "rootSlug": str(root_row["slug"]),
                                "sessionId": session_id,
                                "configuredWorkerCount": worker_count,
                                "activeWorkerCount": len(inflight),
                                "scanState": scan_state,
                                "filesSeen": int(updated_session["files_seen"]),
                                "bytesSeen": int(updated_session["bytes_seen"]),
                                "directoriesTotal": total_directories,
                                "directoriesCompleted": int(
                                    updated_session["directories_completed"]
                                ),
                                "pendingDirectories": pending_directories,
                                "lastRelativePath": updated_session["last_relative_path"],
                                "percent": percent,
                            }
                        )
                    if max_files is not None and files_seen >= max_files:
                        pause_requested = True
                        break

                if pause_requested:
                    for future in inflight:
                        future.cancel()
                    self.store.requeue_processing_directories(settings, session_id)
                    paused_session = (
                        self.store.mark_session_stopped(settings, session_id)
                        if stop_requested
                        else self.store.mark_session_paused(settings, session_id)
                    )
                    snapshot = self.store.get_snapshot(settings, int(session_row["snapshot_id"]))
                    if paused_session is None or snapshot is None:
                        action = "stopped" if stop_requested else "paused"
                        raise ValueError(f"Catalog session `{session_id}` could not be {action}.")
                    checks.append(
                        CheckResult(
                            name="catalog_scan_session",
                            status=CheckStatus.WARN,
                            message=(
                                (
                                    f"Catalog session `{session_id}` stopped cooperatively at a "
                                    "safe boundary."
                                )
                                if stop_requested
                                else (
                                    f"Catalog session `{session_id}` paused after reaching the "
                                    "configured file limit."
                                )
                            ),
                            details={
                                "snapshot_id": paused_session["snapshot_id"],
                                "files_seen": paused_session["files_seen"],
                                "pending_directories": self.store.count_pending_directories(
                                    settings,
                                    session_id,
                                ),
                                "scan_workers": worker_count,
                                "scan_state": "stopped" if stop_requested else "paused",
                            },
                        )
                    )
                    return {
                        "checks": checks,
                        "session": paused_session,
                        "snapshot": snapshot,
                        "summary": (
                            (
                                f"Catalog scan stopped for root `{root_row['slug']}` after "
                                f"{paused_session['files_seen']} files. Resume with "
                                f"`--resume-session-id {session_id}`."
                            )
                            if stop_requested
                            else (
                                f"Catalog scan paused for root `{root_row['slug']}` after "
                                f"{paused_session['files_seen']} files. Resume with "
                                f"`--resume-session-id {session_id}`."
                            )
                        ),
                        "run_context": {
                            "scan_workers": worker_count,
                            "scan_state": "stopped" if stop_requested else "paused",
                        },
                    }

        completed_session = self.store.commit_scan_session(settings, session_id)
        snapshot = self.store.get_snapshot(settings, int(session_row["snapshot_id"]))
        if completed_session is None or snapshot is None:
            raise ValueError(f"Catalog session `{session_id}` could not be finalized.")
        checks.append(
            CheckResult(
                name="catalog_scan_session",
                status=CheckStatus.PASS
                if int(completed_session["error_count"]) == 0
                else CheckStatus.WARN,
                message=f"Catalog session `{session_id}` completed for root `{root_row['slug']}`.",
                details={
                    "snapshot_id": completed_session["snapshot_id"],
                    "files_seen": completed_session["files_seen"],
                    "error_count": completed_session["error_count"],
                    "scan_workers": worker_count,
                },
            )
        )
        return {
            "checks": checks,
            "session": completed_session,
            "snapshot": snapshot,
            "summary": (
                f"Catalog scan completed for root `{root_row['slug']}`. "
                f"Indexed {completed_session['files_seen']} files with "
                f"{snapshot['zero_byte_count']} zero-byte findings."
            ),
            "run_context": {"scan_workers": worker_count},
        }

    def _observe_directory(
        self,
        root_path: Path,
        relative_path: str,
    ) -> dict[str, object]:
        directory_path = root_path if not relative_path else root_path / relative_path
        subdirectories: list[str] = []
        files: list[CatalogFileObservation] = []
        error_count = 0
        bytes_delta = 0
        last_relative_path: str | None = None

        try:
            with os.scandir(directory_path) as iterator:
                for entry in iterator:
                    try:
                        entry_relative_path = self._relative_path(root_path, Path(entry.path))
                        if entry.is_dir(follow_symlinks=False):
                            subdirectories.append(entry_relative_path)
                            last_relative_path = entry_relative_path
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        stat_result = entry.stat(follow_symlinks=False)
                        observation = self._build_observation(
                            root_path=root_path,
                            entry_path=Path(entry.path),
                            stat_result=stat_result,
                        )
                        files.append(observation)
                        bytes_delta += observation.size_bytes
                        last_relative_path = observation.relative_path
                    except OSError:
                        error_count += 1
        except OSError as exc:
            if exc.errno not in {errno.ENOENT, errno.EACCES, errno.EPERM}:
                error_count += 1
            else:
                error_count += 1

        subdirectories.sort()
        files.sort(key=lambda item: item.relative_path)
        return {
            "subdirectories": subdirectories,
            "files": files,
            "error_count": error_count,
            "bytes_delta": bytes_delta,
            "last_relative_path": last_relative_path,
        }

    def _prepare_directory_queue(
        self,
        settings: AppSettings,
        *,
        session_id: str,
        root_slug: str,
        root_path: Path,
        worker_count: int,
        progress_callback: Callable[[dict[str, object]], None] | None,
    ) -> None:
        discovered_directories: list[str] = []

        def emit_discovery(count: int) -> None:
            if progress_callback is None:
                return
            progress_callback(
                {
                    "phase": "prepare",
                    "rootSlug": root_slug,
                    "configuredWorkerCount": worker_count,
                    "activeWorkerCount": 0,
                    "scanState": "running",
                    "current": count,
                    "total": None,
                    "percent": None,
                    "directoriesDiscovered": count,
                    "message": f"Counting directories for root `{root_slug}`.",
                }
            )

        stack: list[tuple[Path, str]] = [(root_path, "")]
        seen_relative_paths = {""}

        while stack:
            current_path, relative_path = stack.pop()
            discovered_directories.append(relative_path)
            discovered_count = len(discovered_directories)
            if progress_callback is not None and (
                discovered_count == 1 or discovered_count % _DISCOVERY_PROGRESS_INTERVAL == 0
            ):
                emit_discovery(discovered_count)

            try:
                child_directories: list[tuple[Path, str]] = []
                with os.scandir(current_path) as iterator:
                    for entry in iterator:
                        try:
                            if not entry.is_dir(follow_symlinks=False):
                                continue
                        except OSError:
                            continue
                        child_relative_path = self._relative_path(root_path, Path(entry.path))
                        if child_relative_path in seen_relative_paths:
                            continue
                        seen_relative_paths.add(child_relative_path)
                        child_directories.append((Path(entry.path), child_relative_path))
                child_directories.sort(key=lambda item: item[1], reverse=True)
                stack.extend(child_directories)
            except OSError:
                continue

        self.store.seed_directory_queue(
            settings,
            session_id=session_id,
            relative_paths=discovered_directories,
        )

        if progress_callback is None:
            return

        session_row = self.store.get_scan_session(settings, session_id)
        pending_directories = self.store.count_pending_directories(settings, session_id)
        directories_completed = int(session_row["directories_completed"]) if session_row else 0
        total_directories = directories_completed + pending_directories
        progress_callback(
            {
                "phase": "prepare",
                "rootSlug": root_slug,
                "configuredWorkerCount": worker_count,
                "activeWorkerCount": 0,
                "scanState": "running",
                "current": len(discovered_directories),
                "total": len(discovered_directories),
                "percent": None,
                "directoriesDiscovered": len(discovered_directories),
                "directoriesTotal": total_directories,
                "directoriesCompleted": directories_completed,
                "pendingDirectories": pending_directories,
                "message": f"Prepared {total_directories} directories for root `{root_slug}`.",
            }
        )

    def _build_observation(
        self,
        *,
        root_path: Path,
        entry_path: Path,
        stat_result: os.stat_result,
    ) -> CatalogFileObservation:
        relative_path = self._relative_path(root_path, entry_path)
        parent_relative_path = str(Path(relative_path).parent).replace("\\", "/")
        if parent_relative_path == ".":
            parent_relative_path = ""
        extension = entry_path.suffix.lower() or None
        file_type_guess, media_class_guess = self._guess_types(extension)
        created_at_fs = datetime.fromtimestamp(stat_result.st_ctime, tz=UTC).isoformat()
        modified_at_fs = datetime.fromtimestamp(stat_result.st_mtime, tz=UTC).isoformat()
        return CatalogFileObservation(
            relative_path=relative_path,
            parent_relative_path=parent_relative_path,
            file_name=entry_path.name,
            extension=extension,
            size_bytes=int(stat_result.st_size),
            created_at_fs=created_at_fs,
            modified_at_fs=modified_at_fs,
            file_type_guess=file_type_guess,
            media_class_guess=media_class_guess,
            zero_byte_flag=stat_result.st_size == 0,
            stat_device=str(getattr(stat_result, "st_dev", "")) or None,
            stat_inode=str(getattr(stat_result, "st_ino", "")) or None,
        )

    def _relative_path(self, root_path: Path, target_path: Path) -> str:
        return target_path.relative_to(root_path).as_posix()

    def _guess_types(self, extension: str | None) -> tuple[str, str]:
        if extension is None:
            return "unknown", "unknown"
        if extension in _IMAGE_EXTENSIONS:
            return "image", "image"
        if extension in _VIDEO_EXTENSIONS:
            return "video", "video"
        if extension in _AUDIO_EXTENSIONS:
            return "audio", "audio"
        return "generic", "unknown"

    def _overlap_check(self, root_rows: list[dict[str, object]]) -> CheckResult:
        overlaps: list[dict[str, str]] = []
        for index, left in enumerate(root_rows):
            left_path = Path(str(left["absolute_path"]))
            for right in root_rows[index + 1 :]:
                right_path = Path(str(right["absolute_path"]))
                if self.filesystem.is_child_path(left_path, right_path):
                    overlaps.append({"parent": str(left["slug"]), "child": str(right["slug"])})
                elif self.filesystem.is_child_path(right_path, left_path):
                    overlaps.append({"parent": str(right["slug"]), "child": str(left["slug"])})
        if overlaps:
            return CheckResult(
                name="catalog_root_overlap",
                status=CheckStatus.WARN,
                message=(
                    "Configured catalog roots overlap and may intentionally index the "
                    "same files more than once."
                ),
                details={"overlaps": overlaps},
            )
        return CheckResult(
            name="catalog_root_overlap",
            status=CheckStatus.PASS,
            message="Configured catalog roots do not overlap.",
        )

    def _build_scan_report(
        self,
        settings: AppSettings,
        *,
        checks: list[CheckResult],
        root_rows: list[dict[str, object]],
        session_row: dict[str, object],
        snapshot_row: dict[str, object] | None,
        summary: str,
        run_context: dict[str, object],
    ) -> ValidationReport:
        sections = [
            self._roots_section(root_rows),
            ValidationSection(
                name="SCAN_SESSION",
                status=self._session_status_to_check_status(str(session_row["status"])),
                rows=[session_row],
            ),
        ]
        if snapshot_row is not None:
            sections.append(
                ValidationSection(
                    name="SCAN_SNAPSHOT",
                    status=self._snapshot_status_to_check_status(str(snapshot_row["status"])),
                    rows=[snapshot_row],
                )
            )
        return ValidationReport(
            domain="analyze.catalog",
            action="scan",
            summary=summary,
            checks=checks,
            sections=sections,
            metadata={
                "catalog_path": str(catalog_database_path(settings)),
                "generated_at_runtime": _utcnow(),
                **run_context,
            },
            metrics=[
                {"name": "files_seen", "value": session_row["files_seen"]},
                {"name": "directories_completed", "value": session_row["directories_completed"]},
                {"name": "bytes_seen", "value": session_row["bytes_seen"]},
                {"name": "error_count", "value": session_row["error_count"]},
            ],
        )

    def _roots_section(self, root_rows: list[dict[str, object]]) -> ValidationSection:
        return ValidationSection(
            name="CATALOG_ROOTS",
            status=CheckStatus.PASS if root_rows else CheckStatus.FAIL,
            rows=root_rows,
        )

    def _session_status_to_check_status(self, status: str) -> CheckStatus:
        if status == "completed":
            return CheckStatus.PASS
        if status in {"paused", "stopped"}:
            return CheckStatus.WARN
        if status == "failed":
            return CheckStatus.FAIL
        return CheckStatus.WARN

    def _snapshot_status_to_check_status(self, status: str) -> CheckStatus:
        if status == "committed":
            return CheckStatus.PASS
        if status == "failed":
            return CheckStatus.FAIL
        return CheckStatus.WARN


@dataclass(slots=True)
class CatalogStatusService:
    store: CatalogStore = field(default_factory=CatalogStore)
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    registry: CatalogRootRegistry = field(default_factory=CatalogRootRegistry)

    def run(self, settings: AppSettings, *, root_slug: str | None) -> ValidationReport:
        catalog_path_check = self.filesystem.validate_creatable_directory(
            "catalog_path",
            catalog_root(settings),
        )
        synced_roots = self.registry.sync(settings)
        effective_scan_roots = self.registry.scan_roots(settings)
        root_check = CheckResult(
            name="configured_catalog_roots",
            status=CheckStatus.PASS if synced_roots else CheckStatus.WARN,
            message=(
                f"Found {len(synced_roots)} configured catalog roots."
                if synced_roots
                else "No configured catalog roots were found."
            ),
        )
        sessions = self.store.list_scan_sessions(settings, slug=root_slug)
        snapshots = self.store.list_latest_snapshots(settings, slug=root_slug)
        effective_root_slugs = [root.slug for root in effective_scan_roots]
        current_root_slugs = sorted(
            [
                str(row["root_slug"])
                for row in snapshots
                if row.get("snapshot_id") is not None
                and bool(row.get("snapshot_current"))
                and str(row["root_slug"]) in effective_root_slugs
            ]
        )
        stale_root_slugs = sorted(
            [
                str(row["root_slug"])
                for row in snapshots
                if row.get("snapshot_id") is not None
                and not bool(row.get("snapshot_current"))
                and str(row["root_slug"]) in effective_root_slugs
            ]
        )
        missing_root_slugs = [
            slug
            for slug in effective_root_slugs
            if slug not in set(current_root_slugs) and slug not in set(stale_root_slugs)
        ]
        requires_scan = bool(effective_root_slugs) and bool(missing_root_slugs or stale_root_slugs)
        active_sessions = [
            row
            for row in sessions
            if str(row["status"]) in {"running", "paused"}
            and str(row["root_slug"]) in effective_root_slugs
        ]
        summary = (
            f"Catalog status loaded {len(synced_roots)} roots, "
            f"{len(snapshots)} latest snapshots, and {len(sessions)} scan sessions."
        )
        return ValidationReport(
            domain="analyze.catalog",
            action="status",
            summary=summary,
            checks=[
                catalog_path_check,
                root_check,
                CheckResult(
                    name="catalog_scan_coverage",
                    status=CheckStatus.WARN if requires_scan else CheckStatus.PASS,
                    message=(
                        "Current committed catalog snapshots exist for all effective scan roots."
                        if not requires_scan
                        else (
                            "One or more effective scan roots are missing a current committed "
                            "snapshot."
                        )
                    ),
                    details={
                        "effective_root_slugs": effective_root_slugs,
                        "current_root_slugs": current_root_slugs,
                        "stale_root_slugs": stale_root_slugs,
                        "missing_root_slugs": missing_root_slugs,
                    },
                ),
            ],
            sections=[
                ValidationSection(
                    name="CATALOG_ROOTS",
                    status=CheckStatus.PASS if synced_roots else CheckStatus.WARN,
                    rows=(
                        synced_roots
                        if root_slug is None
                        else [row for row in synced_roots if str(row["slug"]) == root_slug]
                    ),
                ),
                ValidationSection(
                    name="LATEST_SNAPSHOTS",
                    status=CheckStatus.PASS if snapshots else CheckStatus.SKIP,
                    rows=snapshots,
                ),
                ValidationSection(
                    name="SCAN_SESSIONS",
                    status=CheckStatus.PASS if sessions else CheckStatus.SKIP,
                    rows=sessions,
                ),
            ],
            metadata={
                "catalog_path": str(catalog_database_path(settings)),
                "scanCoverage": {
                    "effectiveRootSlugs": effective_root_slugs,
                    "currentRootSlugs": current_root_slugs,
                    "staleRootSlugs": stale_root_slugs,
                    "missingRootSlugs": missing_root_slugs,
                    "requiresScan": requires_scan,
                    "hasCompleteCoverage": not requires_scan,
                    "activeSessions": active_sessions,
                },
            },
        )


@dataclass(slots=True)
class CatalogZeroByteReportService:
    store: CatalogStore = field(default_factory=CatalogStore)
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    registry: CatalogRootRegistry = field(default_factory=CatalogRootRegistry)

    def run(
        self,
        settings: AppSettings,
        *,
        root_slug: str | None,
        limit: int,
    ) -> ValidationReport:
        catalog_path_check = self.filesystem.validate_creatable_directory(
            "catalog_path",
            catalog_root(settings),
        )
        self.registry.sync(settings)
        rows = self.store.list_zero_byte_files(settings, slug=root_slug, limit=limit)
        snapshots = self.store.list_latest_snapshots(settings, slug=root_slug)
        summary = (
            f"Loaded {len(rows)} zero-byte file findings from the latest committed "
            "catalog snapshots."
        )
        snapshots_available = any(row["snapshot_id"] is not None for row in snapshots)
        return ValidationReport(
            domain="analyze.catalog",
            action="zero-byte",
            summary=summary,
            checks=[
                catalog_path_check,
                CheckResult(
                    name="catalog_latest_snapshots",
                    status=CheckStatus.PASS if snapshots_available else CheckStatus.WARN,
                    message=(
                        "Committed catalog snapshots are available for zero-byte reporting."
                        if snapshots_available
                        else "No committed catalog snapshots are available yet."
                    ),
                ),
            ],
            sections=[
                ValidationSection(
                    name="ZERO_BYTE_FILES",
                    status=CheckStatus.FAIL if rows else CheckStatus.PASS,
                    rows=rows,
                )
            ],
            metadata={
                "catalog_path": str(catalog_database_path(settings)),
                "limit": limit,
                "root_slug": root_slug,
            },
        )
