from __future__ import annotations

import json
from dataclasses import dataclass, field

from immich_doctor.adapters.external_tools import ExternalToolsAdapter
from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.backup.core.models import SnapshotCoverage, SnapshotKind
from immich_doctor.backup.core.store import BackupSnapshotStore
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport


@dataclass(slots=True)
class BackupVerifyService:
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    external_tools: ExternalToolsAdapter = field(default_factory=ExternalToolsAdapter)
    snapshot_store: BackupSnapshotStore = field(default_factory=BackupSnapshotStore)

    def run(self, settings: AppSettings) -> ValidationReport:
        checks: list[CheckResult] = []

        if settings.backup_target_path is None:
            checks.append(
                CheckResult(
                    name="backup_target_configured",
                    status=CheckStatus.FAIL,
                    message="Backup target path is not configured.",
                )
            )
        else:
            checks.append(
                CheckResult(
                    name="backup_target_configured",
                    status=CheckStatus.PASS,
                    message="Backup target path is configured.",
                    details={"path": str(settings.backup_target_path)},
                )
            )
            checks.append(
                self.filesystem.validate_directory(
                    name="backup_target_path",
                    path=settings.backup_target_path,
                )
            )
            checks.append(
                self.filesystem.validate_readable_directory(
                    name="backup_target_path_readable",
                    path=settings.backup_target_path,
                )
            )
            checks.append(
                self.filesystem.validate_writable_directory(
                    name="backup_target_path_writable",
                    path=settings.backup_target_path,
                )
            )
            checks.extend(self._snapshot_checks(settings))

        if settings.required_external_tools:
            checks.extend(
                self.external_tools.validate_required_tools(settings.required_external_tools)
            )
        else:
            checks.append(
                CheckResult(
                    name="required_external_tools",
                    status=CheckStatus.SKIP,
                    message="No required external tools configured.",
                )
            )

        return ValidationReport(
            domain="backup",
            action="verify",
            summary="Backup verification completed.",
            checks=checks,
            metadata={"environment": settings.environment},
        )

    def _snapshot_checks(self, settings: AppSettings) -> list[CheckResult]:
        manifest_paths = self.snapshot_store.list_snapshot_manifest_paths(settings)
        if not manifest_paths:
            return [
                CheckResult(
                    name="backup_snapshot_manifests",
                    status=CheckStatus.SKIP,
                    message="No persisted backup snapshot manifests found yet.",
                )
            ]

        checks: list[CheckResult] = [
            CheckResult(
                name="backup_snapshot_manifests",
                status=CheckStatus.PASS,
                message=f"Found {len(manifest_paths)} persisted backup snapshot manifests.",
                details={"count": len(manifest_paths)},
            )
        ]
        valid = True
        for manifest_path in manifest_paths:
            try:
                snapshot = self.snapshot_store.load_snapshot_from_path(manifest_path)
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                valid = False
                checks.append(
                    CheckResult(
                        name=f"backup_snapshot_manifest:{manifest_path.stem}",
                        status=CheckStatus.FAIL,
                        message="Snapshot manifest could not be parsed safely.",
                        details={
                            "manifest_path": manifest_path.as_posix(),
                            "error": str(exc),
                        },
                    )
                )
                continue

            consistency_error = self._snapshot_consistency_error(snapshot)
            if consistency_error is not None:
                valid = False
                checks.append(
                    CheckResult(
                        name=f"backup_snapshot:{snapshot.snapshot_id}",
                        status=CheckStatus.FAIL,
                        message=consistency_error,
                        details={
                            "snapshot_id": snapshot.snapshot_id,
                            "kind": snapshot.kind.value,
                            "coverage": snapshot.coverage.value,
                            "manifest_path": snapshot.manifest_path.as_posix(),
                        },
                    )
                )
                continue

            checks.append(
                CheckResult(
                    name=f"backup_snapshot:{snapshot.snapshot_id}",
                    status=CheckStatus.PASS,
                    message="Snapshot manifest structure is consistent with declared coverage.",
                    details={
                        "snapshot_id": snapshot.snapshot_id,
                        "kind": snapshot.kind.value,
                        "coverage": snapshot.coverage.value,
                        "manifest_path": snapshot.manifest_path.as_posix(),
                        "repair_run_id": snapshot.repair_run_id,
                    },
                )
            )

        if valid:
            checks.append(
                CheckResult(
                    name="backup_snapshot_reference_integrity",
                    status=CheckStatus.PASS,
                    message="Snapshot manifests passed current structural integrity checks.",
                )
            )
        return checks

    def _snapshot_consistency_error(self, snapshot) -> str | None:
        return snapshot_consistency_error(snapshot)


def snapshot_consistency_error(snapshot) -> str | None:
    if snapshot.manifest_path.suffix != ".json":
        return "Snapshot manifest path must point to a JSON file."

    if snapshot.kind in {SnapshotKind.PRE_REPAIR, SnapshotKind.POST_REPAIR}:
        if snapshot.repair_run_id is None:
            return "Repair-classified snapshots must reference a repair run ID."

    if snapshot.kind not in {
        SnapshotKind.PRE_REPAIR,
        SnapshotKind.POST_REPAIR,
        SnapshotKind.PERIODIC,
        SnapshotKind.MANUAL,
    }:
        return "Snapshot kind is unsupported."

    if snapshot.coverage == SnapshotCoverage.FILES_ONLY:
        if not snapshot.file_artifacts or snapshot.db_artifact is not None:
            return "Files-only snapshot must contain file artifacts and no db artifact."
        return None
    if snapshot.coverage == SnapshotCoverage.DB_ONLY:
        if snapshot.file_artifacts or snapshot.db_artifact is None:
            return "DB-only snapshot must contain exactly one db artifact."
        return None
    if snapshot.coverage == SnapshotCoverage.PAIRED:
        if not snapshot.file_artifacts or snapshot.db_artifact is None:
            return "Paired snapshot must contain both file artifacts and a db artifact."
        return None
    return "Snapshot coverage is unsupported."
