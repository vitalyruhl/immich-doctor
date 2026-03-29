from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from immich_doctor.core.models import CheckResult, CheckStatus


class ConsistencySeverity(StrEnum):
    FAIL = "fail"
    WARN = "warn"


class ConsistencyRepairMode(StrEnum):
    SAFE_DELETE = "safe_delete"
    INSPECT_ONLY = "inspect_only"


class ConsistencyRepairStatus(StrEnum):
    REPAIRABLE = "repairable"
    INSPECT_ONLY = "inspect_only"
    SKIPPED = "skipped"
    WOULD_REPAIR = "would_repair"
    REPAIRED = "repaired"
    FAILED = "failed"


@dataclass(slots=True, frozen=True)
class ConsistencyFinding:
    category: str
    finding_id: str
    severity: ConsistencySeverity
    repair_mode: ConsistencyRepairMode
    affected_tables: tuple[str, ...] = ()
    affected_paths: tuple[str, ...] = ()
    key_fields: dict[str, str] = field(default_factory=dict)
    message: str = ""
    sample_metadata: dict[str, Any] = field(default_factory=dict)
    row_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "finding_id": self.finding_id,
            "severity": self.severity.value,
            "repair_mode": self.repair_mode.value,
            "affected_tables": list(self.affected_tables),
            "affected_paths": list(self.affected_paths),
            "key_fields": self.key_fields,
            "message": self.message,
            "sample_metadata": self.sample_metadata,
            "row_count": self.row_count,
        }


@dataclass(slots=True, frozen=True)
class ConsistencyCategory:
    name: str
    severity: ConsistencySeverity
    repair_mode: ConsistencyRepairMode
    status: CheckStatus
    count: int
    repairable: bool
    message: str
    sample_findings: tuple[ConsistencyFinding, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "severity": self.severity.value,
            "repair_mode": self.repair_mode.value,
            "status": self.status.value,
            "count": self.count,
            "repairable": self.repairable,
            "message": self.message,
            "sample_findings": [finding.to_dict() for finding in self.sample_findings],
        }


@dataclass(slots=True, frozen=True)
class ConsistencySummary:
    profile_name: str
    profile_supported: bool
    support_status: str = "unsupported"
    product_version_current: str | None = None
    product_version_confidence: str = "unknown"
    schema_generation_key: str | None = None
    schema_fingerprint: str | None = None
    asset_reference_column: str | None = None
    capability_snapshot: dict[str, bool] = field(default_factory=dict)
    risk_flags: tuple[str, ...] = ()
    executed_categories: tuple[str, ...] = ()
    skipped_categories: tuple[str, ...] = ()
    scope_boundaries: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "profile_supported": self.profile_supported,
            "support_status": self.support_status,
            "product_version_current": self.product_version_current,
            "product_version_confidence": self.product_version_confidence,
            "schema_generation_key": self.schema_generation_key,
            "schema_fingerprint": self.schema_fingerprint,
            "asset_reference_column": self.asset_reference_column,
            "capability_snapshot": self.capability_snapshot,
            "risk_flags": list(self.risk_flags),
            "executed_categories": list(self.executed_categories),
            "skipped_categories": list(self.skipped_categories),
            "scope_boundaries": list(self.scope_boundaries),
        }


@dataclass(slots=True, frozen=True)
class ConsistencyRepairAction:
    category: str
    repair_mode: ConsistencyRepairMode
    status: ConsistencyRepairStatus
    message: str
    target_table: str | None = None
    finding_ids: tuple[str, ...] = ()
    row_count: int = 0
    sample_findings: tuple[ConsistencyFinding, ...] = ()
    dry_run: bool = True
    applied: bool = False
    backup_sql: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "repair_mode": self.repair_mode.value,
            "status": self.status.value,
            "message": self.message,
            "target_table": self.target_table,
            "finding_ids": list(self.finding_ids),
            "row_count": self.row_count,
            "sample_findings": [finding.to_dict() for finding in self.sample_findings],
            "dry_run": self.dry_run,
            "applied": self.applied,
            "backup_sql": self.backup_sql,
        }


@dataclass(slots=True, frozen=True)
class ConsistencyRepairPlan:
    selected_categories: tuple[str, ...] = ()
    selected_ids: tuple[str, ...] = ()
    all_safe: bool = False
    actions: tuple[ConsistencyRepairAction, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_categories": list(self.selected_categories),
            "selected_ids": list(self.selected_ids),
            "all_safe": self.all_safe,
            "actions": [action.to_dict() for action in self.actions],
        }


@dataclass(slots=True)
class ConsistencyValidationReport:
    domain: str
    action: str
    summary: str
    checks: list[CheckResult]
    categories: list[ConsistencyCategory]
    findings: list[ConsistencyFinding]
    consistency_summary: ConsistencySummary
    recommendations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        statuses.update(category.status for category in self.categories)
        if CheckStatus.FAIL in statuses:
            return CheckStatus.FAIL
        if CheckStatus.WARN in statuses:
            return CheckStatus.WARN
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
            "categories": [category.to_dict() for category in self.categories],
            "findings": [finding.to_dict() for finding in self.findings],
            "consistency_summary": self.consistency_summary.to_dict(),
            "recommendations": self.recommendations,
        }


@dataclass(slots=True)
class ConsistencyRepairResult:
    domain: str
    action: str
    summary: str
    checks: list[CheckResult]
    repair_plan: ConsistencyRepairPlan
    consistency_summary: ConsistencySummary
    recommendations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        action_statuses = {action.status for action in self.repair_plan.actions}
        if ConsistencyRepairStatus.FAILED in action_statuses or CheckStatus.FAIL in statuses:
            return CheckStatus.FAIL
        if ConsistencyRepairStatus.WOULD_REPAIR in action_statuses:
            return CheckStatus.WARN
        if ConsistencyRepairStatus.SKIPPED in action_statuses and not action_statuses.difference(
            {ConsistencyRepairStatus.SKIPPED}
        ):
            return CheckStatus.SKIP
        return CheckStatus.PASS

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
            "repair_plan": self.repair_plan.to_dict(),
            "consistency_summary": self.consistency_summary.to_dict(),
            "recommendations": self.recommendations,
        }
