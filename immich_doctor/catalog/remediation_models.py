from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from immich_doctor.core.models import CheckResult, CheckStatus


class CatalogRemediationFindingKind(StrEnum):
    BROKEN_DB_ORIGINAL = "broken_db_original"
    FUSE_HIDDEN_ORPHAN = "fuse_hidden_orphan"


class BrokenDbOriginalClassification(StrEnum):
    MISSING_CONFIRMED = "missing_confirmed"
    FOUND_ELSEWHERE = "found_elsewhere"
    UNRESOLVED_SEARCH_ERROR = "unresolved_search_error"


class FuseHiddenOrphanClassification(StrEnum):
    BLOCKED_IN_USE = "blocked_in_use"
    DELETABLE_ORPHAN = "deletable_orphan"
    CHECK_FAILED = "check_failed"


class CatalogRemediationOperationStatus(StrEnum):
    PLANNED = "planned"
    APPLIED = "applied"
    SKIPPED = "skipped"
    FAILED = "failed"
    ALREADY_REMOVED = "already_removed"


@dataclass(slots=True, frozen=True)
class BrokenDbOriginalFinding:
    finding_id: str
    kind: CatalogRemediationFindingKind
    asset_id: str
    asset_name: str | None
    asset_type: str | None
    expected_database_path: str
    expected_relative_path: str
    classification: BrokenDbOriginalClassification
    action_eligible: bool
    action_reason: str
    found_root_slug: str | None = None
    found_relative_path: str | None = None
    found_absolute_path: str | None = None
    found_size_bytes: int | None = None
    expected_size_bytes: int | None = None
    search_error: str | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "kind": self.kind.value,
            "asset_id": self.asset_id,
            "asset_name": self.asset_name,
            "asset_type": self.asset_type,
            "expected_database_path": self.expected_database_path,
            "expected_relative_path": self.expected_relative_path,
            "classification": self.classification.value,
            "action_eligible": self.action_eligible,
            "action_reason": self.action_reason,
            "found_root_slug": self.found_root_slug,
            "found_relative_path": self.found_relative_path,
            "found_absolute_path": self.found_absolute_path,
            "found_size_bytes": self.found_size_bytes,
            "expected_size_bytes": self.expected_size_bytes,
            "search_error": self.search_error,
            "message": self.message,
        }


@dataclass(slots=True, frozen=True)
class FuseHiddenOrphanFinding:
    finding_id: str
    kind: CatalogRemediationFindingKind
    root_slug: str
    relative_path: str
    absolute_path: str
    file_name: str
    size_bytes: int
    classification: FuseHiddenOrphanClassification
    action_eligible: bool
    action_reason: str
    in_use_check_tool: str | None = None
    in_use_check_reason: str | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "kind": self.kind.value,
            "root_slug": self.root_slug,
            "relative_path": self.relative_path,
            "absolute_path": self.absolute_path,
            "file_name": self.file_name,
            "size_bytes": self.size_bytes,
            "classification": self.classification.value,
            "action_eligible": self.action_eligible,
            "action_reason": self.action_reason,
            "in_use_check_tool": self.in_use_check_tool,
            "in_use_check_reason": self.in_use_check_reason,
            "message": self.message,
        }


@dataclass(slots=True, frozen=True)
class CatalogRemediationOperationItem:
    finding_id: str
    kind: CatalogRemediationFindingKind
    target_id: str
    status: CatalogRemediationOperationStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "kind": self.kind.value,
            "target_id": self.target_id,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
        }


@dataclass(slots=True)
class CatalogRemediationScanResult:
    summary: str
    checks: list[CheckResult]
    broken_db_originals: list[BrokenDbOriginalFinding]
    fuse_hidden_orphans: list[FuseHiddenOrphanFinding]
    metadata: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        if self.broken_db_originals or self.fuse_hidden_orphans:
            statuses.add(CheckStatus.WARN)
        if CheckStatus.FAIL in statuses:
            return CheckStatus.FAIL
        if CheckStatus.WARN in statuses:
            return CheckStatus.WARN
        if CheckStatus.PASS in statuses:
            return CheckStatus.PASS
        return CheckStatus.SKIP

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": "consistency.catalog_remediation",
            "action": "scan",
            "status": self.overall_status.value.upper(),
            "summary": self.summary,
            "generated_at": self.generated_at,
            "checks": [check.to_dict() for check in self.checks],
            "broken_db_originals": [item.to_dict() for item in self.broken_db_originals],
            "fuse_hidden_orphans": [item.to_dict() for item in self.fuse_hidden_orphans],
            "metadata": self.metadata,
            "recommendations": self.recommendations,
        }


@dataclass(slots=True)
class CatalogRemediationPreviewResult:
    summary: str
    checks: list[CheckResult]
    finding_kind: CatalogRemediationFindingKind
    repair_run_id: str
    selected_items: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        if self.selected_items:
            statuses.add(CheckStatus.WARN)
        if CheckStatus.FAIL in statuses:
            return CheckStatus.FAIL
        if CheckStatus.WARN in statuses:
            return CheckStatus.WARN
        return CheckStatus.SKIP

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": "consistency.catalog_remediation",
            "action": "preview",
            "status": self.overall_status.value.upper(),
            "summary": self.summary,
            "generated_at": self.generated_at,
            "checks": [check.to_dict() for check in self.checks],
            "finding_kind": self.finding_kind.value,
            "repair_run_id": self.repair_run_id,
            "selected_items": self.selected_items,
            "metadata": self.metadata,
            "recommendations": self.recommendations,
        }


@dataclass(slots=True)
class CatalogRemediationApplyResult:
    summary: str
    checks: list[CheckResult]
    finding_kind: CatalogRemediationFindingKind
    repair_run_id: str
    items: list[CatalogRemediationOperationItem]
    metadata: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        item_statuses = {item.status for item in self.items}
        if CatalogRemediationOperationStatus.FAILED in item_statuses:
            return CheckStatus.FAIL
        if item_statuses.intersection(
            {
                CatalogRemediationOperationStatus.APPLIED,
                CatalogRemediationOperationStatus.ALREADY_REMOVED,
                CatalogRemediationOperationStatus.SKIPPED,
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
            "domain": "consistency.catalog_remediation",
            "action": "apply",
            "status": self.overall_status.value.upper(),
            "summary": self.summary,
            "generated_at": self.generated_at,
            "checks": [check.to_dict() for check in self.checks],
            "finding_kind": self.finding_kind.value,
            "repair_run_id": self.repair_run_id,
            "items": [item.to_dict() for item in self.items],
            "metadata": self.metadata,
            "recommendations": self.recommendations,
        }
