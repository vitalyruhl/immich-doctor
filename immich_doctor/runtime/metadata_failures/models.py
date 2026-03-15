from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.runtime.integrity.models import FileIntegrityFinding


class MetadataFailureCause(StrEnum):
    CAUSED_BY_MISSING_FILE = "CAUSED_BY_MISSING_FILE"
    CAUSED_BY_EMPTY_FILE = "CAUSED_BY_EMPTY_FILE"
    CAUSED_BY_CORRUPTED_FILE = "CAUSED_BY_CORRUPTED_FILE"
    CAUSED_BY_PERMISSION_ERROR = "CAUSED_BY_PERMISSION_ERROR"
    CAUSED_BY_PATH_MISMATCH = "CAUSED_BY_PATH_MISMATCH"
    CAUSED_BY_UNSUPPORTED_FORMAT = "CAUSED_BY_UNSUPPORTED_FORMAT"
    CAUSED_BY_RUNTIME_TOOLING_ERROR = "CAUSED_BY_RUNTIME_TOOLING_ERROR"
    IMMICH_BUG_SUSPECTED = "IMMICH_BUG_SUSPECTED"
    UNKNOWN = "UNKNOWN"


class MetadataFailureLevel(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"


class SuggestedAction(StrEnum):
    REPORT_ONLY = "report_only"
    RETRY_JOBS = "retry_jobs"
    REQUEUE = "requeue"
    FIX_PERMISSIONS = "fix_permissions"
    QUARANTINE_CORRUPT = "quarantine_corrupt"
    MARK_UNRECOVERABLE = "mark_unrecoverable"
    INSPECT_RUNTIME_TOOLING = "inspect_runtime_tooling"
    DANGEROUS_UNKNOWN = "dangerous_unknown"


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MetadataRepairStatus(StrEnum):
    DETECTED = "detected"
    PLANNED = "planned"
    REPAIRED = "repaired"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(slots=True, frozen=True)
class MetadataFailureDiagnostic:
    diagnostic_id: str
    asset_id: str
    job_name: str
    root_cause: MetadataFailureCause
    failure_level: MetadataFailureLevel
    suggested_action: SuggestedAction
    confidence: ConfidenceLevel
    source_path: str
    source_file_status: str
    source_message: str
    available_actions: tuple[SuggestedAction, ...] = ()
    file_findings: tuple[FileIntegrityFinding, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "diagnostic_id": self.diagnostic_id,
            "asset_id": self.asset_id,
            "job_name": self.job_name,
            "root_cause": self.root_cause.value,
            "failure_level": self.failure_level.value,
            "suggested_action": self.suggested_action.value,
            "confidence": self.confidence.value,
            "source_path": self.source_path,
            "source_file_status": self.source_file_status,
            "source_message": self.source_message,
            "available_actions": [action.value for action in self.available_actions],
            "file_findings": [finding.to_dict() for finding in self.file_findings],
            "details": self.details,
        }


@dataclass(slots=True, frozen=True)
class MetadataFailureSummaryItem:
    root_cause: MetadataFailureCause
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {"root_cause": self.root_cause.value, "count": self.count}


@dataclass(slots=True, frozen=True)
class MetadataRepairAction:
    action: SuggestedAction
    diagnostic_id: str
    status: MetadataRepairStatus
    reason: str
    path: str
    supports_apply: bool
    dry_run: bool
    applied: bool
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "diagnostic_id": self.diagnostic_id,
            "status": self.status.value,
            "reason": self.reason,
            "path": self.path,
            "supports_apply": self.supports_apply,
            "dry_run": self.dry_run,
            "applied": self.applied,
            "details": self.details,
        }


@dataclass(slots=True)
class MetadataFailureInspectResult:
    domain: str
    action: str
    summary: str
    checks: list[CheckResult]
    integrity_summary: list[dict[str, Any]]
    metadata_summary: list[MetadataFailureSummaryItem]
    diagnostics: list[MetadataFailureDiagnostic]
    recommendations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        if self.diagnostics:
            if any(
                diagnostic.root_cause
                in {
                    MetadataFailureCause.CAUSED_BY_MISSING_FILE,
                    MetadataFailureCause.CAUSED_BY_EMPTY_FILE,
                    MetadataFailureCause.CAUSED_BY_CORRUPTED_FILE,
                    MetadataFailureCause.CAUSED_BY_PERMISSION_ERROR,
                    MetadataFailureCause.CAUSED_BY_PATH_MISMATCH,
                }
                for diagnostic in self.diagnostics
            ):
                statuses.add(CheckStatus.FAIL)
            else:
                statuses.add(CheckStatus.WARN)

        if CheckStatus.FAIL in statuses:
            return CheckStatus.FAIL
        if CheckStatus.WARN in statuses:
            return CheckStatus.WARN
        if not self.diagnostics and CheckStatus.SKIP in statuses:
            return CheckStatus.SKIP
        if CheckStatus.PASS in statuses:
            return CheckStatus.PASS
        return CheckStatus.SKIP

    @property
    def exit_code(self) -> int:
        return 1 if self.overall_status == CheckStatus.FAIL else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "action": self.action,
            "status": self.overall_status.value.upper(),
            "summary": self.summary,
            "generated_at": self.generated_at,
            "metadata": self.metadata,
            "checks": [check.to_dict() for check in self.checks],
            "integrity_summary": self.integrity_summary,
            "metadata_summary": [item.to_dict() for item in self.metadata_summary],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
            "recommendations": self.recommendations,
        }


@dataclass(slots=True)
class MetadataFailureRepairResult:
    domain: str
    action: str
    summary: str
    checks: list[CheckResult]
    diagnostics: list[MetadataFailureDiagnostic]
    repair_actions: list[MetadataRepairAction]
    post_validation: MetadataFailureInspectResult | None = None
    recommendations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        action_statuses = {action.status for action in self.repair_actions}

        if MetadataRepairStatus.FAILED in action_statuses or CheckStatus.FAIL in statuses:
            return CheckStatus.FAIL
        if MetadataRepairStatus.REPAIRED in action_statuses:
            return CheckStatus.PASS
        if MetadataRepairStatus.PLANNED in action_statuses:
            return CheckStatus.WARN
        if MetadataRepairStatus.SKIPPED in action_statuses:
            return CheckStatus.SKIP
        return CheckStatus.PASS if self.diagnostics else CheckStatus.SKIP

    @property
    def exit_code(self) -> int:
        return 1 if self.overall_status == CheckStatus.FAIL else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "action": self.action,
            "status": self.overall_status.value.upper(),
            "summary": self.summary,
            "generated_at": self.generated_at,
            "metadata": self.metadata,
            "checks": [check.to_dict() for check in self.checks],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
            "repair_actions": [action.to_dict() for action in self.repair_actions],
            "post_validation": self.post_validation.to_dict() if self.post_validation else None,
            "recommendations": self.recommendations,
        }
