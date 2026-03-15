from __future__ import annotations

from fastapi import APIRouter

from immich_doctor.api.models import HealthOverviewApiResponse
from immich_doctor.core.config import load_settings
from immich_doctor.services.dashboard_health import DashboardHealthService

health_router = APIRouter(prefix="/health", tags=["health"])


@health_router.get("/overview", response_model=HealthOverviewApiResponse)
def get_health_overview() -> HealthOverviewApiResponse:
    settings = load_settings()
    overview = DashboardHealthService().run(settings)
    return HealthOverviewApiResponse(data=overview)
