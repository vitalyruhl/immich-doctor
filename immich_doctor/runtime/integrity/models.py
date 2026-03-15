from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from immich_doctor.core.models import CheckResult, CheckStatus


class FileIntegrityStatus(StrEnum):
    FILE_OK = "FILE_OK"
    FILE_MISSING = "FILE_MISSING"
    FILE_EMPTY = "FILE_EMPTY"
    FILE_PERMISSION_DENIED = "FILE_PERMISSION_DENIED"
    FILE_TRUNCATED = "FILE_TRUNCATED"
    FILE_CONTAINER_BROKEN = "FILE_CONTAINER_BROKEN"
    FILE_CORRUPTED = "FILE_CORRUPTED"
    FILE_TYPE_MISMATCH = "FILE_TYPE_MISMATCH"
    FILE_UNKNOWN_PROBLEM = "FILE_UNKNOWN_PROBLEM"


class FileRole(StrEnum):
    SOURCE = "source"
    PREVIEW = "preview"
    THUMBNAIL = "thumbnail"
    DERIVATIVE = "derivative"


class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class FileIntegrityFinding:
    finding_id: str
    asset_id: str
    file_role: FileRole
    media_kind: MediaKind
    path: str
    status: FileIntegrityStatus
    asset_file_id: str | None = None
    message: str = ""
    size_bytes: int | None = None
    detected_format: str | None = None
    extension: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "asset_id": self.asset_id,
            "file_role": self.file_role.value,
            "media_kind": self.media_kind.value,
            "path": self.path,
            "status": self.status.value,
            "asset_file_id": self.asset_file_id,
            "message": self.message,
            "size_bytes": self.size_bytes,
            "detected_format": self.detected_format,
            "extension": self.extension,
            "details": self.details,
        }


@dataclass(slots=True, frozen=True)
class FileIntegritySummaryItem:
    status: FileIntegrityStatus
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "count": self.count}


@dataclass(slots=True)
class FileIntegrityInspectResult:
    domain: str
    action: str
    summary: str
    checks: list[CheckResult]
    findings: list[FileIntegrityFinding]
    summary_items: list[FileIntegritySummaryItem]
    recommendations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        if any(
            finding.status
            in {
                FileIntegrityStatus.FILE_MISSING,
                FileIntegrityStatus.FILE_EMPTY,
                FileIntegrityStatus.FILE_PERMISSION_DENIED,
                FileIntegrityStatus.FILE_TRUNCATED,
                FileIntegrityStatus.FILE_CONTAINER_BROKEN,
                FileIntegrityStatus.FILE_CORRUPTED,
                FileIntegrityStatus.FILE_TYPE_MISMATCH,
                FileIntegrityStatus.FILE_UNKNOWN_PROBLEM,
            }
            for finding in self.findings
        ):
            statuses.add(CheckStatus.FAIL)
        elif self.findings:
            statuses.add(CheckStatus.PASS)

        if CheckStatus.FAIL in statuses:
            return CheckStatus.FAIL
        if CheckStatus.WARN in statuses:
            return CheckStatus.WARN
        if not self.findings and CheckStatus.SKIP in statuses:
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
            "findings": [finding.to_dict() for finding in self.findings],
            "summary_items": [item.to_dict() for item in self.summary_items],
            "recommendations": self.recommendations,
        }
