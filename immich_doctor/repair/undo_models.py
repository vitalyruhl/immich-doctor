from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from immich_doctor.core.models import CheckResult, CheckStatus


class UndoEligibility(StrEnum):
    REVERSIBLE_NOW = "reversible_now"
    PARTIALLY_REVERSIBLE = "partially_reversible"
    NOT_REVERSIBLE = "not_reversible"
    REQUIRES_FULL_RESTORE = "requires_full_restore"


class UndoExecutionStatus(StrEnum):
    PLANNED = "planned"
    APPLIED = "applied"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(slots=True, frozen=True)
class UndoBlocker:
    code: str
    message: str
    severity: str
    entry_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "entry_id": self.entry_id,
        }


@dataclass(slots=True, frozen=True)
class UndoEntryAssessment:
    entry_id: str
    operation_type: str
    eligibility: UndoEligibility
    asset_id: str | None
    original_path: str | None
    undo_type: str
    blockers: tuple[UndoBlocker, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "operation_type": self.operation_type,
            "eligibility": self.eligibility.value,
            "asset_id": self.asset_id,
            "original_path": self.original_path,
            "undo_type": self.undo_type,
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "details": self.details,
        }


@dataclass(slots=True, frozen=True)
class UndoExecutionItem:
    entry_id: str
    operation_type: str
    status: UndoExecutionStatus
    message: str
    original_path: str | None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "operation_type": self.operation_type,
            "status": self.status.value,
            "message": self.message,
            "original_path": self.original_path,
            "details": self.details,
        }


@dataclass(slots=True)
class UndoPlanResult:
    domain: str
    action: str
    summary: str
    repair_run_id: str
    target_repair_run_status: str
    eligibility: UndoEligibility
    apply_allowed: bool
    checks: list[CheckResult]
    blockers: list[UndoBlocker] = field(default_factory=list)
    entry_assessments: list[UndoEntryAssessment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        if self.eligibility in {
            UndoEligibility.REQUIRES_FULL_RESTORE,
            UndoEligibility.NOT_REVERSIBLE,
        }:
            statuses.add(CheckStatus.FAIL)
        elif self.eligibility == UndoEligibility.PARTIALLY_REVERSIBLE:
            statuses.add(CheckStatus.WARN)
        elif self.eligibility == UndoEligibility.REVERSIBLE_NOW:
            statuses.add(CheckStatus.PASS)
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
            "repair_run_id": self.repair_run_id,
            "target_repair_run_status": self.target_repair_run_status,
            "eligibility": self.eligibility.value,
            "apply_allowed": self.apply_allowed,
            "checks": [check.to_dict() for check in self.checks],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "entry_assessments": [entry.to_dict() for entry in self.entry_assessments],
            "recommendations": self.recommendations,
        }


@dataclass(slots=True)
class UndoExecutionResult:
    domain: str
    action: str
    summary: str
    repair_run_id: str
    target_repair_run_id: str
    eligibility: UndoEligibility
    checks: list[CheckResult]
    execution_items: list[UndoExecutionItem] = field(default_factory=list)
    blockers: list[UndoBlocker] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        item_statuses = {item.status for item in self.execution_items}
        if UndoExecutionStatus.FAILED in item_statuses:
            statuses.add(CheckStatus.FAIL)
        elif UndoExecutionStatus.SKIPPED in item_statuses:
            statuses.add(CheckStatus.WARN)
        elif UndoExecutionStatus.APPLIED in item_statuses:
            statuses.add(CheckStatus.PASS)
        if self.eligibility == UndoEligibility.REQUIRES_FULL_RESTORE:
            statuses.add(CheckStatus.FAIL)
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
            "repair_run_id": self.repair_run_id,
            "target_repair_run_id": self.target_repair_run_id,
            "eligibility": self.eligibility.value,
            "checks": [check.to_dict() for check in self.checks],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "execution_items": [item.to_dict() for item in self.execution_items],
            "recommendations": self.recommendations,
        }
