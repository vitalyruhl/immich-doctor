from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from immich_doctor.core.models import CheckResult, CheckStatus


class CatalogRemediationFindingKind(StrEnum):
    BROKEN_DB_ORIGINAL = "broken_db_original"
    ZERO_BYTE_FILE = "zero_byte_file"
    FUSE_HIDDEN_ORPHAN = "fuse_hidden_orphan"


class CatalogRemediationActionKind(StrEnum):
    BROKEN_DB_CLEANUP = "broken_db_cleanup"
    BROKEN_DB_PATH_FIX = "broken_db_path_fix"
    ZERO_BYTE_DELETE = "zero_byte_delete"
    FUSE_HIDDEN_DELETE = "fuse_hidden_delete"


class BrokenDbOriginalClassification(StrEnum):
    MISSING_CONFIRMED = "missing_confirmed"
    FOUND_ELSEWHERE = "found_elsewhere"
    FOUND_WITH_HASH_MATCH = "found_with_hash_match"
    UNRESOLVED_SEARCH_ERROR = "unresolved_search_error"


class ZeroByteClassification(StrEnum):
    ZERO_BYTE_UPLOAD_ORPHAN = "zero_byte_upload_orphan"
    ZERO_BYTE_UPLOAD_CRITICAL = "zero_byte_upload_critical"
    ZERO_BYTE_VIDEO_DERIVATIVE = "zero_byte_video_derivative"
    ZERO_BYTE_THUMB_DERIVATIVE = "zero_byte_thumb_derivative"
    IGNORE_INTERNAL = "ignore_internal"


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
    classification: BrokenDbOriginalClassification
    expected_database_path: str
    expected_relative_path: str
    expected_absolute_path: str | None
    found_root_slug: str | None
    found_relative_path: str | None
    found_absolute_path: str | None
    found_size_bytes: int | None
    expected_size_bytes: int | None
    checksum_value: str | None
    checksum_algorithm: str | None
    checksum_match: bool | None
    owner_id: str | None
    owner_label: str | None
    eligible_actions: tuple[CatalogRemediationActionKind, ...]
    action_reason: str
    search_error: str | None = None
    message: str = ""

    @property
    def action_eligible(self) -> bool:
        return bool(self.eligible_actions)

    def supports_action(self, action: CatalogRemediationActionKind) -> bool:
        return action in self.eligible_actions

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "kind": self.kind.value,
            "asset_id": self.asset_id,
            "asset_name": self.asset_name,
            "asset_type": self.asset_type,
            "classification": self.classification.value,
            "expected_database_path": self.expected_database_path,
            "expected_relative_path": self.expected_relative_path,
            "expected_absolute_path": self.expected_absolute_path,
            "found_root_slug": self.found_root_slug,
            "found_relative_path": self.found_relative_path,
            "found_absolute_path": self.found_absolute_path,
            "found_size_bytes": self.found_size_bytes,
            "expected_size_bytes": self.expected_size_bytes,
            "checksum_value": self.checksum_value,
            "checksum_algorithm": self.checksum_algorithm,
            "checksum_match": self.checksum_match,
            "owner_id": self.owner_id,
            "owner_label": self.owner_label,
            "eligible_actions": [action.value for action in self.eligible_actions],
            "action_eligible": self.action_eligible,
            "action_reason": self.action_reason,
            "search_error": self.search_error,
            "message": self.message,
        }


