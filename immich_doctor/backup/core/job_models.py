from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BackgroundJobState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    RESUMING = "resuming"
    STOPPING = "stopping"
    STOPPED = "stopped"
    PARTIAL = "partial"
    COMPLETED = "completed"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELED = "canceled"


TERMINAL_BACKGROUND_JOB_STATES = frozenset(
    {
        BackgroundJobState.PARTIAL,
        BackgroundJobState.COMPLETED,
        BackgroundJobState.FAILED,
        BackgroundJobState.UNSUPPORTED,
        BackgroundJobState.CANCELED,
        BackgroundJobState.PAUSED,
        BackgroundJobState.STOPPED,
    }
)


class BackgroundJobRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    job_id: str = Field(alias="jobId")
    job_type: str = Field(alias="jobType")
    state: BackgroundJobState
    summary: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        alias="createdAt",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        alias="updatedAt",
    )
    started_at: str | None = Field(default=None, alias="startedAt")
    completed_at: str | None = Field(default=None, alias="completedAt")
    cancel_requested: bool = Field(default=False, alias="cancelRequested")
    error: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
