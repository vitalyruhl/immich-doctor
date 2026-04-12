from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class RepairRunStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class RepairJournalEntryStatus(StrEnum):
    PLANNED = "planned"
    APPLIED = "applied"
    SKIPPED = "skipped"
    FAILED = "failed"


class UndoType(StrEnum):
    NONE = "none"
    RESTORE_PERMISSIONS = "restore_permissions"
    RESTORE_DB_VALUES = "restore_db_values"
    RESTORE_QUARANTINE_FILE = "restore_quarantine_file"


@dataclass(slots=True, frozen=True)
class PlanToken:
    token_id: str
    created_at: str
    scope: dict[str, Any]
    db_fingerprint: str
    file_fingerprint: str
    expires_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "created_at": self.created_at,
            "scope": self.scope,
            "db_fingerprint": self.db_fingerprint,
            "file_fingerprint": self.file_fingerprint,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PlanToken:
        return cls(
            token_id=payload["token_id"],
            created_at=payload["created_at"],
            scope=dict(payload["scope"]),
            db_fingerprint=payload["db_fingerprint"],
            file_fingerprint=payload["file_fingerprint"],
            expires_at=payload.get("expires_at"),
        )


@dataclass(slots=True)
class RepairRun:
    repair_run_id: str
    started_at: str
    ended_at: str | None
    scope: dict[str, Any]
    status: RepairRunStatus
    live_state_fingerprint: str
    plan_token_id: str
    pre_repair_snapshot_id: str | None = None
    post_repair_snapshot_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "repair_run_id": self.repair_run_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "scope": self.scope,
            "status": self.status.value,
            "live_state_fingerprint": self.live_state_fingerprint,
            "plan_token_id": self.plan_token_id,
            "pre_repair_snapshot_id": self.pre_repair_snapshot_id,
            "post_repair_snapshot_id": self.post_repair_snapshot_id,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RepairRun:
        return cls(
            repair_run_id=payload["repair_run_id"],
            started_at=payload["started_at"],
            ended_at=payload.get("ended_at"),
            scope=dict(payload["scope"]),
            status=RepairRunStatus(payload["status"]),
            live_state_fingerprint=payload["live_state_fingerprint"],
            plan_token_id=payload["plan_token_id"],
            pre_repair_snapshot_id=payload.get("pre_repair_snapshot_id"),
            post_repair_snapshot_id=payload.get("post_repair_snapshot_id"),
        )

    @classmethod
    def new(
        cls,
        *,
        repair_run_id: str,
        scope: dict[str, Any],
        status: RepairRunStatus,
        live_state_fingerprint: str,
        plan_token_id: str,
        pre_repair_snapshot_id: str | None = None,
        post_repair_snapshot_id: str | None = None,
    ) -> RepairRun:
        return cls(
            repair_run_id=repair_run_id,
            started_at=datetime.now(UTC).isoformat(),
            ended_at=None,
            scope=scope,
            status=status,
            live_state_fingerprint=live_state_fingerprint,
            plan_token_id=plan_token_id,
            pre_repair_snapshot_id=pre_repair_snapshot_id,
            post_repair_snapshot_id=post_repair_snapshot_id,
        )

    def finish(self, status: RepairRunStatus) -> None:
        self.status = status
        self.ended_at = datetime.now(UTC).isoformat()


@dataclass(slots=True, frozen=True)
class RepairJournalEntry:
    entry_id: str
    repair_run_id: str
    operation_type: str
    status: RepairJournalEntryStatus
    asset_id: str | None
    table: str | None
    old_db_values: dict[str, Any] | None
    new_db_values: dict[str, Any] | None
    original_path: str | None
    quarantine_path: str | None
    undo_type: UndoType
    undo_payload: dict[str, Any]
    error_details: dict[str, Any] | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "repair_run_id": self.repair_run_id,
            "operation_type": self.operation_type,
            "status": self.status.value,
            "asset_id": self.asset_id,
            "table": self.table,
            "old_db_values": self.old_db_values,
            "new_db_values": self.new_db_values,
            "original_path": self.original_path,
            "quarantine_path": self.quarantine_path,
            "undo_type": self.undo_type.value,
            "undo_payload": self.undo_payload,
            "error_details": self.error_details,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RepairJournalEntry:
        return cls(
            entry_id=payload["entry_id"],
            repair_run_id=payload["repair_run_id"],
            operation_type=payload["operation_type"],
            status=RepairJournalEntryStatus(payload["status"]),
            asset_id=payload.get("asset_id"),
            table=payload.get("table"),
            old_db_values=payload.get("old_db_values"),
            new_db_values=payload.get("new_db_values"),
            original_path=payload.get("original_path"),
            quarantine_path=payload.get("quarantine_path"),
            undo_type=UndoType(payload["undo_type"]),
            undo_payload=dict(payload.get("undo_payload", {})),
            error_details=payload.get("error_details"),
            created_at=payload["created_at"],
        )


@dataclass(slots=True, frozen=True)
class QuarantineItem:
    quarantine_item_id: str
    repair_run_id: str
    asset_id: str | None
    source_path: str
    quarantine_path: str
    reason: str
    checksum: str | None = None
    size_bytes: int | None = None
    restorable: bool = True
    owner_id: str | None = None
    owner_label: str | None = None
    category_key: str | None = None
    finding_id: str | None = None
    source_kind: str | None = None
    root_slug: str | None = None
    relative_path: str | None = None
    original_relative_path: str | None = None
    db_reference_kind: str | None = None
    state: str = "active"
    state_changed_at: str | None = None
    deleted_at: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "quarantine_item_id": self.quarantine_item_id,
            "repair_run_id": self.repair_run_id,
            "asset_id": self.asset_id,
            "source_path": self.source_path,
            "quarantine_path": self.quarantine_path,
            "reason": self.reason,
            "checksum": self.checksum,
            "size_bytes": self.size_bytes,
            "restorable": self.restorable,
            "owner_id": self.owner_id,
            "owner_label": self.owner_label,
            "category_key": self.category_key,
            "finding_id": self.finding_id,
            "source_kind": self.source_kind,
            "root_slug": self.root_slug,
            "relative_path": self.relative_path,
            "original_relative_path": self.original_relative_path,
            "db_reference_kind": self.db_reference_kind,
            "state": self.state,
            "state_changed_at": self.state_changed_at,
            "deleted_at": self.deleted_at,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> QuarantineItem:
        return cls(
            quarantine_item_id=payload["quarantine_item_id"],
            repair_run_id=payload["repair_run_id"],
            asset_id=payload.get("asset_id"),
            source_path=payload["source_path"],
            quarantine_path=payload["quarantine_path"],
            reason=payload["reason"],
            checksum=payload.get("checksum"),
            size_bytes=payload.get("size_bytes"),
            restorable=bool(payload["restorable"]),
            owner_id=payload.get("owner_id"),
            owner_label=payload.get("owner_label"),
            category_key=payload.get("category_key"),
            finding_id=payload.get("finding_id"),
            source_kind=payload.get("source_kind"),
            root_slug=payload.get("root_slug"),
            relative_path=payload.get("relative_path"),
            original_relative_path=payload.get("original_relative_path"),
            db_reference_kind=payload.get("db_reference_kind"),
            state=str(payload.get("state") or "active"),
            state_changed_at=payload.get("state_changed_at"),
            deleted_at=payload.get("deleted_at"),
            created_at=payload["created_at"],
        )
