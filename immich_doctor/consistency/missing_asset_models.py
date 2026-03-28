from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from immich_doctor.core.models import CheckResult, CheckStatus


class MissingAssetReferenceStatus(StrEnum):
    PRESENT = "present"
    MISSING_ON_DISK = "missing_on_disk"
    PERMISSION_ERROR = "permission_error"
    UNREADABLE_PATH = "unreadable_path"
    UNSUPPORTED = "unsupported"
    ALREADY_REMOVED = "already_removed"


class RepairReadinessStatus(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"


class MissingAssetOperationStatus(StrEnum):
    PLANNED = "planned"
    APPLIED = "applied"
    SKIPPED = "skipped"
    FAILED = "failed"
    RESTORED = "restored"
    DELETED = "deleted"
    ALREADY_REMOVED = "already_removed"


class MissingAssetRestorePointStatus(StrEnum):
    AVAILABLE = "available"
    RESTORED = "restored"


@dataclass(slots=True, frozen=True)
class MissingAssetReferenceFinding:
    finding_id: str
    asset_id: str
    asset_type: str
    status: MissingAssetReferenceStatus
    logical_path: str
    resolved_physical_path: str
    owner_id: str | None
    created_at: str | None
    updated_at: str | None
    scan_timestamp: str
    repair_readiness: RepairReadinessStatus
    repair_blockers: tuple[str, ...] = ()
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "status": self.status.value,
            "logical_path": self.logical_path,
            "resolved_physical_path": self.resolved_physical_path,
            "owner_id": self.owner_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "scan_timestamp": self.scan_timestamp,
            "repair_readiness": self.repair_readiness.value,
            "repair_blockers": list(self.repair_blockers),
            "message": self.message,
        }


@dataclass(slots=True, frozen=True)
class MissingAssetRestorePointRecord:
    table: str
    row_count: int

    def to_dict(self) -> dict[str, Any]:
        return {"table": self.table, "row_count": self.row_count}


@dataclass(slots=True)
class MissingAssetRestorePoint:
    restore_point_id: str
    repair_run_id: str
    asset_id: str
    created_at: str
    status: MissingAssetRestorePointStatus
    record_count: int
    logical_path: str
    records: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "restore_point_id": self.restore_point_id,
            "repair_run_id": self.repair_run_id,
            "asset_id": self.asset_id,
            "created_at": self.created_at,
            "status": self.status.value,
            "record_count": self.record_count,
            "logical_path": self.logical_path,
            "records": self.records,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> MissingAssetRestorePoint:
        return cls(
            restore_point_id=payload["restore_point_id"],
            repair_run_id=payload["repair_run_id"],
            asset_id=payload["asset_id"],
            created_at=payload["created_at"],
            status=MissingAssetRestorePointStatus(payload["status"]),
            record_count=int(payload["record_count"]),
            logical_path=payload["logical_path"],
            records=list(payload.get("records", [])),
        )

    @property
    def record_summaries(self) -> list[MissingAssetRestorePointRecord]:
        return [
            MissingAssetRestorePointRecord(
                table=str(item["table"]),
                row_count=len(list(item.get("rows", []))),
            )
            for item in self.records
        ]


@dataclass(slots=True, frozen=True)
class MissingAssetOperationItem:
    asset_id: str
    status: MissingAssetOperationStatus
    restore_point_id: str | None
    message: str
    record_count: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "status": self.status.value,
            "restore_point_id": self.restore_point_id,
            "message": self.message,
            "record_count": self.record_count,
            "details": self.details,
        }


@dataclass(slots=True)
class MissingAssetReferenceScanResult:
    summary: str
    checks: list[CheckResult]
    findings: list[MissingAssetReferenceFinding]
    metadata: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        if any(
            finding.status in {MissingAssetReferenceStatus.MISSING_ON_DISK}
            for finding in self.findings
        ):
            statuses.add(CheckStatus.FAIL)
        elif any(
            finding.status
            in {
                MissingAssetReferenceStatus.PERMISSION_ERROR,
                MissingAssetReferenceStatus.UNREADABLE_PATH,
                MissingAssetReferenceStatus.UNSUPPORTED,
            }
            for finding in self.findings
        ):
            statuses.add(CheckStatus.WARN)
        elif self.findings:
            statuses.add(CheckStatus.PASS)

        if CheckStatus.FAIL in statuses:
            return CheckStatus.FAIL
        if CheckStatus.WARN in statuses:
            return CheckStatus.WARN
        if CheckStatus.PASS in statuses:
            return CheckStatus.PASS
        return CheckStatus.SKIP

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": "consistency.missing_asset_references",
            "action": "scan",
            "status": self.overall_status.value.upper(),
            "summary": self.summary,
            "generated_at": self.generated_at,
            "checks": [check.to_dict() for check in self.checks],
            "findings": [finding.to_dict() for finding in self.findings],
            "metadata": self.metadata,
            "recommendations": self.recommendations,
        }


