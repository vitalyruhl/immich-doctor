"""Foundational backup data models without operational logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

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


@dataclass(slots=True, frozen=True)
class BackupArtifact:
    """Describes one produced backup artifact and its intended metadata surface."""

    name: str
    kind: ArtifactKind
    target: BackupTarget
    relative_path: Path
    size_bytes: int | None = None
    checksum: str | None = None


@dataclass(slots=True, frozen=True)
class BackupManifest:
    """Captures the future manifest shape for a completed backup run."""

    timestamp: datetime
    included_components: tuple[ComponentName, ...]
    artifacts: tuple[BackupArtifact, ...]
    versions: dict[str, str] = field(default_factory=dict)
    environment_hints: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class BackupContext:
    """Carries immutable context metadata for one backup workflow execution."""

    job_name: str
    requested_components: tuple[ComponentName, ...]
    target: BackupTarget
    started_at: datetime
    initiated_by: str = "manual"
    correlation_id: str | None = None


@dataclass(slots=True, frozen=True)
class BackupJob:
    """Defines one future backup unit of work in orchestration order."""

    name: str
    component: ComponentName
    description: str
    target: BackupTarget
    order: int = 0
    requires_lock: bool = True


@dataclass(slots=True, frozen=True)
class BackupResult:
    """Describes the future result contract of a backup workflow or sub-job."""

    status: BackupStatus
    summary: str
    context: BackupContext
    artifacts: tuple[BackupArtifact, ...] = ()
    manifest: BackupManifest | None = None
    warnings: tuple[str, ...] = ()
