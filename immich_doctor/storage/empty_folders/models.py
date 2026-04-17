from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from immich_doctor.core.models import CheckResult, CheckStatus


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True, frozen=True)
class EmptyDirectoryFinding:
    root_slug: str
    relative_path: str
    absolute_path: Path
    depth: int
    size_bytes: int | None
    last_modified_at: str | None
    child_count_before: int = 0
    is_orphan_parent: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_slug": self.root_slug,
            "relative_path": self.relative_path,
            "absolute_path": str(self.absolute_path),
            "depth": self.depth,
            "size_bytes": self.size_bytes,
            "last_modified_at": self.last_modified_at,
            "child_count_before": self.child_count_before,
            "is_orphan_parent": self.is_orphan_parent,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EmptyDirectoryFinding:
        return cls(
            root_slug=str(payload.get("root_slug") or ""),
            relative_path=str(payload.get("relative_path") or ""),
            absolute_path=Path(str(payload.get("absolute_path") or "")),
            depth=int(payload.get("depth") or 0),
            size_bytes=(
                int(payload["size_bytes"]) if payload.get("size_bytes") is not None else None
            ),
            last_modified_at=(
                str(payload["last_modified_at"])
                if payload.get("last_modified_at") is not None
                else None
            ),
            child_count_before=int(payload.get("child_count_before") or 0),
            is_orphan_parent=bool(payload.get("is_orphan_parent")),
        )


@dataclass(slots=True)
class EmptyFolderScanReport:
    domain: str
    action: str
    summary: str
    checks: list[CheckResult]
    findings: list[EmptyDirectoryFinding] = field(default_factory=list)
    orphan_parents: list[EmptyDirectoryFinding] = field(default_factory=list)
    symlink_directories: list[dict[str, str]] = field(default_factory=list)
    entry_errors: list[dict[str, str]] = field(default_factory=list)
    roots_scanned: list[str] = field(default_factory=list)
    roots_with_errors: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=utcnow)

    @property
    def total_empty_dirs(self) -> int:
        return len(self.findings)

    @property
    def total_orphan_parents(self) -> int:
        return len(self.orphan_parents)

    @property
    def reclaimed_space_bytes(self) -> int:
        return sum(finding.size_bytes or 0 for finding in self.findings)

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {check.status for check in self.checks}
        if CheckStatus.FAIL in statuses:
            return CheckStatus.FAIL
        if self.findings or self.orphan_parents or self.symlink_directories or self.entry_errors:
            return CheckStatus.WARN
        if CheckStatus.PASS in statuses:
            return CheckStatus.PASS
        return CheckStatus.SKIP

    @property
    def exit_code(self) -> int:
        return 1 if self.overall_status == CheckStatus.FAIL else 0

    def to_dict(self) -> dict[str, Any]:
        findings_by_root: dict[str, list[dict[str, Any]]] = {}
        orphan_parents_by_root: dict[str, list[dict[str, Any]]] = {}
        for finding in self.findings:
            findings_by_root.setdefault(finding.root_slug, []).append(finding.to_dict())
        for finding in self.orphan_parents:
            orphan_parents_by_root.setdefault(finding.root_slug, []).append(finding.to_dict())
        return {
            "domain": self.domain,
            "action": self.action,
            "status": self.overall_status.value.upper(),
            "summary": self.summary,
            "generated_at": self.generated_at,
            "metadata": self.metadata,
            "checks": [check.to_dict() for check in self.checks],
            "total_empty_dirs": self.total_empty_dirs,
            "total_orphan_parents": self.total_orphan_parents,
            "reclaimed_space_bytes": self.reclaimed_space_bytes,
            "roots_scanned": len(self.roots_scanned),
            "root_slugs_scanned": list(self.roots_scanned),
            "roots_with_errors": dict(self.roots_with_errors),
            "findings": [finding.to_dict() for finding in self.findings],
            "findings_by_root": findings_by_root,
            "orphan_parents": [finding.to_dict() for finding in self.orphan_parents],
            "orphan_parents_by_root": orphan_parents_by_root,
            "symlink_directories": list(self.symlink_directories),
            "entry_errors": list(self.entry_errors),
        }


