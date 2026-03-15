from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.runtime.integrity.models import (
    FileIntegrityFinding,
    FileIntegrityStatus,
    FileRole,
    MediaKind,
)
from immich_doctor.runtime.metadata_failures.models import MetadataFailureCause
from immich_doctor.runtime.metadata_failures.service import RuntimeMetadataFailuresInspectService


@dataclass(slots=True)
class _FakeAnalyzer:
    findings: list[FileIntegrityFinding]
    ffprobe_ready: bool = True

    @property
    def media_probe(self):  # type: ignore[no-untyped-def]
        return self

    def ffprobe_available(self) -> bool:
        return self.ffprobe_ready

    def inspect_records(
        self,
        asset_rows: list[dict[str, object]],
        asset_file_rows: dict[str, list[dict[str, object]]],
        *,
        include_derivatives: bool,
    ) -> list[FileIntegrityFinding]:
        return list(self.findings)


class _FakePostgres:
    def __init__(self, *, candidates: list[dict[str, object]], supported: bool = True) -> None:
        self.candidates = candidates
        self.supported = supported

    def validate_connection(self, dsn: str, timeout_seconds: int) -> CheckResult:
        return CheckResult(
            name="postgres_connection",
            status=CheckStatus.PASS,
            message="PostgreSQL connection established.",
        )

    def list_tables(self, dsn: str, timeout_seconds: int) -> list[dict[str, object]]:
        tables = [
            {"table_schema": "public", "table_name": "asset"},
            {"table_schema": "public", "table_name": "asset_file"},
        ]
        if self.supported:
            tables.append({"table_schema": "public", "table_name": "asset_job_status"})
        return tables

    def list_columns(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        table_schema: str,
        table_name: str,
    ) -> list[dict[str, object]]:
        columns = {
            "asset": ("id", "type", "originalPath"),
            "asset_file": ("id", "assetId", "type", "path"),
            "asset_job_status": ("assetId", "metadataExtractedAt"),
        }
        return [{"column_name": name} for name in columns.get(table_name, ())]

    def list_metadata_failure_candidates(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, object]]:
        return self.candidates[offset : offset + limit]

    def list_asset_files_for_assets(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        asset_ids: tuple[str, ...],
    ) -> list[dict[str, object]]:
        return []


def _source_finding(
    asset_id: str,
    path: str,
    status: FileIntegrityStatus,
) -> FileIntegrityFinding:
    return FileIntegrityFinding(
        finding_id=f"file_integrity:{asset_id}:source:{Path(path).name}",
        asset_id=asset_id,
        file_role=FileRole.SOURCE,
        media_kind=MediaKind.IMAGE,
        path=path,
        status=status,
        message=f"status={status.value}",
        details={},
    )


def test_metadata_failures_service_classifies_root_causes_from_file_findings(
    tmp_path: Path,
) -> None:
    library_root = tmp_path / "library"
    missing_path = str(library_root / "missing.jpg")
    denied_path = str(library_root / "denied.jpg")
    healthy_path = str(library_root / "healthy.jpg")
    mismatch_path = str(tmp_path / "outside" / "path.jpg")

    candidates = [
        {"id": "asset-missing", "type": "image", "originalPath": missing_path},
        {"id": "asset-permission", "type": "image", "originalPath": denied_path},
        {"id": "asset-bug", "type": "image", "originalPath": healthy_path},
        {"id": "asset-path", "type": "image", "originalPath": mismatch_path},
    ]
    analyzer = _FakeAnalyzer(
        findings=[
            _source_finding(
                "asset-missing",
                missing_path,
                FileIntegrityStatus.FILE_MISSING,
            ),
            _source_finding(
                "asset-permission",
                denied_path,
                FileIntegrityStatus.FILE_PERMISSION_DENIED,
            ),
            _source_finding("asset-bug", healthy_path, FileIntegrityStatus.FILE_OK),
            _source_finding("asset-path", mismatch_path, FileIntegrityStatus.FILE_MISSING),
        ]
    )
    service = RuntimeMetadataFailuresInspectService(
        postgres=_FakePostgres(candidates=candidates),
        analyzer=analyzer,
    )

    result = service.run(
        AppSettings(
            db_host="postgres",
            db_name="immich",
            db_user="immich",
            db_password="secret",
            immich_library_root=library_root,
        )
    )

    diagnostics = {diagnostic.asset_id: diagnostic for diagnostic in result.diagnostics}

    assert result.overall_status == CheckStatus.FAIL
    assert diagnostics["asset-missing"].root_cause == MetadataFailureCause.CAUSED_BY_MISSING_FILE
    assert (
        diagnostics["asset-permission"].root_cause
        == MetadataFailureCause.CAUSED_BY_PERMISSION_ERROR
    )
    assert diagnostics["asset-bug"].root_cause == MetadataFailureCause.IMMICH_BUG_SUSPECTED
    assert diagnostics["asset-path"].root_cause == MetadataFailureCause.CAUSED_BY_PATH_MISMATCH


def test_metadata_failures_service_skips_unsupported_schema() -> None:
    service = RuntimeMetadataFailuresInspectService(
        postgres=_FakePostgres(candidates=[], supported=False),
        analyzer=_FakeAnalyzer(findings=[]),
    )

    result = service.run(
        AppSettings(
            db_host="postgres",
            db_name="immich",
            db_user="immich",
            db_password="secret",
        )
    )

    assert result.overall_status == CheckStatus.SKIP
    assert result.diagnostics == []
    assert "unsupported" in result.summary.lower()
