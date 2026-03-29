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


class MissingAssetRepairBlockerType(StrEnum):
    PATH = "path"
    FILESYSTEM = "filesystem"
    SCOPE = "scope"
    SCHEMA = "schema"


class MissingAssetBlockingSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class MissingAssetScanState(StrEnum):
    IDLE = "idle"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class MissingAssetScanFailureKind(StrEnum):
    EXCEPTION = "exception"
    INTERRUPTED = "interrupted"


@dataclass(slots=True, frozen=True)
class MissingAssetRepairBlocker:
    blocker_code: str
    blocker_type: MissingAssetRepairBlockerType | str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    affected_tables: tuple[str, ...] = ()
    repair_covered_tables: tuple[str, ...] = ()
    blocking_severity: MissingAssetBlockingSeverity | str = MissingAssetBlockingSeverity.ERROR
    is_repairable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocker_code": self.blocker_code,
            "blocker_type": (
                self.blocker_type.value
                if isinstance(self.blocker_type, MissingAssetRepairBlockerType)
                else self.blocker_type
            ),
            "summary": self.summary,
            "details": self.details,
            "affected_tables": list(self.affected_tables),
            "repair_covered_tables": list(self.repair_covered_tables),
            "blocking_severity": (
                self.blocking_severity.value
                if isinstance(self.blocking_severity, MissingAssetBlockingSeverity)
                else self.blocking_severity
            ),
            "is_repairable": self.is_repairable,
        }


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
    repair_blocker_details: tuple[MissingAssetRepairBlocker, ...] = ()
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
            "repair_blocker_details": [
                blocker.to_dict() for blocker in self.repair_blocker_details
            ],
            "message": self.message,
        }


@dataclass(slots=True, frozen=True)
class MissingAssetRestorePointRecord:
    table: str
    row_count: int

    def to_dict(self) -> dict[str, Any]:
        return {"table": self.table, "row_count": self.row_count}


@dataclass(slots=True, frozen=True)
class MissingAssetScanJob:
    scan_id: str
    state: MissingAssetScanState
    requested_at: str
    updated_at: str
    summary: str
    started_at: str | None = None
    finished_at: str | None = None
    result_count: int = 0
    scanned_asset_count: int = 0
    error_message: str | None = None
    failure_kind: MissingAssetScanFailureKind | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "state": self.state.value,
            "requested_at": self.requested_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": self.summary,
            "result_count": self.result_count,
            "scanned_asset_count": self.scanned_asset_count,
            "error_message": self.error_message,
            "failure_kind": self.failure_kind.value if self.failure_kind is not None else None,
        }


@dataclass(slots=True, frozen=True)
class MissingAssetCompletedScanSummary:
    scan_id: str
    status: str
    summary: str
    generated_at: str
    completed_at: str
    finding_count: int
    missing_on_disk_count: int
    ready_count: int
    blocked_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "status": self.status,
            "summary": self.summary,
            "generated_at": self.generated_at,
            "completed_at": self.completed_at,
            "finding_count": self.finding_count,
            "missing_on_disk_count": self.missing_on_disk_count,
            "ready_count": self.ready_count,
            "blocked_count": self.blocked_count,
        }


@dataclass(slots=True)
class MissingAssetScanStatusResult:
    summary: str
    scan_state: MissingAssetScanState
    active_scan: MissingAssetScanJob | None = None
    latest_completed: MissingAssetCompletedScanSummary | None = None
    checks: list[CheckResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        if self.scan_state == MissingAssetScanState.FAILED:
            return CheckStatus.FAIL
        if self.scan_state in {MissingAssetScanState.PENDING, MissingAssetScanState.RUNNING}:
            return CheckStatus.WARN
        if self.latest_completed is not None:
            normalized = self.latest_completed.status.lower()
            if normalized == "fail":
                return CheckStatus.FAIL
            if normalized == "warn":
                return CheckStatus.WARN
            if normalized == "pass":
                return CheckStatus.PASS
        if self.scan_state == MissingAssetScanState.COMPLETED:
            return CheckStatus.PASS
        return CheckStatus.SKIP

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": "consistency.missing_asset_references",
            "action": "scan_status",
            "status": self.overall_status.value.upper(),
            "summary": self.summary,
            "generated_at": self.generated_at,
            "scan_state": self.scan_state.value,
            "active_scan": self.active_scan.to_dict() if self.active_scan is not None else None,
            "latest_completed": (
                self.latest_completed.to_dict() if self.latest_completed is not None else None
            ),
            "checks": [check.to_dict() for check in self.checks],
            "metadata": self.metadata,
            "recommendations": self.recommendations,
        }


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
