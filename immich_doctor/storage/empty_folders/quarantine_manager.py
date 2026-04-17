from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.storage.empty_folders.models import (
    EmptyDirDeleteResult,
    EmptyDirQuarantineItem,
    EmptyDirQuarantineResult,
    EmptyDirQuarantineSession,
    EmptyDirRestoreResult,
)
from immich_doctor.storage.empty_folders.scanner import EmptyFolderScanner


@dataclass(slots=True)
class EmptyDirQuarantineManager:
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    scanner: EmptyFolderScanner = field(default_factory=EmptyFolderScanner)

    def quarantine(
        self,
        settings: AppSettings,
        *,
        root_slugs: tuple[str, ...],
        paths: tuple[str, ...],
        quarantine_all: bool,
        dry_run: bool,
        reason: str = "storage empty-folder cleanup",
    ) -> EmptyDirQuarantineResult:
        scan_report = self.scanner.scan(settings)
        selected = self._select_findings(
            scan_report.findings,
            root_slugs=root_slugs,
            paths=paths,
            select_all=quarantine_all,
        )
        if not selected:
            return EmptyDirQuarantineResult(
                summary="No empty directories matched the requested quarantine selection.",
                dry_run=dry_run,
                session_id=None,
            )

        session = EmptyDirQuarantineSession.new(
            root_slugs=root_slugs,
            requested_paths=paths,
            dry_run=dry_run,
            reason=reason,
        )

        if dry_run:
            preview_items = [
                EmptyDirQuarantineItem(
                    quarantine_item_id=f"dry-run-{index}",
                    session_id=session.session_id,
                    root_slug=finding.root_slug,
                    relative_path=finding.relative_path,
                    original_path=str(finding.absolute_path),
                    quarantine_path=str(
                        self._quarantine_destination(settings, session.session_id, finding)
                    ),
                    reason=reason,
                    size_bytes=finding.size_bytes,
                    last_modified_at=finding.last_modified_at,
                )
                for index, finding in enumerate(selected, start=1)
            ]
            return EmptyDirQuarantineResult(
                summary=f"Dry-run prepared {len(preview_items)} empty directories for quarantine.",
                dry_run=True,
                session_id=session.session_id,
                items=preview_items,
            )

        items: list[EmptyDirQuarantineItem] = []
        failed: list[dict[str, str]] = []
        for finding in selected:
            source = finding.absolute_path
            destination = self._quarantine_destination(settings, session.session_id, finding)
            mode = self._safe_mode(source)
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(source.as_posix(), destination.as_posix())
                items.append(
                    EmptyDirQuarantineItem(
                        quarantine_item_id=f"{session.session_id}:{finding.root_slug}:{finding.relative_path}",
                        session_id=session.session_id,
                        root_slug=finding.root_slug,
                        relative_path=finding.relative_path,
                        original_path=str(source),
                        quarantine_path=str(destination),
                        reason=reason,
                        size_bytes=finding.size_bytes,
                        last_modified_at=finding.last_modified_at,
                        mode=mode,
                    )
                )
            except OSError as exc:
                failed.append({"path": str(source), "reason": str(exc)})

        self._ensure_storage_root(settings)
        self._write_session(settings, session)
        self._merge_index_items(settings, items)

        return EmptyDirQuarantineResult(
            summary=f"Quarantined {len(items)} empty directories.",
            dry_run=False,
            session_id=session.session_id,
            items=items,
            failed=failed,
        )

    def list_quarantined(
        self,
        settings: AppSettings,
        *,
        session_id: str | None = None,
        include_inactive: bool = False,
    ) -> list[EmptyDirQuarantineItem]:
        items = self._read_index(settings)
        if session_id is not None:
            items = [item for item in items if item.session_id == session_id]
        if not include_inactive:
            items = [item for item in items if item.state == "active"]
        items.sort(key=lambda item: (item.root_slug, item.relative_path))
        return items

    def restore(
        self,
        settings: AppSettings,
        *,
        session_id: str,
        paths: tuple[str, ...],
        restore_all: bool,
        dry_run: bool,
    ) -> EmptyDirRestoreResult:
        items = self._select_quarantine_items(
            self.list_quarantined(settings, session_id=session_id),
            paths=paths,
            select_all=restore_all,
        )
        if not items:
            return EmptyDirRestoreResult(
                summary="No quarantined empty directories matched the requested restore selection.",
                dry_run=dry_run,
            )

        if dry_run:
            return EmptyDirRestoreResult(
                summary=f"Dry-run prepared {len(items)} quarantined directories for restore.",
                dry_run=True,
                restored=items,
            )

        restored: list[EmptyDirQuarantineItem] = []
        failed: list[dict[str, str]] = []
        index_items = self._read_index(settings)
        updated_by_id = {item.quarantine_item_id: item for item in index_items}
        for item in items:
            source = Path(item.quarantine_path)
            destination = Path(item.original_path)
            if not destination.parent.exists():
                failed.append(
                    {
                        "path": item.original_path,
                        "reason": "Original parent directory is missing or inaccessible.",
                    }
                )
                continue
            if destination.exists():
                failed.append(
                    {
                        "path": item.original_path,
                        "reason": "Original path already exists.",
                    }
                )
                continue
            try:
                shutil.move(source.as_posix(), destination.as_posix())
                if item.last_modified_at is not None:
                    timestamp = self._timestamp_from_iso(item.last_modified_at)
                    os.utime(destination, (timestamp, timestamp))
                if item.mode is not None:
                    destination.chmod(item.mode)
                restored_item = item.mark_restored()
                updated_by_id[item.quarantine_item_id] = restored_item
                restored.append(restored_item)
            except OSError as exc:
                failed.append({"path": item.original_path, "reason": str(exc)})
        self._write_index(settings, list(updated_by_id.values()))
        return EmptyDirRestoreResult(
            summary=f"Restored {len(restored)} quarantined empty directories.",
            dry_run=False,
            restored=restored,
            failed=failed,
        )

    def finalize_delete(
        self,
        settings: AppSettings,
        *,
        session_id: str,
        paths: tuple[str, ...],
        delete_all: bool,
        dry_run: bool,
    ) -> EmptyDirDeleteResult:
        items = self._select_quarantine_items(
            self.list_quarantined(settings, session_id=session_id),
            paths=paths,
            select_all=delete_all,
        )
        if not items:
            return EmptyDirDeleteResult(
                summary="No quarantined empty directories matched the requested delete selection.",
                dry_run=dry_run,
            )

        if dry_run:
            return EmptyDirDeleteResult(
                summary=f"Dry-run prepared {len(items)} quarantined directories for deletion.",
                dry_run=True,
                deleted=items,
            )

        deleted: list[EmptyDirQuarantineItem] = []
        failed: list[dict[str, str]] = []
        index_items = self._read_index(settings)
        updated_by_id = {item.quarantine_item_id: item for item in index_items}
        for item in items:
            quarantine_path = Path(item.quarantine_path)
            try:
                shutil.rmtree(quarantine_path)
                deleted_item = item.mark_deleted()
                updated_by_id[item.quarantine_item_id] = deleted_item
                deleted.append(deleted_item)
            except OSError as exc:
                failed.append({"path": item.quarantine_path, "reason": str(exc)})
        self._write_index(settings, list(updated_by_id.values()))
        return EmptyDirDeleteResult(
            summary=f"Deleted {len(deleted)} quarantined empty directories permanently.",
            dry_run=False,
            deleted=deleted,
            failed=failed,
        )

    def _select_findings(
        self,
        findings,
        *,
        root_slugs: tuple[str, ...],
        paths: tuple[str, ...],
        select_all: bool,
    ):
        if select_all:
            return list(findings)
        selected = []
        normalized_roots = {item for item in root_slugs if item}
        normalized_paths = {item for item in paths if item}
        for finding in findings:
            root_matches = not normalized_roots or finding.root_slug in normalized_roots
            path_matches = not normalized_paths or (
                finding.relative_path in normalized_paths
                or str(finding.absolute_path) in normalized_paths
                or f"{finding.root_slug}:{finding.relative_path}" in normalized_paths
            )
            if root_matches and path_matches and (normalized_roots or normalized_paths):
                selected.append(finding)
        return selected

    def _select_quarantine_items(
        self,
        items: list[EmptyDirQuarantineItem],
        *,
        paths: tuple[str, ...],
        select_all: bool,
    ) -> list[EmptyDirQuarantineItem]:
        if select_all:
            return list(items)
        normalized_paths = {item for item in paths if item}
        return [
            item
            for item in items
            if normalized_paths
            and (
                item.relative_path in normalized_paths
            or item.original_path in normalized_paths
            or item.quarantine_item_id in normalized_paths
            or f"{item.root_slug}:{item.relative_path}" in normalized_paths
            )
        ]

    def _quarantine_root(self, settings: AppSettings) -> Path:
        return settings.quarantine_path / "empty-folders"

    def _quarantine_destination(
        self, settings: AppSettings, session_id: str, finding
    ) -> Path:
        relative = Path(finding.relative_path) if finding.relative_path else Path("_root")
        return (
            self._quarantine_root(settings)
            / "sessions"
            / session_id
            / finding.root_slug
            / relative
        )

    def _session_file(self, settings: AppSettings, session_id: str) -> Path:
        return self._quarantine_root(settings) / "session-index" / f"{session_id}.json"

    def _index_file(self, settings: AppSettings) -> Path:
        return self._quarantine_root(settings) / "index.json"

    def _ensure_storage_root(self, settings: AppSettings) -> None:
        self._quarantine_root(settings).mkdir(parents=True, exist_ok=True)
        self._session_file(settings, "placeholder").parent.mkdir(parents=True, exist_ok=True)

    def _write_session(self, settings: AppSettings, session: EmptyDirQuarantineSession) -> None:
        session_path = self._session_file(settings, session.session_id)
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.write_text(
            json.dumps(session.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _read_index(self, settings: AppSettings) -> list[EmptyDirQuarantineItem]:
        index_path = self._index_file(settings)
        if not index_path.exists():
            return []
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        return [EmptyDirQuarantineItem.from_dict(item) for item in payload]

    def _write_index(self, settings: AppSettings, items: list[EmptyDirQuarantineItem]) -> None:
        index_path = self._index_file(settings)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = [item.to_dict() for item in items]
        serialized.sort(key=lambda item: (str(item["root_slug"]), str(item["relative_path"])))
        index_path.write_text(
            json.dumps(serialized, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _merge_index_items(
        self,
        settings: AppSettings,
        items: list[EmptyDirQuarantineItem],
    ) -> None:
        existing = {item.quarantine_item_id: item for item in self._read_index(settings)}
        for item in items:
            existing[item.quarantine_item_id] = item
        self._write_index(settings, list(existing.values()))

    def _safe_mode(self, path: Path) -> int | None:
        try:
            return path.stat().st_mode
        except OSError:
            return None

    def _timestamp_from_iso(self, value: str) -> float:
        return datetime.fromisoformat(value).timestamp()