@dataclass(slots=True)
class MissingAssetPreviewResult:
    summary: str
    checks: list[CheckResult]
    selected_findings: list[MissingAssetReferenceFinding]
    repair_run_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        if self.selected_findings:
            statuses.add(CheckStatus.WARN)
        if CheckStatus.FAIL in statuses:
            return CheckStatus.FAIL
        if CheckStatus.WARN in statuses:
            return CheckStatus.WARN
        return CheckStatus.SKIP

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": "consistency.missing_asset_references",
            "action": "preview",
            "status": self.overall_status.value.upper(),
            "summary": self.summary,
            "generated_at": self.generated_at,
            "checks": [check.to_dict() for check in self.checks],
            "selected_findings": [finding.to_dict() for finding in self.selected_findings],
            "repair_run_id": self.repair_run_id,
            "metadata": self.metadata,
            "recommendations": self.recommendations,
        }


@dataclass(slots=True)
class MissingAssetApplyResult:
    summary: str
    checks: list[CheckResult]
    repair_run_id: str
    items: list[MissingAssetOperationItem]
    metadata: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        item_statuses = {item.status for item in self.items}
        if MissingAssetOperationStatus.FAILED in item_statuses:
            return CheckStatus.FAIL
        if item_statuses.intersection(
            {
                MissingAssetOperationStatus.APPLIED,
                MissingAssetOperationStatus.ALREADY_REMOVED,
                MissingAssetOperationStatus.SKIPPED,
            }
        ):
            return CheckStatus.PASS
        if CheckStatus.FAIL in statuses:
            return CheckStatus.FAIL
        if CheckStatus.WARN in statuses:
            return CheckStatus.WARN
        return CheckStatus.SKIP

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": "consistency.missing_asset_references",
            "action": "apply",
            "status": self.overall_status.value.upper(),
            "summary": self.summary,
            "generated_at": self.generated_at,
            "checks": [check.to_dict() for check in self.checks],
            "repair_run_id": self.repair_run_id,
            "items": [item.to_dict() for item in self.items],
            "metadata": self.metadata,
            "recommendations": self.recommendations,
        }


@dataclass(slots=True)
class MissingAssetRestorePointsResult:
    summary: str
    checks: list[CheckResult]
    items: list[MissingAssetRestorePoint]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": "consistency.missing_asset_references",
            "action": "restore_points",
            "status": "PASS",
            "summary": self.summary,
            "generated_at": self.generated_at,
            "checks": [check.to_dict() for check in self.checks],
            "items": [
                {
                    "restore_point_id": item.restore_point_id,
                    "repair_run_id": item.repair_run_id,
                    "asset_id": item.asset_id,
                    "created_at": item.created_at,
                    "status": item.status.value,
                    "record_count": item.record_count,
                    "logical_path": item.logical_path,
                    "records": [record.to_dict() for record in item.record_summaries],
                }
                for item in self.items
            ],
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class MissingAssetRestoreResult:
    summary: str
    checks: list[CheckResult]
    repair_run_id: str
    items: list[MissingAssetOperationItem]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        status = (
            CheckStatus.FAIL
            if any(item.status == MissingAssetOperationStatus.FAILED for item in self.items)
            else CheckStatus.PASS
        )
        return {
            "domain": "consistency.missing_asset_references",
            "action": "restore",
            "status": status.value.upper(),
            "summary": self.summary,
            "generated_at": self.generated_at,
            "checks": [check.to_dict() for check in self.checks],
            "repair_run_id": self.repair_run_id,
            "items": [item.to_dict() for item in self.items],
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class MissingAssetRestorePointDeleteResult:
    summary: str
    checks: list[CheckResult]
    items: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": "consistency.missing_asset_references",
            "action": "delete_restore_points",
            "status": "PASS",
            "summary": self.summary,
            "generated_at": self.generated_at,
            "checks": [check.to_dict() for check in self.checks],
            "items": self.items,
            "metadata": self.metadata,
        }
