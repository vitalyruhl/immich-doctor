from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from immich_doctor.backup.core.job_models import BackgroundJobState


class BackupSizeEstimateStatus(StrEnum):
    UNKNOWN = "unknown"
    STALE = "stale"
    QUEUED = "queued"
    RUNNING = "running"
    PARTIAL = "partial"
    COMPLETED = "completed"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    CANCELED = "canceled"


class BackupSizeCategory(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    label: str
    path: str | None = None
    bytes: int | None = None
    file_count: int | None = Field(default=None, alias="fileCount")


class BackupSizeProgress(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    scope: str | None = None
    message: str
    current: int | None = None
    total: int | None = None
    unit: str | None = None
    current_path: str | None = Field(default=None, alias="currentPath")


class BackupSizeScopeEstimate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    scope: str
    label: str
    state: BackgroundJobState
    source_scope: str = Field(alias="sourceScope")
    representation: str
    bytes: int | None = None
    file_count: int | None = Field(default=None, alias="fileCount")
    collected_at: str | None = Field(default=None, alias="collectedAt")
    duration_seconds: float | None = Field(default=None, alias="durationSeconds")
    stale: bool = False
    categories: list[BackupSizeCategory] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class BackupSizeEstimateSnapshot(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    generated_at: str = Field(alias="generatedAt")
    job_id: str | None = Field(default=None, alias="jobId")
    state: BackgroundJobState
    status: BackupSizeEstimateStatus = BackupSizeEstimateStatus.UNKNOWN
    summary: str
    source_scope: str = Field(alias="sourceScope")
    collected_at: str | None = Field(default=None, alias="collectedAt")
    duration_seconds: float | None = Field(default=None, alias="durationSeconds")
    cache_age_seconds: float | None = Field(default=None, alias="cacheAgeSeconds")
    stale: bool = False
    stale_reason: str | None = Field(default=None, alias="staleReason")
    scopes: list[BackupSizeScopeEstimate] = Field(default_factory=list)
    progress: BackupSizeProgress | None = None
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