@dataclass(slots=True, frozen=True)
class ZeroByteFinding:
    finding_id: str
    kind: CatalogRemediationFindingKind
    root_slug: str
    relative_path: str
    absolute_path: str
    file_name: str
    size_bytes: int
    classification: ZeroByteClassification
    asset_id: str | None
    asset_name: str | None
    owner_id: str | None
    owner_label: str | None
    db_reference_kind: str | None
    original_relative_path: str | None
    eligible_actions: tuple[CatalogRemediationActionKind, ...]
    action_reason: str
    message: str = ""

    @property
    def action_eligible(self) -> bool:
        return bool(self.eligible_actions)

    def supports_action(self, action: CatalogRemediationActionKind) -> bool:
        return action in self.eligible_actions

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
            "asset_id": self.asset_id,
            "asset_name": self.asset_name,
            "owner_id": self.owner_id,
            "owner_label": self.owner_label,
            "db_reference_kind": self.db_reference_kind,
            "original_relative_path": self.original_relative_path,
            "eligible_actions": [action.value for action in self.eligible_actions],
            "action_eligible": self.action_eligible,
            "action_reason": self.action_reason,
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
    owner_id: str | None
    owner_label: str | None
    eligible_actions: tuple[CatalogRemediationActionKind, ...]
    action_reason: str
    in_use_check_tool: str | None = None
    in_use_check_reason: str | None = None
    message: str = ""

    @property
    def action_eligible(self) -> bool:
        return bool(self.eligible_actions)

    def supports_action(self, action: CatalogRemediationActionKind) -> bool:
        return action in self.eligible_actions

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
            "owner_id": self.owner_id,
            "owner_label": self.owner_label,
            "eligible_actions": [action.value for action in self.eligible_actions],
            "action_eligible": self.action_eligible,
            "action_reason": self.action_reason,
            "in_use_check_tool": self.in_use_check_tool,
            "in_use_check_reason": self.in_use_check_reason,
            "message": self.message,
        }


@dataclass(slots=True, frozen=True)
class CatalogIgnoredFinding:
    ignored_item_id: str
    finding_id: str
    category_key: str
    title: str
    owner_id: str | None
    owner_label: str | None
    source_path: str | None
    original_relative_path: str | None
    reason: str
    details: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    released_at: str | None = None
    state: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ignored_item_id": self.ignored_item_id,
            "finding_id": self.finding_id,
            "category_key": self.category_key,
            "title": self.title,
            "owner_id": self.owner_id,
            "owner_label": self.owner_label,
            "source_path": self.source_path,
            "original_relative_path": self.original_relative_path,
            "reason": self.reason,
            "details": self.details,
            "created_at": self.created_at,
            "released_at": self.released_at,
            "state": self.state,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CatalogIgnoredFinding:
        return cls(
            ignored_item_id=str(payload["ignored_item_id"]),
            finding_id=str(payload["finding_id"]),
            category_key=str(payload["category_key"]),
            title=str(payload["title"]),
            owner_id=payload.get("owner_id"),
            owner_label=payload.get("owner_label"),
            source_path=payload.get("source_path"),
            original_relative_path=payload.get("original_relative_path"),
            reason=str(payload["reason"]),
            details=dict(payload.get("details", {})),
            created_at=str(payload["created_at"]),
            released_at=payload.get("released_at"),
            state=str(payload.get("state") or "active"),
        )


@dataclass(slots=True, frozen=True)
class CatalogRemediationOperationItem:
    finding_id: str
    kind: CatalogRemediationFindingKind
    action_kind: CatalogRemediationActionKind
    target_id: str
    status: CatalogRemediationOperationStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "kind": self.kind.value,
            "action_kind": self.action_kind.value,
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
    zero_byte_findings: list[ZeroByteFinding]
    fuse_hidden_orphans: list[FuseHiddenOrphanFinding]
    metadata: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        if self.broken_db_originals or self.zero_byte_findings or self.fuse_hidden_orphans:
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
            "zero_byte_findings": [item.to_dict() for item in self.zero_byte_findings],
            "fuse_hidden_orphans": [item.to_dict() for item in self.fuse_hidden_orphans],
            "metadata": self.metadata,
            "recommendations": self.recommendations,
        }


@dataclass(slots=True)
class CatalogRemediationPreviewResult:
    summary: str
    checks: list[CheckResult]
    finding_kind: CatalogRemediationFindingKind
    action_kind: CatalogRemediationActionKind
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
            "action_kind": self.action_kind.value,
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
    action_kind: CatalogRemediationActionKind
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
            "action_kind": self.action_kind.value,
            "repair_run_id": self.repair_run_id,
            "items": [item.to_dict() for item in self.items],
            "metadata": self.metadata,
            "recommendations": self.recommendations,
        }
