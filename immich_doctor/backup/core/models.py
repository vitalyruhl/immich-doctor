"""Foundational backup data models without operational logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

ComponentName = Literal["database", "files", "metadata", "reports", "config"]
TargetKind = Literal["local", "docker", "remote"]
ArtifactKind = Literal["database_dump", "file_archive", "metadata_snapshot", "manifest"]
BackupStatus = Literal["pending", "success", "warn", "fail"]


@dataclass(slots=True, frozen=True)
class BackupTarget:
    """Describes a future backup destination without resolving or writing to it."""

    kind: TargetKind
    reference: str
    display_name: str
    writable_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "reference": self.reference,
            "display_name": self.display_name,
            "writable_required": self.writable_required,
        }


@dataclass(slots=True, frozen=True)
class ResolvedBackupLocation:
    """Resolves a logical backup target to a concrete path for one operation."""

    target: BackupTarget
    root_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target.to_dict(),
            "root_path": self.root_path.as_posix(),
        }


@dataclass(slots=True, frozen=True)
class BackupArtifact:
    """Describes one produced backup artifact and its intended metadata surface."""

    name: str
    kind: ArtifactKind
    target: BackupTarget
    relative_path: Path
    size_bytes: int | None = None
    checksum: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "target": self.target.to_dict(),
            "relative_path": self.relative_path.as_posix(),
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
        }


@dataclass(slots=True, frozen=True)
class BackupManifest:
    """Captures the future manifest shape for a completed backup run."""

    timestamp: datetime
    included_components: tuple[ComponentName, ...]
    artifacts: tuple[BackupArtifact, ...]
    versions: dict[str, str] = field(default_factory=dict)
    environment_hints: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "included_components": list(self.included_components),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "versions": self.versions,
            "environment_hints": self.environment_hints,
        }


@dataclass(slots=True, frozen=True)
class BackupContext:
    """Carries immutable context metadata for one backup workflow execution."""

    job_name: str
    requested_components: tuple[ComponentName, ...]
    target: BackupTarget
    started_at: datetime
    initiated_by: str = "manual"
    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_name": self.job_name,
            "requested_components": list(self.requested_components),
            "target": self.target.to_dict(),
            "started_at": self.started_at.isoformat(),
            "initiated_by": self.initiated_by,
            "correlation_id": self.correlation_id,
        }


@dataclass(slots=True, frozen=True)
class BackupJob:
    """Defines one future backup unit of work in orchestration order."""

    name: str
    component: ComponentName
    description: str
    target: BackupTarget
    order: int = 0
    requires_lock: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "component": self.component,
            "description": self.description,
            "target": self.target.to_dict(),
            "order": self.order,
            "requires_lock": self.requires_lock,
        }


@dataclass(slots=True, frozen=True)
class BackupResult:
    """Describes the future result contract of a backup workflow or sub-job."""

    domain: str
    action: str
    status: BackupStatus
    summary: str
    context: BackupContext
    artifacts: tuple[BackupArtifact, ...] = ()
    manifest: BackupManifest | None = None
    warnings: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return 0 if self.status in {"success", "warn"} else 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "action": self.action,
            "status": self.status.upper(),
            "summary": self.summary,
            "context": self.context.to_dict(),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "manifest": self.manifest.to_dict() if self.manifest else None,
            "warnings": list(self.warnings),
            "details": self.details,
        }
