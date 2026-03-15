from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.runtime.integrity.models import (
    FileIntegrityFinding,
    FileIntegrityStatus,
    FileIntegritySummaryItem,
    FileRole,
)
from immich_doctor.runtime.integrity.service import (
    DEFAULT_BATCH_LIMIT,
    RuntimeFileIntegrityAnalyzer,
)
from immich_doctor.runtime.metadata_failures.models import (
    ConfidenceLevel,
    MetadataFailureCause,
    MetadataFailureDiagnostic,
    MetadataFailureInspectResult,
    MetadataFailureLevel,
    MetadataFailureSummaryItem,
    SuggestedAction,
)
from immich_doctor.runtime.metadata_failures.profile import (
    RUNTIME_METADATA_PROFILE_NAME,
    RuntimeMetadataProfileDetector,
    RuntimeMetadataProfileResult,
)


@dataclass(slots=True)
class RuntimeMetadataFailuresInspectService:
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)
    analyzer: RuntimeFileIntegrityAnalyzer = field(default_factory=RuntimeFileIntegrityAnalyzer)
    batch_limit: int = DEFAULT_BATCH_LIMIT

    def run(
        self,
        settings: AppSettings,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> MetadataFailureInspectResult:
        dsn = settings.postgres_dsn_value()
        if not dsn:
            return MetadataFailureInspectResult(
                domain="runtime.metadata_failures",
                action="inspect",
                summary=(
                    "Metadata failure inspection failed because database access is not configured."
                ),
                checks=[
                    CheckResult(
                        name="postgres_connection",
                        status=CheckStatus.FAIL,
                        message="Database DSN is not configured.",
                    )
                ],
                integrity_summary=[],
                metadata_summary=[],
                diagnostics=[],
                metadata={"environment": settings.environment},
            )

        timeout = settings.postgres_connect_timeout_seconds
        connection_check = self.postgres.validate_connection(dsn, timeout)
        if connection_check.status == CheckStatus.FAIL:
            return MetadataFailureInspectResult(
                domain="runtime.metadata_failures",
                action="inspect",
                summary=(
                    "Metadata failure inspection failed because PostgreSQL could not be reached."
                ),
                checks=[connection_check],
                integrity_summary=[],
                metadata_summary=[],
                diagnostics=[],
                metadata={"environment": settings.environment},
            )

        profile_result = RuntimeMetadataProfileDetector(self.postgres).detect(dsn, timeout)
        checks = [connection_check, self._profile_check(profile_result)]
        if not profile_result.supported:
            return MetadataFailureInspectResult(
                domain="runtime.metadata_failures",
                action="inspect",
                summary=(
                    "Metadata failure inspection skipped because the current PostgreSQL schema is "
                    "unsupported."
                ),
                checks=checks,
                integrity_summary=[],
                metadata_summary=[],
                diagnostics=[],
                recommendations=[
                    "This workflow currently supports only the exact observed runtime metadata "
                    "profile.",
                ],
                metadata={"environment": settings.environment},
            )
        checks.append(self._ffprobe_check())

        batch_size = limit or self.batch_limit
        candidate_rows = self.postgres.list_metadata_failure_candidates(
            dsn,
            timeout,
            limit=batch_size,
            offset=offset,
        )
        asset_files = self.postgres.list_asset_files_for_assets(
            dsn,
            timeout,
            asset_ids=tuple(str(row["id"]) for row in candidate_rows),
        )
        asset_file_lookup: dict[str, list[dict[str, object]]] = {}
        for row in asset_files:
            asset_file_lookup.setdefault(str(row["assetId"]), []).append(row)

        integrity_findings = self.analyzer.inspect_records(
            candidate_rows,
            asset_file_lookup,
            include_derivatives=True,
        )
        findings_by_asset = self._group_findings_by_asset(integrity_findings)
        diagnostics = [
            self._build_diagnostic(
                settings=settings,
                asset_row=row,
                findings_by_asset=findings_by_asset,
            )
            for row in candidate_rows
        ]

        return MetadataFailureInspectResult(
            domain="runtime.metadata_failures",
            action="inspect",
            summary=self._build_summary(diagnostics),
            checks=checks,
            integrity_summary=[
                item.to_dict() for item in self._build_integrity_summary_items(integrity_findings)
            ],
            metadata_summary=self._build_metadata_summary(diagnostics),
            diagnostics=diagnostics,
            recommendations=self._recommendations(diagnostics),
            metadata={"environment": settings.environment, "limit": batch_size, "offset": offset},
        )

    def _build_diagnostic(
        self,
        *,
        settings: AppSettings,
        asset_row: dict[str, object],
        findings_by_asset: dict[str, list[FileIntegrityFinding]],
    ) -> MetadataFailureDiagnostic:
        asset_id = str(asset_row["id"])
        findings = tuple(findings_by_asset.get(asset_id, []))
        source_finding = next(
            (finding for finding in findings if finding.file_role == FileRole.SOURCE),
            None,
        )
        if source_finding is None:
            return MetadataFailureDiagnostic(
                diagnostic_id=f"metadata_failure:{asset_id}",
                asset_id=asset_id,
                job_name="metadata_extraction",
                root_cause=MetadataFailureCause.UNKNOWN,
                failure_level=MetadataFailureLevel.PRIMARY,
                suggested_action=SuggestedAction.DANGEROUS_UNKNOWN,
                confidence=ConfidenceLevel.LOW,
                source_path=str(asset_row["originalPath"]),
                source_file_status=FileIntegrityStatus.FILE_UNKNOWN_PROBLEM.value,
                source_message="Source file finding could not be produced.",
                available_actions=(SuggestedAction.DANGEROUS_UNKNOWN,),
                file_findings=findings,
            )

        root_cause, failure_level, suggested_action, confidence = self._classify_root_cause(
            settings,
            source_finding,
        )
        return MetadataFailureDiagnostic(
            diagnostic_id=f"metadata_failure:{asset_id}",
            asset_id=asset_id,
            job_name="metadata_extraction",
            root_cause=root_cause,
            failure_level=failure_level,
            suggested_action=suggested_action,
            confidence=confidence,
            source_path=source_finding.path,
            source_file_status=source_finding.status.value,
            source_message=source_finding.message,
            available_actions=self._available_actions(root_cause),
            file_findings=findings,
            details={
                "primary_file_finding": source_finding.to_dict(),
                "metadataExtractedAt": asset_row.get("metadataExtractedAt"),
            },
        )

    def _classify_root_cause(
        self,
        settings: AppSettings,
        source_finding: FileIntegrityFinding,
    ) -> tuple[
        MetadataFailureCause,
        MetadataFailureLevel,
        SuggestedAction,
        ConfidenceLevel,
    ]:
        if source_finding.status == FileIntegrityStatus.FILE_MISSING:
            if self._is_path_mismatch(settings, source_finding.path):
                return (
                    MetadataFailureCause.CAUSED_BY_PATH_MISMATCH,
                    MetadataFailureLevel.SECONDARY,
                    SuggestedAction.REPORT_ONLY,
                    ConfidenceLevel.MEDIUM,
                )
            return (
                MetadataFailureCause.CAUSED_BY_MISSING_FILE,
                MetadataFailureLevel.SECONDARY,
                SuggestedAction.REPORT_ONLY,
                ConfidenceLevel.HIGH,
            )
        if source_finding.status == FileIntegrityStatus.FILE_EMPTY:
            return (
                MetadataFailureCause.CAUSED_BY_EMPTY_FILE,
                MetadataFailureLevel.SECONDARY,
                SuggestedAction.MARK_UNRECOVERABLE,
                ConfidenceLevel.HIGH,
            )
        if source_finding.status == FileIntegrityStatus.FILE_PERMISSION_DENIED:
            return (
                MetadataFailureCause.CAUSED_BY_PERMISSION_ERROR,
                MetadataFailureLevel.SECONDARY,
                SuggestedAction.FIX_PERMISSIONS,
                ConfidenceLevel.HIGH,
            )
        if source_finding.status in {
            FileIntegrityStatus.FILE_TRUNCATED,
            FileIntegrityStatus.FILE_CONTAINER_BROKEN,
            FileIntegrityStatus.FILE_CORRUPTED,
        }:
            return (
                MetadataFailureCause.CAUSED_BY_CORRUPTED_FILE,
                MetadataFailureLevel.SECONDARY,
                SuggestedAction.QUARANTINE_CORRUPT,
                ConfidenceLevel.HIGH,
            )
        if source_finding.status == FileIntegrityStatus.FILE_TYPE_MISMATCH:
            return (
                MetadataFailureCause.CAUSED_BY_UNSUPPORTED_FORMAT,
                MetadataFailureLevel.SECONDARY,
                SuggestedAction.MARK_UNRECOVERABLE,
                ConfidenceLevel.MEDIUM,
            )
        probe_error = source_finding.details.get("probe_error_category")
        if probe_error in {"tool_missing", "runtime_tooling_error"}:
            return (
                MetadataFailureCause.CAUSED_BY_RUNTIME_TOOLING_ERROR,
                MetadataFailureLevel.PRIMARY,
                SuggestedAction.INSPECT_RUNTIME_TOOLING,
                ConfidenceLevel.MEDIUM,
            )
        if source_finding.status == FileIntegrityStatus.FILE_OK:
            return (
                MetadataFailureCause.IMMICH_BUG_SUSPECTED,
                MetadataFailureLevel.PRIMARY,
                SuggestedAction.RETRY_JOBS,
                ConfidenceLevel.LOW,
            )
        return (
            MetadataFailureCause.UNKNOWN,
            MetadataFailureLevel.PRIMARY,
            SuggestedAction.DANGEROUS_UNKNOWN,
            ConfidenceLevel.LOW,
        )

    def _is_path_mismatch(self, settings: AppSettings, path_value: str) -> bool:
        path = Path(path_value)
        if not path.is_absolute():
            return True
        if settings.immich_library_root is None:
            return False
        try:
            path.resolve().relative_to(settings.immich_library_root.resolve())
        except ValueError:
            return True
        return False

    def _available_actions(self, root_cause: MetadataFailureCause) -> tuple[SuggestedAction, ...]:
        mapping = {
            MetadataFailureCause.CAUSED_BY_MISSING_FILE: (
                SuggestedAction.REPORT_ONLY,
                SuggestedAction.MARK_UNRECOVERABLE,
            ),
            MetadataFailureCause.CAUSED_BY_EMPTY_FILE: (
                SuggestedAction.REPORT_ONLY,
                SuggestedAction.MARK_UNRECOVERABLE,
            ),
            MetadataFailureCause.CAUSED_BY_CORRUPTED_FILE: (
                SuggestedAction.REPORT_ONLY,
                SuggestedAction.QUARANTINE_CORRUPT,
            ),
            MetadataFailureCause.CAUSED_BY_PERMISSION_ERROR: (
                SuggestedAction.FIX_PERMISSIONS,
                SuggestedAction.REPORT_ONLY,
            ),
            MetadataFailureCause.CAUSED_BY_PATH_MISMATCH: (SuggestedAction.REPORT_ONLY,),
            MetadataFailureCause.CAUSED_BY_UNSUPPORTED_FORMAT: (
                SuggestedAction.REPORT_ONLY,
                SuggestedAction.MARK_UNRECOVERABLE,
            ),
            MetadataFailureCause.CAUSED_BY_RUNTIME_TOOLING_ERROR: (
                SuggestedAction.INSPECT_RUNTIME_TOOLING,
                SuggestedAction.REPORT_ONLY,
            ),
            MetadataFailureCause.IMMICH_BUG_SUSPECTED: (
                SuggestedAction.RETRY_JOBS,
                SuggestedAction.REQUEUE,
                SuggestedAction.REPORT_ONLY,
            ),
            MetadataFailureCause.UNKNOWN: (SuggestedAction.DANGEROUS_UNKNOWN,),
        }
        return mapping[root_cause]

    def _group_findings_by_asset(
        self,
        findings: list[FileIntegrityFinding],
    ) -> dict[str, list[FileIntegrityFinding]]:
        grouped: dict[str, list[FileIntegrityFinding]] = {}
        for finding in findings:
            grouped.setdefault(finding.asset_id, []).append(finding)
        return grouped

    def _build_integrity_summary_items(
        self,
        findings: list[FileIntegrityFinding],
    ) -> list[FileIntegritySummaryItem]:
        counts: dict[FileIntegrityStatus, int] = {}
        for finding in findings:
            counts[finding.status] = counts.get(finding.status, 0) + 1
        return [
            FileIntegritySummaryItem(status=status, count=counts[status])
            for status in FileIntegrityStatus
            if counts.get(status)
        ]

    def _build_metadata_summary(
        self,
        diagnostics: list[MetadataFailureDiagnostic],
    ) -> list[MetadataFailureSummaryItem]:
        counts: dict[MetadataFailureCause, int] = {}
        for diagnostic in diagnostics:
            counts[diagnostic.root_cause] = counts.get(diagnostic.root_cause, 0) + 1
        return [
            MetadataFailureSummaryItem(root_cause=cause, count=counts[cause])
            for cause in MetadataFailureCause
            if counts.get(cause)
        ]

    def _build_summary(self, diagnostics: list[MetadataFailureDiagnostic]) -> str:
        if not diagnostics:
            return "No unresolved metadata extraction candidates were found in the current batch."

        corrupted = sum(
            1
            for diagnostic in diagnostics
            if diagnostic.root_cause == MetadataFailureCause.CAUSED_BY_CORRUPTED_FILE
        )
        permission_errors = sum(
            1
            for diagnostic in diagnostics
            if diagnostic.root_cause == MetadataFailureCause.CAUSED_BY_PERMISSION_ERROR
        )
        bug_suspected = sum(
            1
            for diagnostic in diagnostics
            if diagnostic.root_cause == MetadataFailureCause.IMMICH_BUG_SUSPECTED
        )
        unexplained = sum(
            1 for diagnostic in diagnostics if diagnostic.root_cause == MetadataFailureCause.UNKNOWN
        )
        return (
            f"{len(diagnostics)} metadata failures detected. "
            f"{corrupted} caused by corrupted or truncated source files. "
            f"{permission_errors} caused by permission denial. "
            f"{bug_suspected} likely Immich or runtime processing issues. "
            f"{unexplained} remain unexplained."
        )

    def _recommendations(self, diagnostics: list[MetadataFailureDiagnostic]) -> list[str]:
        if not diagnostics:
            return ["No metadata failure diagnostics were produced in the current batch."]
        return [
            "Inspect physical source file integrity before retrying metadata extraction jobs.",
            "Use `runtime metadata-failures repair --dry-run` before any apply-capable action.",
        ]

    def _profile_check(self, profile_result: RuntimeMetadataProfileResult) -> CheckResult:
        if profile_result.supported:
            return CheckResult(
                name="runtime_metadata_schema_profile",
                status=CheckStatus.PASS,
                message=(
                    f"Supported schema profile `{profile_result.profile.name}` detected for "
                    "metadata failure inspection."
                ),
            )
        return CheckResult(
            name="runtime_metadata_schema_profile",
            status=CheckStatus.SKIP,
            message=(
                f"Unsupported schema for `{RUNTIME_METADATA_PROFILE_NAME}`. Metadata failure "
                "inspection will be skipped."
            ),
            details={
                "missing_tables": list(profile_result.missing_tables),
                "missing_columns": {
                    table: list(columns)
                    for table, columns in profile_result.missing_columns.items()
                },
            },
        )

    def _ffprobe_check(self) -> CheckResult:
        if self.analyzer.media_probe.ffprobe_available():
            return CheckResult(
                name="ffprobe_runtime_tool",
                status=CheckStatus.PASS,
                message="ffprobe is available for media failure diagnostics.",
            )
        return CheckResult(
            name="ffprobe_runtime_tool",
            status=CheckStatus.WARN,
            message=(
                "ffprobe is not available. Some video or audio failures may degrade to runtime "
                "tooling or unknown classifications."
            ),
        )
