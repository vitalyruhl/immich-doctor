from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from immich_doctor.services.dashboard_health import DashboardHealthOverview
from immich_doctor.services.settings_service import (
    SettingsOverview,
    SettingsSchema,
    SettingsUpdateResult,
)


class HealthOverviewApiResponse(BaseModel):
    data: DashboardHealthOverview
    source: Literal["backend"] = "backend"
    mocked: bool = False


class SettingsOverviewApiResponse(BaseModel):
    data: SettingsOverview
    source: Literal["backend"] = "backend"
    mocked: bool = False


class SettingsSchemaApiResponse(BaseModel):
    data: SettingsSchema
    source: Literal["backend"] = "backend"
    mocked: bool = False


class SettingsUpdateApiResponse(BaseModel):
    data: SettingsUpdateResult
    source: Literal["backend"] = "backend"
    mocked: bool = False
