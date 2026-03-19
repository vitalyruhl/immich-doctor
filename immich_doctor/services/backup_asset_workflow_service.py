from __future__ import annotations

import hashlib
import mimetypes
import os
import shutil
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.backup.targets.models import BackupTargetConfig, BackupTargetType
from immich_doctor.backup.targets.paths import (
    backup_workflow_current_library_root,
    backup_workflow_root,
    backup_workflow_test_root,
)
from immich_doctor.core.config import AppSettings
from immich_doctor.services.backup_target_settings_service import BackupTargetSettingsService


class BackupAssetComparisonStatus(StrEnum):
    PENDING = "pending"
    IDENTICAL = "identical"
    MISSING_IN_BACKUP = "missing_in_backup"
    MISMATCH = "mismatch"
    CONFLICT = "conflict"
    RESTORE_CANDIDATE = "restore_candidate"
    RESTORED = "restored"
    SKIPPED = "skipped"
    FAILED = "failed"


RESTORE_ELIGIBLE_STATUSES = {
    BackupAssetComparisonStatus.RESTORE_CANDIDATE.value,
    BackupAssetComparisonStatus.MISMATCH.value,
    BackupAssetComparisonStatus.CONFLICT.value,
}

SYNC_ELIGIBLE_STATUSES = {
    BackupAssetComparisonStatus.MISSING_IN_BACKUP.value,
}

PREVIEWABLE_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/heic"}
PREVIEWABLE_VIDEO_PREFIX = "video/"


@dataclass(slots=True, frozen=True)
class AssetSideDetails:
    exists: bool
    relative_path: str
    absolute_path: str | None
    size: int | None
    modified_at: str | None
    mime_type: str | None
    preview_kind: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "exists": self.exists,
            "relativePath": self.relative_path,
            "absolutePath": self.absolute_path,
            "size": self.size,
            "modifiedAt": self.modified_at,
            "mimeType": self.mime_type,
            "previewKind": self.preview_kind,
        }


@dataclass(slots=True, frozen=True)
class AssetComparisonRecord:
    asset_id: str
    status: BackupAssetComparisonStatus
    source: AssetSideDetails
    backup: AssetSideDetails
    comparison_method: str
    decision: str
    source_hash: str | None = None
    backup_hash: str | None = None
    details: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "assetId": self.asset_id,
            "status": self.status.value,
            "syncEligible": self.status.value in SYNC_ELIGIBLE_STATUSES,
            "restoreEligible": self.status.value in RESTORE_ELIGIBLE_STATUSES,
            "source": self.source.to_dict(),
            "backup": self.backup.to_dict(),
            "comparison": {
                "method": self.comparison_method,
                "decision": self.decision,
                "sourceHash": self.source_hash,
                "backupHash": self.backup_hash,
                "details": self.details,
            },
        }


