from __future__ import annotations

from fastapi.testclient import TestClient

from immich_doctor.api.app import create_api_app
from immich_doctor.api.routes import runtime as runtime_routes
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.runtime.integrity.models import (
    FileIntegrityFinding,
    FileIntegrityInspectResult,
    FileIntegrityStatus,
    FileIntegritySummaryItem,
    FileRole,
    MediaKind,
)
from immich_doctor.runtime.metadata_failures.models import (
    ConfidenceLevel,
    MetadataFailureCause,
    MetadataFailureDiagnostic,
    MetadataFailureInspectResult,
    MetadataFailureLevel,
    MetadataFailureRepairResult,
    MetadataFailureSummaryItem,
    MetadataRepairAction,
    MetadataRepairStatus,
    SuggestedAction,
)


def _integrity_result() -> FileIntegrityInspectResult:
    return FileIntegrityInspectResult(
        domain="runtime.integrity",
        action="inspect",
        summary="Integrity inspection finished.",
        checks=[
            CheckResult(
                name="postgres_connection",
                status=CheckStatus.PASS,
                message="PostgreSQL connection established.",
            )
        ],
        findings=[
            FileIntegrityFinding(
                finding_id="file_integrity:asset-1:source:asset.jpg",
                asset_id="asset-1",
                file_role=FileRole.SOURCE,
                media_kind=MediaKind.IMAGE,
                path="/library/asset.jpg",
                status=FileIntegrityStatus.FILE_OK,
                message="File passed the current physical integrity checks.",
            )
        ],
        summary_items=[
            FileIntegritySummaryItem(status=FileIntegrityStatus.FILE_OK, count=1),
        ],
    )


def _diagnostic() -> MetadataFailureDiagnostic:
    return MetadataFailureDiagnostic(
        diagnostic_id="metadata_failure:asset-1",
        asset_id="asset-1",
        job_name="metadata_extraction",
        root_cause=MetadataFailureCause.CAUSED_BY_PERMISSION_ERROR,
        failure_level=MetadataFailureLevel.SECONDARY,
        suggested_action=SuggestedAction.FIX_PERMISSIONS,
        confidence=ConfidenceLevel.HIGH,
        source_path="/library/asset.jpg",
        source_file_status=FileIntegrityStatus.FILE_PERMISSION_DENIED.value,
        source_message="File exists but is not readable by the current process.",
        available_actions=(SuggestedAction.FIX_PERMISSIONS, SuggestedAction.REPORT_ONLY),
        file_findings=(
            FileIntegrityFinding(
                finding_id="file_integrity:asset-1:source:asset.jpg",
                asset_id="asset-1",
                file_role=FileRole.SOURCE,
                media_kind=MediaKind.IMAGE,
                path="/library/asset.jpg",
                status=FileIntegrityStatus.FILE_PERMISSION_DENIED,
                message="File exists but is not readable by the current process.",
            ),
        ),
    )


def _metadata_inspect_result() -> MetadataFailureInspectResult:
    return MetadataFailureInspectResult(
        domain="runtime.metadata_failures",
        action="inspect",
        summary="1 metadata failure detected.",
        checks=[
            CheckResult(
                name="postgres_connection",
                status=CheckStatus.PASS,
                message="PostgreSQL connection established.",
            )
        ],
        integrity_summary=[
            {"status": FileIntegrityStatus.FILE_PERMISSION_DENIED.value, "count": 1}
        ],
        metadata_summary=[
            MetadataFailureSummaryItem(
                root_cause=MetadataFailureCause.CAUSED_BY_PERMISSION_ERROR,
                count=1,
            )
        ],
        diagnostics=[_diagnostic()],
    )


def _metadata_repair_result() -> MetadataFailureRepairResult:
    diagnostic = _diagnostic()
    return MetadataFailureRepairResult(
        domain="runtime.metadata_failures",
        action="repair",
        summary="Metadata failure repair planned 1 actions and skipped 0 without mutating data.",
        checks=[
            CheckResult(
                name="postgres_connection",
                status=CheckStatus.PASS,
                message="PostgreSQL connection established.",
            )
        ],
        diagnostics=[diagnostic],
        repair_actions=[
            MetadataRepairAction(
                action=SuggestedAction.FIX_PERMISSIONS,
                diagnostic_id=diagnostic.diagnostic_id,
                status=MetadataRepairStatus.PLANNED,
                reason="Planned `fix_permissions` because root cause was permission related.",
                path=diagnostic.source_path,
                supports_apply=True,
                dry_run=True,
                applied=False,
            )
        ],
    )


def test_runtime_integrity_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_routes.RuntimeIntegrityInspectService,
        "run",
        lambda self, settings, **kwargs: _integrity_result(),
    )
    client = TestClient(create_api_app())

    response = client.get("/api/runtime/integrity/inspect")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "backend"
    assert payload["data"]["domain"] == "runtime.integrity"
    assert payload["data"]["findings"][0]["status"] == "FILE_OK"


def test_runtime_metadata_failures_inspect_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_routes.RuntimeMetadataFailuresInspectService,
        "run",
        lambda self, settings, **kwargs: _metadata_inspect_result(),
    )
    client = TestClient(create_api_app())

    response = client.get("/api/runtime/metadata-failures/inspect")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["domain"] == "runtime.metadata_failures"
    assert payload["data"]["diagnostics"][0]["root_cause"] == "CAUSED_BY_PERMISSION_ERROR"


def test_runtime_metadata_failures_repair_route_returns_expected_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_routes.RuntimeMetadataFailuresRepairService,
        "run",
        lambda self, settings, **kwargs: _metadata_repair_result(),
    )
    client = TestClient(create_api_app())

    response = client.post(
        "/api/runtime/metadata-failures/repair",
        json={"apply": False, "diagnostic_ids": ["metadata_failure:asset-1"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["domain"] == "runtime.metadata_failures"
    assert payload["data"]["repair_actions"][0]["status"] == "planned"


def test_runtime_metadata_failures_repair_readiness_route_returns_expected_shape(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        runtime_routes.RuntimeRepairReadinessService,
        "run",
        lambda self, settings: {
            "generatedAt": "2026-03-15T10:00:00+00:00",
            "action": "fix_permissions",
            "applyAllowed": False,
            "blockingReasons": ["Backup target path is not writable."],
            "preconditions": [
                {
                    "id": "backup_target_path_writable",
                    "label": "backup target path writable",
                    "status": "error",
                    "blocking": True,
                    "summary": "Backup target path is not writable.",
                    "details": {},
                }
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
        },
    )
    client = TestClient(create_api_app())

    response = client.get("/api/runtime/metadata-failures/repair-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["applyAllowed"] is False
    assert payload["data"]["snapshotPlan"]["coverage"] == "files_only"
