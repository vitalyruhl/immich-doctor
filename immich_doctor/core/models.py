from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


@dataclass(slots=True)
class CheckResult:
    name: str
    status: CheckStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass(slots=True)
class ValidationSection:
    name: str
    status: CheckStatus
    rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "rows": self.rows,
        }


@dataclass(slots=True)
class ValidationReport:
    domain: str
    action: str
    summary: str
    checks: list[CheckResult]
    sections: list[ValidationSection] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        statuses.update(section.status for section in self.sections)
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
            "sections": [section.to_dict() for section in self.sections],
            "metrics": self.metrics,
            "recommendations": self.recommendations,
        }


class RepairItemStatus(StrEnum):
    DETECTED = "detected"
    PLANNED = "planned"
    REPAIRED = "repaired"
    SKIPPED = "skipped"


@dataclass(slots=True)
class RepairPlanItem:
    action: str
    target_table: str
    reason: str
    key_columns: tuple[str, ...]
    row_count: int
    sample_rows: list[dict[str, Any]] = field(default_factory=list)
    dry_run: bool = True
    applied: bool = False
    status: RepairItemStatus = RepairItemStatus.DETECTED
    backup_sql: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target_table": self.target_table,
            "reason": self.reason,
            "key_columns": list(self.key_columns),
            "row_count": self.row_count,
            "sample_rows": self.sample_rows,
            "dry_run": self.dry_run,
            "applied": self.applied,
            "status": self.status.value,
            "backup_sql": self.backup_sql,
        }


@dataclass(slots=True)
class RepairReport:
    domain: str
    action: str
    summary: str
    checks: list[CheckResult]
    plans: list[RepairPlanItem] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        if any(plan.status == RepairItemStatus.REPAIRED for plan in self.plans):
            statuses.add(CheckStatus.PASS)
        if any(plan.status == RepairItemStatus.PLANNED for plan in self.plans):
            statuses.add(CheckStatus.WARN)
        if any(plan.status == RepairItemStatus.SKIPPED for plan in self.plans):
            statuses.add(CheckStatus.SKIP)
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
            "plans": [plan.to_dict() for plan in self.plans],
            "recommendations": self.recommendations,
        }
