from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from immich_doctor.services.dashboard_health import DashboardHealthOverview


class HealthOverviewApiResponse(BaseModel):
    data: DashboardHealthOverview
    source: Literal["backend"] = "backend"
    mocked: bool = False
