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
class ValidationReport:
    command: str
    checks: list[CheckResult]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
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
            "command": self.command,
            "overall_status": self.overall_status.value,
            "generated_at": self.generated_at,
            "metadata": self.metadata,
            "checks": [check.to_dict() for check in self.checks],
        }