@dataclass(slots=True, frozen=True)
class EmptyDirQuarantineItem:
    quarantine_item_id: str
    session_id: str
    root_slug: str
    relative_path: str
    original_path: str
    quarantine_path: str
    reason: str
    size_bytes: int | None
    last_modified_at: str | None
    mode: int | None = None
    state: str = "active"
    created_at: str = field(default_factory=utcnow)
    state_changed_at: str | None = None
    deleted_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "quarantine_item_id": self.quarantine_item_id,
            "session_id": self.session_id,
            "root_slug": self.root_slug,
            "relative_path": self.relative_path,
            "original_path": self.original_path,
            "quarantine_path": self.quarantine_path,
            "reason": self.reason,
            "size_bytes": self.size_bytes,
            "last_modified_at": self.last_modified_at,
            "mode": self.mode,
            "state": self.state,
            "created_at": self.created_at,
            "state_changed_at": self.state_changed_at,
            "deleted_at": self.deleted_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EmptyDirQuarantineItem:
        return cls(
            quarantine_item_id=str(payload.get("quarantine_item_id") or ""),
            session_id=str(payload.get("session_id") or ""),
            root_slug=str(payload.get("root_slug") or ""),
            relative_path=str(payload.get("relative_path") or ""),
            original_path=str(payload.get("original_path") or ""),
            quarantine_path=str(payload.get("quarantine_path") or ""),
            reason=str(payload.get("reason") or ""),
            size_bytes=(
                int(payload["size_bytes"]) if payload.get("size_bytes") is not None else None
            ),
            last_modified_at=(
                str(payload["last_modified_at"])
                if payload.get("last_modified_at") is not None
                else None
            ),
            mode=int(payload["mode"]) if payload.get("mode") is not None else None,
            state=str(payload.get("state") or "active"),
            created_at=str(payload.get("created_at") or utcnow()),
            state_changed_at=(
                str(payload["state_changed_at"])
                if payload.get("state_changed_at") is not None
                else None
            ),
            deleted_at=(
                str(payload["deleted_at"])
                if payload.get("deleted_at") is not None
                else None
            ),
        )

    def mark_restored(self) -> EmptyDirQuarantineItem:
        return EmptyDirQuarantineItem(
            **{
                **self.to_dict(),
                "state": "restored",
                "state_changed_at": utcnow(),
            }
        )

    def mark_deleted(self) -> EmptyDirQuarantineItem:
        timestamp = utcnow()
        return EmptyDirQuarantineItem(
            **{
                **self.to_dict(),
                "state": "deleted",
                "state_changed_at": timestamp,
                "deleted_at": timestamp,
            }
        )


@dataclass(slots=True, frozen=True)
class EmptyDirQuarantineSession:
    session_id: str
    created_at: str
    root_slugs: tuple[str, ...]
    requested_paths: tuple[str, ...]
    dry_run: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "root_slugs": list(self.root_slugs),
            "requested_paths": list(self.requested_paths),
            "dry_run": self.dry_run,
            "reason": self.reason,
        }

    @classmethod
    def new(
        cls,
        *,
        root_slugs: tuple[str, ...],
        requested_paths: tuple[str, ...],
        dry_run: bool,
        reason: str,
    ) -> EmptyDirQuarantineSession:
        return cls(
            session_id=uuid4().hex,
            created_at=utcnow(),
            root_slugs=root_slugs,
            requested_paths=requested_paths,
            dry_run=dry_run,
            reason=reason,
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EmptyDirQuarantineSession:
        return cls(
            session_id=str(payload.get("session_id") or ""),
            created_at=str(payload.get("created_at") or utcnow()),
            root_slugs=tuple(str(item) for item in payload.get("root_slugs", [])),
            requested_paths=tuple(str(item) for item in payload.get("requested_paths", [])),
            dry_run=bool(payload.get("dry_run")),
            reason=str(payload.get("reason") or ""),
        )


@dataclass(slots=True)
class EmptyDirQuarantineResult:
    summary: str
    dry_run: bool
    session_id: str | None
    items: list[EmptyDirQuarantineItem] = field(default_factory=list)
    failed: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "dry_run": self.dry_run,
            "session_id": self.session_id,
            "quarantined_count": len(self.items),
            "items": [item.to_dict() for item in self.items],
            "failed": list(self.failed),
        }


@dataclass(slots=True)
class EmptyDirRestoreResult:
    summary: str
    dry_run: bool
    restored: list[EmptyDirQuarantineItem] = field(default_factory=list)
    failed: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "dry_run": self.dry_run,
            "restored_count": len(self.restored),
            "restored": [item.to_dict() for item in self.restored],
            "failed": list(self.failed),
        }


@dataclass(slots=True)
class EmptyDirDeleteResult:
    summary: str
    dry_run: bool
    deleted: list[EmptyDirQuarantineItem] = field(default_factory=list)
    failed: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "dry_run": self.dry_run,
            "deleted_count": len(self.deleted),
            "deleted": [item.to_dict() for item in self.deleted],
            "failed": list(self.failed),
        }
