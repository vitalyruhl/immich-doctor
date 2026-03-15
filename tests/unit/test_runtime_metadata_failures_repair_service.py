from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from immich_doctor.backup.core.models import (
    BackupContext,
    BackupResult,
    BackupSnapshot,
    BackupTarget,
    SnapshotCoverage,
    SnapshotKind,
)
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.repair.models import RepairJournalEntryStatus, RepairRunStatus
from immich_doctor.repair.store import RepairJournalStore
from immich_doctor.runtime.integrity.models import (
    FileIntegrityFinding,
    FileIntegrityStatus,
    FileRole,
    MediaKind,
)
from immich_doctor.runtime.metadata_failures.models import (
    ConfidenceLevel,
    MetadataFailureCause,
    MetadataFailureDiagnostic,
    MetadataFailureInspectResult,
    MetadataFailureLevel,
    MetadataRepairStatus,
    SuggestedAction,
)
from immich_doctor.runtime.metadata_failures.repair_service import (
    RuntimeMetadataFailuresRepairService,
)


def _diagnostic(
    asset_id: str,
    *,
    root_cause: MetadataFailureCause,
    suggested_action: SuggestedAction,
    available_actions: tuple[SuggestedAction, ...],
    source_path: str,
) -> MetadataFailureDiagnostic:
    return MetadataFailureDiagnostic(
        diagnostic_id=f"metadata_failure:{asset_id}",
        asset_id=asset_id,
        job_name="metadata_extraction",
        root_cause=root_cause,
        failure_level=MetadataFailureLevel.SECONDARY,
        suggested_action=suggested_action,
        confidence=ConfidenceLevel.HIGH,
        source_path=source_path,
        source_file_status=FileIntegrityStatus.FILE_PERMISSION_DENIED.value,
        source_message="probe failed",
        available_actions=available_actions,
        file_findings=(
            FileIntegrityFinding(
                finding_id=f"file_integrity:{asset_id}:source:file",
                asset_id=asset_id,
                file_role=FileRole.SOURCE,
                media_kind=MediaKind.IMAGE,
                path=source_path,
                status=FileIntegrityStatus.FILE_PERMISSION_DENIED,
                message="probe failed",
            ),
        ),
    )


