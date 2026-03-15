from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from immich_doctor.core.models import CheckResult, CheckStatus


class RestoreReadiness(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"
    SIMULATION_ONLY = "simulation_only"


@dataclass(slots=True, frozen=True)
class RestoreBlocker:
    code: str
    message: str
    severity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass(slots=True, frozen=True)
class RestoreInstruction:
    step_id: str
    phase: str
    description: str
    command: str | None = None
    manual: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "phase": self.phase,
            "description": self.description,
            "command": self.command,
            "manual": self.manual,
        }


@dataclass(slots=True)
class RestoreSimulationResult:
    domain: str
    action: str
    summary: str
    readiness: RestoreReadiness
    checks: list[CheckResult]
    selected_snapshot: dict[str, Any] | None = None
    blockers: list[RestoreBlocker] = field(default_factory=list)
    instructions: list[RestoreInstruction] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        if self.readiness == RestoreReadiness.BLOCKED:
            statuses.add(CheckStatus.FAIL)
        elif self.readiness == RestoreReadiness.SIMULATION_ONLY:
            statuses.add(CheckStatus.WARN)
        elif self.readiness == RestoreReadiness.READY:
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
            "readiness": self.readiness.value,
            "checks": [check.to_dict() for check in self.checks],
            "selected_snapshot": self.selected_snapshot,
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "instructions": [instruction.to_dict() for instruction in self.instructions],
            "recommendations": self.recommendations,
        }
