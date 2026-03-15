from __future__ import annotations

from dataclasses import dataclass

from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
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

    def run(
        self,
        settings: AppSettings,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> MetadataFailureInspectResult:
        self.call_count += 1
        return self.result


@dataclass(slots=True)
class _FakeFilesystem:
    repaired_paths: list[str]

    def add_read_permissions(self, path) -> None:  # type: ignore[no-untyped-def]
        self.repaired_paths.append(str(path).replace("\\", "/"))


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


def test_metadata_failures_repair_dry_run_filters_by_diagnostic_id() -> None:
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
    filesystem = _FakeFilesystem(repaired_paths=[])
    service = RuntimeMetadataFailuresRepairService(
        inspect_service=inspect_service,
        filesystem=filesystem,
    )

    result = service.run(
        AppSettings(),
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


def test_metadata_failures_repair_apply_fixes_permissions_and_revalidates() -> None:
    diagnostics = [
        _diagnostic(
            "asset-a",
            root_cause=MetadataFailureCause.CAUSED_BY_PERMISSION_ERROR,
            suggested_action=SuggestedAction.FIX_PERMISSIONS,
            available_actions=(SuggestedAction.FIX_PERMISSIONS, SuggestedAction.REPORT_ONLY),
            source_path="/library/a.jpg",
        )
    ]
    inspect_service = _FakeInspectService(result=_inspect_result(diagnostics))
    filesystem = _FakeFilesystem(repaired_paths=[])
    service = RuntimeMetadataFailuresRepairService(
        inspect_service=inspect_service,
        filesystem=filesystem,
    )

    result = service.run(
        AppSettings(),
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

    assert filesystem.repaired_paths == ["/library/a.jpg"]
    assert inspect_service.call_count == 2
    assert result.repair_actions[0].status == MetadataRepairStatus.REPAIRED
    assert result.post_validation is not None