@dataclass(slots=True)
class _FakeInspectService:
    result: MetadataFailureInspectResult
    call_count: int = 0
    drift_result: MetadataFailureInspectResult | None = None

    def run(
        self,
        settings: AppSettings,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> MetadataFailureInspectResult:
        self.call_count += 1
        if self.drift_result is not None and self.call_count == 2:
            return self.drift_result
        return self.result


@dataclass(slots=True)
class _FakeFilesystem:
    repaired_paths: list[str]
    modes: dict[str, int]

    def stat_path(self, path) -> SimpleNamespace:  # type: ignore[no-untyped-def]
        normalized = str(path).replace("\\", "/")
        return SimpleNamespace(st_mode=self.modes[normalized])

    def add_read_permissions(self, path) -> None:  # type: ignore[no-untyped-def]
        normalized = str(path).replace("\\", "/")
        self.repaired_paths.append(normalized)
        self.modes[normalized] = self.modes[normalized] | 0o440


@dataclass(slots=True)
class _FakeBackupFilesService:
    status: str = "success"
    snapshot_id: str = "snapshot-1"
    call_count: int = 0
    last_repair_run_id: str | None = None
    last_kind: str | None = None

    def run(  # type: ignore[no-untyped-def]
        self,
        settings,
        *,
        snapshot_kind,
        repair_run_id,
        source_fingerprint,
    ):
        self.call_count += 1
        self.last_repair_run_id = repair_run_id
        self.last_kind = snapshot_kind.value
        if self.status != "success":
            return BackupResult(
                domain="backup.files",
                action="run",
                status="fail",
                summary="snapshot failed",
                context=BackupContext(
                    job_name="backup-files",
                    requested_components=("files",),
                    target=BackupTarget(
                        kind="local",
                        reference="/backup",
                        display_name="backup",
                    ),
                    started_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
                ),
                warnings=("snapshot failed",),
                details={"source_fingerprint": source_fingerprint},
            )
        return BackupResult(
            domain="backup.files",
            action="run",
            status="success",
            summary="snapshot ok",
            context=BackupContext(
                job_name="backup-files",
                requested_components=("files",),
                target=BackupTarget(
                    kind="local",
                    reference="/backup",
                    display_name="backup",
                ),
                started_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
            ),
            snapshot=BackupSnapshot(
                snapshot_id=self.snapshot_id,
                kind=SnapshotKind.PRE_REPAIR,
                created_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
                source_fingerprint=source_fingerprint,
                coverage=SnapshotCoverage.FILES_ONLY,
                file_artifacts=(),
                db_artifact=None,
                manifest_path=Path("/manifests") / f"{self.snapshot_id}.json",
                verified=False,
                repair_run_id=repair_run_id,
            ),
        )


def _inspect_result(
    diagnostics: list[MetadataFailureDiagnostic],
) -> MetadataFailureInspectResult:
    return MetadataFailureInspectResult(
        domain="runtime.metadata_failures",
        action="inspect",
        summary="diagnostics ready",
        checks=[
            CheckResult(
                name="postgres_connection",
                status=CheckStatus.PASS,
                message="PostgreSQL connection established.",
            )
        ],
        integrity_summary=[],
        metadata_summary=[],
        diagnostics=diagnostics,
    )


def test_metadata_failures_repair_dry_run_filters_by_diagnostic_id(tmp_path: Path) -> None:
    diagnostics = [
        _diagnostic(
            "asset-a",
            root_cause=MetadataFailureCause.CAUSED_BY_PERMISSION_ERROR,
            suggested_action=SuggestedAction.FIX_PERMISSIONS,
            available_actions=(SuggestedAction.FIX_PERMISSIONS, SuggestedAction.REPORT_ONLY),
            source_path="/library/a.jpg",
        ),
        _diagnostic(
            "asset-b",
            root_cause=MetadataFailureCause.CAUSED_BY_CORRUPTED_FILE,
            suggested_action=SuggestedAction.QUARANTINE_CORRUPT,
            available_actions=(SuggestedAction.QUARANTINE_CORRUPT, SuggestedAction.REPORT_ONLY),
            source_path="/library/b.jpg",
        ),
    ]
    inspect_service = _FakeInspectService(result=_inspect_result(diagnostics))
    filesystem = _FakeFilesystem(repaired_paths=[], modes={"/library/a.jpg": 0o200})
    service = RuntimeMetadataFailuresRepairService(
        inspect_service=inspect_service,
        filesystem=filesystem,
        backup_files_service=_FakeBackupFilesService(),
    )
    settings = AppSettings(
        manifests_path=tmp_path / "manifests",
        quarantine_path=tmp_path / "quarantine",
    )

    result = service.run(
        settings,
        apply=False,
        limit=100,
        offset=0,
        diagnostic_ids=("metadata_failure:asset-a",),
        retry_jobs=False,
        requeue=False,
        fix_permissions=False,
        quarantine_corrupt=False,
        mark_unrecoverable=False,
    )

    assert inspect_service.call_count == 1
    assert filesystem.repaired_paths == []
    assert len(result.repair_actions) == 1
    assert result.repair_actions[0].status == MetadataRepairStatus.PLANNED
    assert result.repair_actions[0].diagnostic_id == "metadata_failure:asset-a"
    store = RepairJournalStore()
    loaded_run = store.load_run(settings, result.metadata["repair_run_id"])
    loaded_entries = store.load_journal_entries(settings, result.metadata["repair_run_id"])
    assert loaded_run.status == RepairRunStatus.COMPLETED
    assert loaded_entries[0].status == RepairJournalEntryStatus.PLANNED


def test_metadata_failures_repair_apply_fixes_permissions_and_revalidates(tmp_path: Path) -> None:
    source_path = str((tmp_path / "runtime-repair-a.jpg").resolve()).replace("\\", "/")
    diagnostics = [
        _diagnostic(
            "asset-a",
            root_cause=MetadataFailureCause.CAUSED_BY_PERMISSION_ERROR,
            suggested_action=SuggestedAction.FIX_PERMISSIONS,
            available_actions=(SuggestedAction.FIX_PERMISSIONS, SuggestedAction.REPORT_ONLY),
            source_path=source_path,
        )
    ]
    inspect_service = _FakeInspectService(result=_inspect_result(diagnostics))
    filesystem = _FakeFilesystem(repaired_paths=[], modes={source_path: 0o200})
    service = RuntimeMetadataFailuresRepairService(
        inspect_service=inspect_service,
        filesystem=filesystem,
        backup_files_service=_FakeBackupFilesService(snapshot_id="snapshot-apply"),
    )
    settings = AppSettings(
        manifests_path=tmp_path / "manifests",
        quarantine_path=tmp_path / "quarantine",
    )

    result = service.run(
        settings,
        apply=True,
        limit=100,
        offset=0,
        diagnostic_ids=("metadata_failure:asset-a",),
        retry_jobs=False,
        requeue=False,
        fix_permissions=True,
        quarantine_corrupt=False,
        mark_unrecoverable=False,
    )

    assert filesystem.repaired_paths == [source_path]
    assert inspect_service.call_count == 3
    assert result.repair_actions[0].status == MetadataRepairStatus.REPAIRED
    assert result.post_validation is not None
    store = RepairJournalStore()
    loaded_run = store.load_run(settings, result.metadata["repair_run_id"])
    loaded_entries = store.load_journal_entries(settings, result.metadata["repair_run_id"])
    assert loaded_run.status == RepairRunStatus.COMPLETED
    assert loaded_run.pre_repair_snapshot_id == "snapshot-apply"
    assert loaded_entries[0].status == RepairJournalEntryStatus.APPLIED
    assert loaded_entries[0].undo_payload["old_mode"] == 0o200
    assert loaded_entries[0].undo_payload["new_mode"] == 0o640


def test_metadata_failures_repair_apply_stops_on_drift(tmp_path: Path) -> None:
    source_path = str((tmp_path / "library" / "a.jpg").resolve()).replace("\\", "/")
    diagnostics = [
        _diagnostic(
            "asset-a",
            root_cause=MetadataFailureCause.CAUSED_BY_PERMISSION_ERROR,
            suggested_action=SuggestedAction.FIX_PERMISSIONS,
            available_actions=(SuggestedAction.FIX_PERMISSIONS, SuggestedAction.REPORT_ONLY),
            source_path=source_path,
        )
    ]
    inspect_service = _FakeInspectService(
        result=_inspect_result(diagnostics),
        drift_result=_inspect_result([]),
    )
    filesystem = _FakeFilesystem(repaired_paths=[], modes={source_path: 0o200})
    service = RuntimeMetadataFailuresRepairService(
        inspect_service=inspect_service,
        filesystem=filesystem,
        backup_files_service=_FakeBackupFilesService(),
    )
    settings = AppSettings(
        manifests_path=tmp_path / "manifests",
        quarantine_path=tmp_path / "quarantine",
    )

    result = service.run(
        settings,
        apply=True,
        limit=100,
        offset=0,
        diagnostic_ids=("metadata_failure:asset-a",),
        retry_jobs=False,
        requeue=False,
        fix_permissions=True,
        quarantine_corrupt=False,
        mark_unrecoverable=False,
    )

    assert filesystem.repaired_paths == []
    assert result.repair_actions == []
    assert result.overall_status == CheckStatus.FAIL
    store = RepairJournalStore()
    loaded_run = store.load_run(settings, result.metadata["repair_run_id"])
    assert loaded_run.status == RepairRunStatus.FAILED


def test_metadata_failures_repair_apply_stops_when_pre_snapshot_fails(tmp_path: Path) -> None:
    source_path = str((tmp_path / "runtime-repair-b.jpg").resolve()).replace("\\", "/")
    diagnostics = [
        _diagnostic(
            "asset-a",
            root_cause=MetadataFailureCause.CAUSED_BY_PERMISSION_ERROR,
            suggested_action=SuggestedAction.FIX_PERMISSIONS,
            available_actions=(SuggestedAction.FIX_PERMISSIONS, SuggestedAction.REPORT_ONLY),
            source_path=source_path,
        )
    ]
    inspect_service = _FakeInspectService(result=_inspect_result(diagnostics))
    filesystem = _FakeFilesystem(repaired_paths=[], modes={source_path: 0o200})
    backup_files_service = _FakeBackupFilesService(status="fail")
    service = RuntimeMetadataFailuresRepairService(
        inspect_service=inspect_service,
        filesystem=filesystem,
        backup_files_service=backup_files_service,
    )
    settings = AppSettings(
        manifests_path=tmp_path / "manifests",
        quarantine_path=tmp_path / "quarantine",
    )

    result = service.run(
        settings,
        apply=True,
        limit=100,
        offset=0,
        diagnostic_ids=("metadata_failure:asset-a",),
        retry_jobs=False,
        requeue=False,
        fix_permissions=True,
        quarantine_corrupt=False,
        mark_unrecoverable=False,
    )

    assert backup_files_service.call_count == 1
    assert filesystem.repaired_paths == []
    assert result.repair_actions == []
    assert result.overall_status == CheckStatus.FAIL
    assert result.metadata["pre_repair_snapshot_id"] is None
