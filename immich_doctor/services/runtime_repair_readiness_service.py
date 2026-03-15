from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus


@dataclass(slots=True)
class RuntimeRepairReadinessService:
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)

    def run(self, settings: AppSettings) -> dict[str, object]:
        checks = self._checks(settings)
        blocking_reasons = [
            check.message for check in checks if check.details.get("blocking") is True
        ]
        return {
            "generatedAt": datetime.now(UTC).isoformat(),
            "action": "fix_permissions",
            "applyAllowed": not blocking_reasons,
            "blockingReasons": blocking_reasons,
            "preconditions": [
                {
                    "id": check.name,
                    "label": check.name.replace("_", " "),
                    "status": self._ui_state(check.status),
                    "blocking": bool(check.details.get("blocking")),
                    "summary": check.message,
                    "details": check.details,
                }
                for check in checks
            ],
            "snapshotPlan": {
                "kind": "pre_repair",
                "coverage": "files_only",
                "willCreate": True,
                "note": "Integrated runtime apply creates a files-only pre-repair snapshot first.",
            },
            "undoVisibility": {
                "journalUndoAvailable": True,
                "automatedUndo": False,
                "note": "Undo is visible through journal data, but not automated yet.",
            },
            "restoreImplemented": False,
            "limitations": [
                "Snapshots are currently files-only.",
                "Full restore orchestration is not implemented yet.",
            ],
        }

    def _checks(self, settings: AppSettings) -> list[CheckResult]:
        checks: list[CheckResult] = []

        if settings.immich_library_root is None:
            checks.append(
                CheckResult(
                    name="immich_library_root",
                    status=CheckStatus.FAIL,
                    message="Immich library root is not configured.",
                    details={"blocking": True},
                )
            )
        else:
            checks.append(
                self._mark_blocking(
                    self.filesystem.validate_directory(
                        "immich_library_root",
                        settings.immich_library_root,
                    )
                )
            )
            checks.append(
                self._mark_blocking(
                    self.filesystem.validate_readable_directory(
                        "immich_library_root_readable",
                        settings.immich_library_root,
                    )
                )
            )

        if settings.backup_target_path is None:
            checks.append(
                CheckResult(
                    name="backup_target_path",
                    status=CheckStatus.FAIL,
                    message="Backup target path is not configured.",
                    details={"blocking": True},
                )
            )
        else:
            checks.append(
                self._mark_blocking(
                    self.filesystem.validate_directory(
                        "backup_target_path",
                        settings.backup_target_path,
                    )
                )
            )
            checks.append(
                self._mark_blocking(
                    self.filesystem.validate_writable_directory(
                        "backup_target_path_writable",
                        settings.backup_target_path,
                    )
                )
            )

        checks.append(
            self._mark_blocking(
                self.filesystem.validate_creatable_directory(
                    "manifests_path_ready",
                    settings.manifests_path,
                )
            )
        )
        checks.append(
            CheckResult(
                name="quarantine_foundation",
                status=self.filesystem.validate_creatable_directory(
                    "quarantine_foundation",
                    settings.quarantine_path,
                ).status,
                message=("Quarantine foundation path is available for future move workflows."),
                details={"blocking": False, "path": str(settings.quarantine_path)},
            )
        )
        checks.append(
            CheckResult(
                name="restore_orchestration",
                status=CheckStatus.SKIP,
                message="Full restore orchestration is not implemented yet.",
                details={"blocking": False},
            )
        )
        return checks

    def _mark_blocking(self, check: CheckResult) -> CheckResult:
        details = dict(check.details)
        details["blocking"] = check.status == CheckStatus.FAIL
        return CheckResult(
            name=check.name,
            status=check.status,
            message=check.message,
            details=details,
        )

    def _ui_state(self, status: CheckStatus) -> str:
        mapping = {
            CheckStatus.PASS: "ok",
            CheckStatus.WARN: "warning",
            CheckStatus.FAIL: "error",
            CheckStatus.SKIP: "unknown",
        }
        return mapping[status]