@dataclass(slots=True)
class BackupAssetWorkflowService:
    target_settings: BackupTargetSettingsService = field(
        default_factory=BackupTargetSettingsService
    )
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    hash_chunk_size: int = 1024 * 1024

    def get_overview(
        self,
        settings: AppSettings,
        *,
        target_id: str,
        max_items: int = 250,
    ) -> dict[str, object]:
        target = self.target_settings.get_target(settings, target_id=target_id)
        source_root, backup_root, warnings = self._resolve_roots(settings, target=target)
        if source_root is None or backup_root is None:
            return self._unsupported_overview(target=target, warnings=warnings)

        source_entries = self._collect_file_entries(source_root)
        backup_entries = self._collect_file_entries(backup_root)
        records = self._compare_entries(source_entries=source_entries, backup_entries=backup_entries)

        counts = Counter(record.status.value for record in records)
        display_items = self._select_display_records(records, max_items=max_items)
        folder_summaries = self._build_folder_summaries(
            source_root=source_root,
            backup_root=backup_root,
            source_entries=source_entries,
            backup_entries=backup_entries,
        )
        suspicious_folder_count = sum(
            1 for item in folder_summaries if bool(item.get("suspicious"))
        )

        return {
            "generatedAt": datetime.now(UTC).isoformat(),
            "targetId": target.target_id,
            "targetType": target.target_type.value,
            "supported": True,
            "sourceRoot": source_root.as_posix(),
            "backupRoot": backup_root.as_posix(),
            "summary": self._overview_summary(counts),
            "warnings": warnings,
            "limitations": [
                "Asset-aware check, sync, test copy, preview, and selective restore are currently local-target only.",
                "Directory totals are heuristic warning signals and not proof of integrity on their own.",
                "Only suspicious same-size files are hashed during normal comparison; no global deep verification is claimed.",
            ],
            "comparison": {
                "totalItems": len(records),
                "statusCounts": {status.value: counts.get(status.value, 0) for status in BackupAssetComparisonStatus},
                "displayedItems": len(display_items),
                "truncated": len(display_items) < len(records),
                "items": [record.to_dict() for record in display_items],
            },
            "folders": {
                "suspiciousCount": suspicious_folder_count,
                "items": folder_summaries,
            },
        }

    def sync_missing(
        self,
        settings: AppSettings,
        *,
        target_id: str,
    ) -> dict[str, object]:
        target = self.target_settings.get_target(settings, target_id=target_id)
        source_root, backup_root, warnings = self._resolve_roots(settings, target=target)
        if source_root is None or backup_root is None:
            return {
                "state": "unsupported",
                "summary": "Asset-aware check/sync is only available for local targets.",
                "warnings": warnings,
                "report": {
                    "statusCounts": {},
                    "copiedCount": 0,
                    "verifiedCount": 0,
                    "results": [],
                    "backupRoot": None,
                },
            }

        source_entries = self._collect_file_entries(source_root)
        backup_entries = self._collect_file_entries(backup_root)
        records = self._compare_entries(source_entries=source_entries, backup_entries=backup_entries)
        counts = Counter(record.status.value for record in records)
        sync_records = [
            record
            for record in records
            if record.status == BackupAssetComparisonStatus.MISSING_IN_BACKUP
        ]

        results: list[dict[str, object]] = []
        copied_count = 0
        verified_count = 0
        failures = 0
        for record in sync_records:
            source_path = source_root / record.asset_id
            backup_path = backup_root / record.asset_id
            result = self._copy_with_verification(
                source_path=source_path,
                target_path=backup_path,
                action="sync_missing",
                asset_id=record.asset_id,
            )
            results.append(result)
            if result["resultStatus"] == BackupAssetComparisonStatus.RESTORED.value:
                copied_count += 1
                if result["verified"]:
                    verified_count += 1
            elif result["resultStatus"] == BackupAssetComparisonStatus.FAILED.value:
                failures += 1

        mismatch_count = counts.get(BackupAssetComparisonStatus.MISMATCH.value, 0)
        conflict_count = counts.get(BackupAssetComparisonStatus.CONFLICT.value, 0)
        restore_candidate_count = counts.get(
            BackupAssetComparisonStatus.RESTORE_CANDIDATE.value,
            0,
        )
        state = "completed"
        if failures > 0:
            state = "failed" if copied_count == 0 else "partial"
        elif mismatch_count or conflict_count or restore_candidate_count:
            state = "partial"

        sample_records = [
            record.to_dict()
            for record in records
            if record.status
            in {
                BackupAssetComparisonStatus.MISMATCH,
                BackupAssetComparisonStatus.CONFLICT,
                BackupAssetComparisonStatus.RESTORE_CANDIDATE,
            }
        ][:25]

        return {
            "state": state,
            "summary": self._sync_summary(
                copied_count=copied_count,
                verified_count=verified_count,
                mismatch_count=mismatch_count,
                conflict_count=conflict_count,
                restore_candidate_count=restore_candidate_count,
            ),
            "warnings": warnings,
            "report": {
                "sourceRoot": source_root.as_posix(),
                "backupRoot": backup_root.as_posix(),
                "statusCounts": {status.value: counts.get(status.value, 0) for status in BackupAssetComparisonStatus},
                "copiedCount": copied_count,
                "verifiedCount": verified_count,
                "results": results,
                "reviewItems": sample_records,
            },
        }

    def run_test_copy(
        self,
        settings: AppSettings,
        *,
        target_id: str,
    ) -> dict[str, object]:
        target = self.target_settings.get_target(settings, target_id=target_id)
        source_root, backup_root, warnings = self._resolve_roots(settings, target=target)
        if source_root is None or backup_root is None:
            return {
                "generatedAt": datetime.now(UTC).isoformat(),
                "targetId": target_id,
                "supported": False,
                "summary": "Test copy is only available for local targets.",
                "warnings": warnings,
                "result": None,
            }

        source_entries = self._collect_file_entries(source_root)
        if not source_entries:
            return {
                "generatedAt": datetime.now(UTC).isoformat(),
                "targetId": target_id,
                "supported": True,
                "summary": "Test copy cannot run because no source asset was found.",
                "warnings": warnings,
                "result": {
                    "assetId": None,
                    "sourcePath": None,
                    "targetPath": None,
                    "copied": False,
                    "verified": False,
                    "verificationMethod": "sha256",
                    "error": "No source file is available for a representative copy test.",
                    "details": {},
                },
            }

        asset_id = sorted(source_entries.keys())[0]
        source_path = source_root / asset_id
        test_root = backup_workflow_test_root(Path(target.transport.path))
        test_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        target_path = test_root / test_id / asset_id
        result = self._copy_with_verification(
            source_path=source_path,
            target_path=target_path,
            action="test_copy",
            asset_id=asset_id,
        )
        cleaned_up = False
        if result["resultStatus"] == BackupAssetComparisonStatus.RESTORED.value:
            try:
                target_path.unlink(missing_ok=True)
                self._remove_empty_parents(target_path.parent, stop_at=test_root)
                cleaned_up = True
            except OSError:
                cleaned_up = False
        details = dict(result["details"])
        details["cleanedUpAfterVerification"] = cleaned_up
        result["details"] = details
        result["targetPath"] = target_path.as_posix()
        result["copied"] = result["resultStatus"] == BackupAssetComparisonStatus.RESTORED.value

        return {
            "generatedAt": datetime.now(UTC).isoformat(),
            "targetId": target_id,
            "supported": True,
            "summary": (
                "Representative test copy completed and verified."
                if result["verified"]
                else "Representative test copy failed."
            ),
            "warnings": warnings,
            "result": result,
        }

    def restore_items(
        self,
        settings: AppSettings,
        *,
        target_id: str,
        asset_ids: list[str],
        apply: bool,
    ) -> dict[str, object]:
        target = self.target_settings.get_target(settings, target_id=target_id)
        source_root, backup_root, warnings = self._resolve_roots(settings, target=target)
        if source_root is None or backup_root is None:
            return {
                "generatedAt": datetime.now(UTC).isoformat(),
                "targetId": target_id,
                "apply": apply,
                "supported": False,
                "summary": "Selective restore is only available for local targets.",
                "warnings": warnings,
                "results": [],
            }

        source_entries = self._collect_file_entries(source_root)
        backup_entries = self._collect_file_entries(backup_root)
        by_id = {
            record.asset_id: record
            for record in self._compare_entries(
                source_entries=source_entries,
                backup_entries=backup_entries,
            )
        }
        results: list[dict[str, object]] = []
        restored_count = 0
        failed_count = 0
        skipped_count = 0
        for asset_id in asset_ids:
            record = by_id.get(asset_id)
            if record is None:
                results.append(
                    self._restore_result(
                        asset_id=asset_id,
                        source_path=(source_root / asset_id),
                        backup_path=(backup_root / asset_id),
                        result_status=BackupAssetComparisonStatus.SKIPPED,
                        outcome="not_found_in_review",
                        reason="Selected item is no longer present in the current review result.",
                        apply=apply,
                    )
                )
                skipped_count += 1
                continue
            if record.status.value not in RESTORE_ELIGIBLE_STATUSES:
                results.append(
                    self._restore_result(
                        asset_id=asset_id,
                        source_path=(source_root / asset_id),
                        backup_path=(backup_root / asset_id),
                        result_status=BackupAssetComparisonStatus.SKIPPED,
                        outcome="not_eligible",
                        reason=f"Status `{record.status.value}` is not eligible for restore.",
                        apply=apply,
                    )
                )
                skipped_count += 1
                continue
            if not apply:
                results.append(
                    self._restore_result(
                        asset_id=asset_id,
                        source_path=(source_root / asset_id),
                        backup_path=(backup_root / asset_id),
                        result_status=BackupAssetComparisonStatus.SKIPPED,
                        outcome="planned",
                        reason="Dry-run only. No source file was modified.",
                        apply=False,
                    )
                )
                skipped_count += 1
                continue
            result = self._restore_one(
                settings,
                asset_id=asset_id,
                source_path=source_root / asset_id,
                backup_path=backup_root / asset_id,
            )
            results.append(result)
            if result["resultStatus"] == BackupAssetComparisonStatus.RESTORED.value:
                restored_count += 1
            elif result["resultStatus"] == BackupAssetComparisonStatus.FAILED.value:
                failed_count += 1
            else:
                skipped_count += 1

        return {
            "generatedAt": datetime.now(UTC).isoformat(),
            "targetId": target_id,
            "apply": apply,
            "supported": True,
            "summary": self._restore_summary(
                apply=apply,
                selected_count=len(asset_ids),
                restored_count=restored_count,
                failed_count=failed_count,
                skipped_count=skipped_count,
            ),
            "warnings": warnings,
            "results": results,
        }

    def resolve_preview_file(
        self,
        settings: AppSettings,
        *,
        target_id: str,
        side: str,
        asset_id: str,
    ) -> tuple[Path, str]:
        target = self.target_settings.get_target(settings, target_id=target_id)
        source_root, backup_root, warnings = self._resolve_roots(settings, target=target)
        if source_root is None or backup_root is None:
            raise FileNotFoundError("Preview is not supported for this target.")
        if warnings and target.target_type != BackupTargetType.LOCAL:
            raise FileNotFoundError("Preview is not supported for this target.")

        root = source_root if side == "source" else backup_root
        path = self._safe_child_path(root, asset_id)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Preview file not found for `{asset_id}`.")
        mime_type, _ = mimetypes.guess_type(path.name)
        if not self._preview_kind(mime_type):
            raise FileNotFoundError("Preview is not available for this file type.")
        return path, mime_type or "application/octet-stream"

    def _resolve_roots(
        self,
        settings: AppSettings,
        *,
        target: BackupTargetConfig,
    ) -> tuple[Path | None, Path | None, list[str]]:
        warnings = list(target.warnings)
        if target.target_type != BackupTargetType.LOCAL or target.transport.path is None:
            warnings.append(
                "Asset-aware local workflow is unavailable because the selected target is not a local filesystem target."
            )
            return None, None, warnings
        if settings.immich_library_root is None:
            warnings.append("IMMICH library root is not configured.")
            return None, None, warnings

        source_root = settings.immich_library_root.expanduser()
        target_root = Path(target.transport.path).expanduser()
        backup_root = backup_workflow_current_library_root(target_root)
        if self.filesystem.is_child_path(source_root, target_root) or self.filesystem.is_child_path(
            target_root,
            source_root,
        ):
            warnings.append(
                "Source and backup target paths overlap. Asset-aware sync/restore is blocked to avoid recursive or destructive copies."
            )
            return None, None, warnings
        backup_root.mkdir(parents=True, exist_ok=True)
        backup_workflow_root(target_root).mkdir(parents=True, exist_ok=True)
        return source_root, backup_root, warnings

    def _unsupported_overview(
        self,
        *,
        target: BackupTargetConfig,
        warnings: list[str],
    ) -> dict[str, object]:
        return {
            "generatedAt": datetime.now(UTC).isoformat(),
            "targetId": target.target_id,
            "targetType": target.target_type.value,
            "supported": False,
            "sourceRoot": None,
            "backupRoot": None,
            "summary": "Asset-aware check / sync / restore is only available for local targets in this phase.",
            "warnings": warnings,
            "limitations": [
                "Remote targets keep their existing conservative validation and files-only execution behavior.",
                "No asset preview or selective restore is claimed for unsupported target types.",
            ],
            "comparison": {
                "totalItems": 0,
                "statusCounts": {status.value: 0 for status in BackupAssetComparisonStatus},
                "displayedItems": 0,
                "truncated": False,
                "items": [],
            },
            "folders": {
                "suspiciousCount": 0,
                "items": [],
            },
        }

    def _collect_file_entries(self, root: Path) -> dict[str, Path]:
        entries: dict[str, Path] = {}
        if not root.exists():
            return entries
        for current_root, _, filenames in os.walk(root):
            base = Path(current_root)
            for filename in filenames:
                path = base / filename
                relative_path = path.relative_to(root).as_posix()
                entries[relative_path] = path
        return entries

    def _compare_entries(
        self,
        *,
        source_entries: dict[str, Path],
        backup_entries: dict[str, Path],
    ) -> list[AssetComparisonRecord]:
        records: list[AssetComparisonRecord] = []
        for asset_id in sorted(set(source_entries) | set(backup_entries)):
            source_path = source_entries.get(asset_id)
            backup_path = backup_entries.get(asset_id)
            records.append(self._compare_one(asset_id, source_path=source_path, backup_path=backup_path))
        return records

    def _compare_one(
        self,
        asset_id: str,
        *,
        source_path: Path | None,
        backup_path: Path | None,
    ) -> AssetComparisonRecord:
        source_side = self._side_details(asset_id=asset_id, path=source_path)
        backup_side = self._side_details(asset_id=asset_id, path=backup_path)
        if source_path is None and backup_path is not None:
            return AssetComparisonRecord(
                asset_id=asset_id,
                status=BackupAssetComparisonStatus.RESTORE_CANDIDATE,
                source=source_side,
                backup=backup_side,
                comparison_method="existence",
                decision="backup_only_restore_candidate",
                details={"reason": "Backup copy exists but source asset is missing."},
            )
        if source_path is not None and backup_path is None:
            return AssetComparisonRecord(
                asset_id=asset_id,
                status=BackupAssetComparisonStatus.MISSING_IN_BACKUP,
                source=source_side,
                backup=backup_side,
                comparison_method="existence",
                decision="copy_missing_to_backup",
                details={"reason": "Source asset is missing in backup."},
            )
        if source_path is None or backup_path is None:
            return AssetComparisonRecord(
                asset_id=asset_id,
                status=BackupAssetComparisonStatus.CONFLICT,
                source=source_side,
                backup=backup_side,
                comparison_method="existence",
                decision="manual_review_required",
                details={"reason": "Comparison inputs are incomplete."},
            )

        source_stat = source_path.stat()
        backup_stat = backup_path.stat()
        details = {
            "sourceSize": source_stat.st_size,
            "backupSize": backup_stat.st_size,
            "sourceTimestamp": self._iso_from_timestamp(source_stat.st_mtime),
            "backupTimestamp": self._iso_from_timestamp(backup_stat.st_mtime),
        }
        if source_stat.st_size != backup_stat.st_size:
            return AssetComparisonRecord(
                asset_id=asset_id,
                status=BackupAssetComparisonStatus.MISMATCH,
                source=source_side,
                backup=backup_side,
                comparison_method="size",
                decision="size_mismatch",
                details=details,
            )
        if source_stat.st_mtime_ns == backup_stat.st_mtime_ns:
            return AssetComparisonRecord(
                asset_id=asset_id,
                status=BackupAssetComparisonStatus.IDENTICAL,
                source=source_side,
                backup=backup_side,
                comparison_method="size+mtime",
                decision="skip_identical",
                details=details,
            )
        try:
            source_hash = self._hash_file(source_path)
            backup_hash = self._hash_file(backup_path)
        except OSError as exc:
            details["error"] = str(exc)
            return AssetComparisonRecord(
                asset_id=asset_id,
                status=BackupAssetComparisonStatus.CONFLICT,
                source=source_side,
                backup=backup_side,
                comparison_method="size+mtime+hash",
                decision="hash_failed_manual_review",
                details=details,
            )
        if source_hash == backup_hash:
            return AssetComparisonRecord(
                asset_id=asset_id,
                status=BackupAssetComparisonStatus.IDENTICAL,
                source=source_side,
                backup=backup_side,
                comparison_method="size+mtime+sha256",
                decision="skip_identical_after_hash",
                source_hash=source_hash,
                backup_hash=backup_hash,
                details=details,
            )
        return AssetComparisonRecord(
            asset_id=asset_id,
            status=BackupAssetComparisonStatus.MISMATCH,
            source=source_side,
            backup=backup_side,
            comparison_method="size+mtime+sha256",
            decision="hash_mismatch",
            source_hash=source_hash,
            backup_hash=backup_hash,
            details=details,
        )

    def _side_details(self, *, asset_id: str, path: Path | None) -> AssetSideDetails:
        if path is None or not path.exists():
            mime_type = mimetypes.guess_type(asset_id)[0]
            return AssetSideDetails(
                exists=False,
                relative_path=asset_id,
                absolute_path=None,
                size=None,
                modified_at=None,
                mime_type=mime_type,
                preview_kind=self._preview_kind(mime_type),
            )
        stat_result = path.stat()
        mime_type, _ = mimetypes.guess_type(path.name)
        return AssetSideDetails(
            exists=True,
            relative_path=asset_id,
            absolute_path=path.as_posix(),
            size=stat_result.st_size,
            modified_at=self._iso_from_timestamp(stat_result.st_mtime),
            mime_type=mime_type,
            preview_kind=self._preview_kind(mime_type),
        )

    def _select_display_records(
        self,
        records: list[AssetComparisonRecord],
        *,
        max_items: int,
    ) -> list[AssetComparisonRecord]:
        priority = {
            BackupAssetComparisonStatus.RESTORE_CANDIDATE.value: 0,
            BackupAssetComparisonStatus.MISMATCH.value: 1,
            BackupAssetComparisonStatus.CONFLICT.value: 2,
            BackupAssetComparisonStatus.MISSING_IN_BACKUP.value: 3,
            BackupAssetComparisonStatus.IDENTICAL.value: 4,
            BackupAssetComparisonStatus.PENDING.value: 5,
            BackupAssetComparisonStatus.RESTORED.value: 6,
            BackupAssetComparisonStatus.SKIPPED.value: 7,
            BackupAssetComparisonStatus.FAILED.value: 8,
        }
        return sorted(
            records,
            key=lambda record: (priority.get(record.status.value, 99), record.asset_id),
        )[:max_items]

    def _build_folder_summaries(
        self,
        *,
        source_root: Path,
        backup_root: Path,
        source_entries: dict[str, Path],
        backup_entries: dict[str, Path],
    ) -> list[dict[str, object]]:
        source_stats = self._aggregate_by_folder(source_root, source_entries)
        backup_stats = self._aggregate_by_folder(backup_root, backup_entries)
        items: list[dict[str, object]] = []
        for folder in sorted(set(source_stats) | set(backup_stats)):
            source = source_stats.get(folder, {"fileCount": 0, "totalBytes": 0})
            backup = backup_stats.get(folder, {"fileCount": 0, "totalBytes": 0})
            file_delta = int(source["fileCount"]) - int(backup["fileCount"])
            size_delta = int(source["totalBytes"]) - int(backup["totalBytes"])
            suspicious_reasons: list[str] = []
            if file_delta != 0:
                suspicious_reasons.append("file_count_differs")
            if size_delta != 0:
                suspicious_reasons.append("total_size_differs")
            items.append(
                {
                    "folder": folder,
                    "sourceFileCount": source["fileCount"],
                    "backupFileCount": backup["fileCount"],
                    "sourceTotalBytes": source["totalBytes"],
                    "backupTotalBytes": backup["totalBytes"],
                    "fileDelta": file_delta,
                    "sizeDeltaBytes": size_delta,
                    "suspicious": bool(suspicious_reasons),
                    "reasons": suspicious_reasons,
                }
            )
        return items

    def _aggregate_by_folder(
        self,
        root: Path,
        entries: dict[str, Path],
    ) -> dict[str, dict[str, int]]:
        del root
        result: dict[str, dict[str, int]] = {}
        for relative_path, path in entries.items():
            folder = Path(relative_path).parts[0] if Path(relative_path).parts else "."
            bucket = result.setdefault(folder, {"fileCount": 0, "totalBytes": 0})
            bucket["fileCount"] += 1
            bucket["totalBytes"] += path.stat().st_size
        return result

    def _copy_with_verification(
        self,
        *,
        source_path: Path,
        target_path: Path,
        action: str,
        asset_id: str,
    ) -> dict[str, object]:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(source_path, target_path)
            source_hash = self._hash_file(source_path)
            target_hash = self._hash_file(target_path)
            verified = source_hash == target_hash
            return {
                "assetId": asset_id,
                "sourcePath": source_path.as_posix(),
                "targetPath": target_path.as_posix(),
                "actionAttempted": action,
                "actionOutcome": "copied" if verified else "copied_with_hash_mismatch",
                "resultStatus": (
                    BackupAssetComparisonStatus.RESTORED.value
                    if verified
                    else BackupAssetComparisonStatus.FAILED.value
                ),
                "copied": True,
                "verified": verified,
                "verificationMethod": "sha256",
                "error": None if verified else "Hash verification failed after copy.",
                "details": {
                    "sourceSize": source_path.stat().st_size,
                    "targetSize": target_path.stat().st_size,
                    "sourceTimestamp": self._iso_from_timestamp(source_path.stat().st_mtime),
                    "targetTimestamp": self._iso_from_timestamp(target_path.stat().st_mtime),
                    "sourceHash": source_hash,
                    "targetHash": target_hash,
                },
            }
        except OSError as exc:
            return {
                "assetId": asset_id,
                "sourcePath": source_path.as_posix(),
                "targetPath": target_path.as_posix(),
                "actionAttempted": action,
                "actionOutcome": "failed",
                "resultStatus": BackupAssetComparisonStatus.FAILED.value,
                "copied": False,
                "verified": False,
                "verificationMethod": "sha256",
                "error": str(exc),
                "details": {},
            }

    def _restore_one(
        self,
        settings: AppSettings,
        *,
        asset_id: str,
        source_path: Path,
        backup_path: Path,
    ) -> dict[str, object]:
        if not backup_path.exists():
            return self._restore_result(
                asset_id=asset_id,
                source_path=source_path,
                backup_path=backup_path,
                result_status=BackupAssetComparisonStatus.FAILED,
                outcome="backup_missing",
                reason="Backup copy is missing.",
                apply=True,
            )

        quarantine_path: Path | None = None
        quarantine_root = settings.quarantine_path / "backup-restore-overwrite" / datetime.now(
            UTC
        ).strftime("%Y%m%dT%H%M%SZ")
        temp_restore_path = source_path.with_name(f"{source_path.name}.immich-doctor-restore.tmp")
        source_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if source_path.exists():
                quarantine_path = quarantine_root / asset_id
                quarantine_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(source_path.as_posix(), quarantine_path.as_posix())
            shutil.copy2(backup_path, temp_restore_path)
            os.replace(temp_restore_path, source_path)
            source_hash = self._hash_file(source_path)
            backup_hash = self._hash_file(backup_path)
            if source_hash != backup_hash:
                raise OSError("Post-restore hash verification failed.")
            return self._restore_result(
                asset_id=asset_id,
                source_path=source_path,
                backup_path=backup_path,
                result_status=BackupAssetComparisonStatus.RESTORED,
                outcome="restored",
                reason="Backup file restored into source storage.",
                apply=True,
                quarantine_path=quarantine_path,
                details={
                    "verificationMethod": "sha256",
                    "sourceHash": source_hash,
                    "backupHash": backup_hash,
                },
            )
        except OSError as exc:
            try:
                if temp_restore_path.exists():
                    temp_restore_path.unlink(missing_ok=True)
            except OSError:
                pass
            rollback_restored = False
            rollback_error: str | None = None
            if quarantine_path is not None and quarantine_path.exists() and not source_path.exists():
                try:
                    source_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(quarantine_path.as_posix(), source_path.as_posix())
                    rollback_restored = True
                except OSError as rollback_exc:
                    rollback_error = str(rollback_exc)
            return self._restore_result(
                asset_id=asset_id,
                source_path=source_path,
                backup_path=backup_path,
                result_status=BackupAssetComparisonStatus.FAILED,
                outcome="restore_failed",
                reason=str(exc),
                apply=True,
                quarantine_path=quarantine_path,
                details={
                    "rollbackRestoredSource": rollback_restored,
                    "rollbackError": rollback_error,
                },
            )

    def _restore_result(
        self,
        *,
        asset_id: str,
        source_path: Path,
        backup_path: Path,
        result_status: BackupAssetComparisonStatus,
        outcome: str,
        reason: str,
        apply: bool,
        quarantine_path: Path | None = None,
        details: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return {
            "assetId": asset_id,
            "sourcePath": source_path.as_posix(),
            "backupPath": backup_path.as_posix(),
            "actionAttempted": "restore_overwrite" if apply else "restore_dry_run",
            "actionOutcome": outcome,
            "resultStatus": result_status.value,
            "reason": reason,
            "quarantinePath": quarantine_path.as_posix() if quarantine_path is not None else None,
            "details": details or {},
        }

    def _hash_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(self.hash_chunk_size)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _overview_summary(self, counts: Counter[str]) -> str:
        if sum(counts.values()) == 0:
            return "No source or backup assets were found for comparison."
        return (
            f"{counts.get(BackupAssetComparisonStatus.IDENTICAL.value, 0)} identical, "
            f"{counts.get(BackupAssetComparisonStatus.MISSING_IN_BACKUP.value, 0)} missing in backup, "
            f"{counts.get(BackupAssetComparisonStatus.MISMATCH.value, 0)} mismatches, "
            f"{counts.get(BackupAssetComparisonStatus.CONFLICT.value, 0)} conflicts, "
            f"{counts.get(BackupAssetComparisonStatus.RESTORE_CANDIDATE.value, 0)} restore candidates."
        )

    def _sync_summary(
        self,
        *,
        copied_count: int,
        verified_count: int,
        mismatch_count: int,
        conflict_count: int,
        restore_candidate_count: int,
    ) -> str:
        return (
            f"Check/sync copied {copied_count} missing assets and verified {verified_count}. "
            f"{mismatch_count} mismatches, {conflict_count} conflicts, and {restore_candidate_count} restore candidates still require review."
        )

    def _restore_summary(
        self,
        *,
        apply: bool,
        selected_count: int,
        restored_count: int,
        failed_count: int,
        skipped_count: int,
    ) -> str:
        if not apply:
            return (
                f"Restore dry-run reviewed {selected_count} selected items. "
                f"{skipped_count} items were planned only; no source files were changed."
            )
        return (
            f"Selective restore processed {selected_count} selected items: "
            f"{restored_count} restored, {failed_count} failed, {skipped_count} skipped."
        )

    def _preview_kind(self, mime_type: str | None) -> str | None:
        if mime_type in PREVIEWABLE_IMAGE_TYPES:
            return "image"
        if mime_type is not None and mime_type.startswith(PREVIEWABLE_VIDEO_PREFIX):
            return "video"
        return None

    def _iso_from_timestamp(self, value: float) -> str:
        return datetime.fromtimestamp(value, tz=UTC).isoformat()

    def _safe_child_path(self, root: Path, relative_path: str) -> Path:
        candidate = (root / relative_path).resolve()
        resolved_root = root.resolve()
        candidate.relative_to(resolved_root)
        return candidate

    def _remove_empty_parents(self, current: Path, *, stop_at: Path) -> None:
        while current != stop_at and current.exists():
            try:
                current.rmdir()
            except OSError:
                return
            current = current.parent
