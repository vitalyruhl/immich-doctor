from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.core.paths import configured_immich_paths
from immich_doctor.storage.empty_folders.models import (
    EmptyDirectoryFinding,
    EmptyFolderScanReport,
)

_ROOT_SPECS = {
    "immich_library_root": "library",
    "immich_uploads_path": "uploads",
    "immich_thumbs_path": "thumbs",
    "immich_profile_path": "profile",
    "immich_video_path": "video",
}


@dataclass(slots=True)
class _RootScanState:
    root_slug: str
    root_path: Path
    directory_count: int = 0
    findings: list[EmptyDirectoryFinding] = field(default_factory=list)
    orphan_parents: list[EmptyDirectoryFinding] = field(default_factory=list)
    symlink_directories: list[dict[str, str]] = field(default_factory=list)
    entry_errors: list[dict[str, str]] = field(default_factory=list)
    error_message: str | None = None


@dataclass(slots=True)
class EmptyFolderScanner:
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)

    def scan(
        self,
        settings: AppSettings,
        *,
        root_slug: str | None = None,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> EmptyFolderScanReport:
        checks: list[CheckResult] = []
        roots = self._effective_roots(settings, root_slug=root_slug)
        if not roots:
            checks.append(
                CheckResult(
                    name="empty_folder_roots",
                    status=CheckStatus.FAIL,
                    message="No storage roots are configured for empty-folder scanning.",
                )
            )
            return EmptyFolderScanReport(
                domain="storage.empty-folders",
                action="scan",
                summary="Empty-folder scan failed because no storage roots are configured.",
                checks=checks,
                metadata={"requested_root_slug": root_slug},
            )

        findings: list[EmptyDirectoryFinding] = []
        orphan_parents: list[EmptyDirectoryFinding] = []
        symlink_directories: list[dict[str, str]] = []
        entry_errors: list[dict[str, str]] = []
        roots_with_errors: dict[str, str] = {}
        scanned_root_slugs: list[str] = []
        total_directories_scanned = 0

        checks.append(
            CheckResult(
                name="empty_folder_root_count",
                status=CheckStatus.PASS,
                message=f"Scanning {len(roots)} storage roots for empty directories.",
                details={"roots": [slug for slug, _ in roots]},
            )
        )

        for slug, path in roots:
            readability_check = self.filesystem.validate_readable_directory(
                f"empty_folder_root_{slug}",
                path,
            )
            checks.append(readability_check)
            if readability_check.status == CheckStatus.FAIL:
                roots_with_errors[slug] = readability_check.message
                continue

            state = _RootScanState(root_slug=slug, root_path=path)
            self._scan_directory(
                state,
                current_path=path,
                progress_callback=progress_callback,
            )
            scanned_root_slugs.append(slug)
            total_directories_scanned += state.directory_count
            findings.extend(state.findings)
            orphan_parents.extend(state.orphan_parents)
            symlink_directories.extend(state.symlink_directories)
            entry_errors.extend(state.entry_errors)
            if state.error_message:
                roots_with_errors[slug] = state.error_message

        findings.sort(key=lambda item: (item.root_slug, -item.depth, item.relative_path))
        orphan_parents.sort(key=lambda item: (item.root_slug, -item.depth, item.relative_path))

        if not scanned_root_slugs:
            summary = "Empty-folder scan could not read any configured storage roots."
        elif findings:
            summary = (
                f"Empty-folder scan found {len(findings)} empty leaf directories across "
                f"{len(scanned_root_slugs)} scanned roots."
            )
        else:
            summary = (
                f"Empty-folder scan found no empty leaf directories across "
                f"{len(scanned_root_slugs)} scanned roots."
            )

        return EmptyFolderScanReport(
            domain="storage.empty-folders",
            action="scan",
            summary=summary,
            checks=checks,
            findings=findings,
            orphan_parents=orphan_parents,
            symlink_directories=symlink_directories,
            entry_errors=entry_errors,
            roots_scanned=scanned_root_slugs,
            roots_with_errors=roots_with_errors,
            metadata={
                "requested_root_slug": root_slug,
                "directories_scanned": total_directories_scanned,
            },
        )

    def _effective_roots(
        self,
        settings: AppSettings,
        *,
        root_slug: str | None,
    ) -> list[tuple[str, Path]]:
        roots: list[tuple[str, Path]] = []
        for setting_name, path in configured_immich_paths(settings).items():
            slug = _ROOT_SPECS.get(setting_name, setting_name)
            roots.append((slug, path))

        effective: list[tuple[str, Path]] = []
        for slug, path in roots:
            if root_slug is not None and slug != root_slug:
                continue
            is_parent = any(
                other_slug != slug and self.filesystem.is_child_path(path, other_path)
                for other_slug, other_path in roots
            )
            if is_parent and slug == "library":
                continue
            effective.append((slug, path))
        effective.sort(key=lambda item: item[0])
        return effective

    def _scan_directory(
        self,
        state: _RootScanState,
        *,
        current_path: Path,
        progress_callback: Callable[[dict[str, object]], None] | None,
    ) -> bool:
        state.directory_count += 1
        relative_path = self._relative_path(state.root_path, current_path)

        child_directories: list[Path] = []
        has_regular_file = False
        has_blocking_entries = False

        try:
            with os.scandir(current_path) as iterator:
                for entry in iterator:
                    entry_path = Path(entry.path)
                    try:
                        if entry.is_symlink():
                            has_blocking_entries = True
                            state.symlink_directories.append(
                                {
                                    "root_slug": state.root_slug,
                                    "relative_path": self._relative_path(
                                        state.root_path,
                                        entry_path,
                                    ),
                                    "absolute_path": entry.path,
                                }
                            )
                            continue
                        if entry.is_file(follow_symlinks=False):
                            has_regular_file = True
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            child_directories.append(entry_path)
                            continue
                        has_blocking_entries = True
                    except OSError as exc:
                        has_blocking_entries = True
                        state.entry_errors.append(
                            {
                                "root_slug": state.root_slug,
                                "relative_path": self._relative_path(state.root_path, entry_path),
                                "message": str(exc),
                            }
                        )
        except OSError as exc:
            message = str(exc)
            if state.error_message is None:
                state.error_message = message
            state.entry_errors.append(
                {
                    "root_slug": state.root_slug,
                    "relative_path": relative_path,
                    "message": message,
                }
            )
            return False

        children_all_empty = True
        for child_directory in sorted(child_directories):
            child_empty = self._scan_directory(
                state,
                current_path=child_directory,
                progress_callback=progress_callback,
            )
            if not child_empty:
                children_all_empty = False

        is_empty = not has_regular_file and not has_blocking_entries and children_all_empty
        if is_empty and relative_path:
            finding = self._build_finding(
                state.root_slug,
                state.root_path,
                current_path,
                child_count_before=len(child_directories),
                is_orphan_parent=bool(child_directories),
            )
            if child_directories:
                state.orphan_parents.append(finding)
            else:
                state.findings.append(finding)

        if progress_callback is not None:
            progress_callback(
                {
                    "rootSlug": state.root_slug,
                    "relativePath": relative_path,
                    "directoriesScanned": state.directory_count,
                    "emptyDirectoriesFound": len(state.findings),
                }
            )
        return is_empty

    def _build_finding(
        self,
        root_slug: str,
        root_path: Path,
        current_path: Path,
        *,
        child_count_before: int,
        is_orphan_parent: bool,
    ) -> EmptyDirectoryFinding:
        relative_path = self._relative_path(root_path, current_path)
        stat_result = self._safe_stat(current_path)
        return EmptyDirectoryFinding(
            root_slug=root_slug,
            relative_path=relative_path,
            absolute_path=current_path,
            depth=len(Path(relative_path).parts),
            size_bytes=int(stat_result.st_size) if stat_result is not None else None,
            last_modified_at=(
                datetime.fromtimestamp(stat_result.st_mtime, tz=UTC).isoformat()
                if stat_result is not None
                else None
            ),
            child_count_before=child_count_before,
            is_orphan_parent=is_orphan_parent,
        )

    def _relative_path(self, root_path: Path, target_path: Path) -> str:
        relative = target_path.relative_to(root_path).as_posix()
        return "" if relative == "." else relative

    def _safe_stat(self, path: Path) -> os.stat_result | None:
        try:
            return path.stat()
        except OSError:
            return None
