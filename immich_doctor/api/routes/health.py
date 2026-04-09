from __future__ import annotations

from fastapi import APIRouter, Request

from immich_doctor.api.models import DatabaseOverviewApiResponse, HealthOverviewApiResponse
from immich_doctor.catalog.workflow_service import CatalogWorkflowService
from immich_doctor.core.config import load_settings
from immich_doctor.services.dashboard_health import DashboardHealthService
from immich_doctor.services.database_overview import DatabaseOverviewService

health_router = APIRouter(prefix="/health", tags=["health"])


@health_router.get("/overview", response_model=HealthOverviewApiResponse)
def get_health_overview(request: Request) -> HealthOverviewApiResponse:
    settings = load_settings()
    overview = DashboardHealthService(runtime=request.app.state.backup_job_runtime).run(settings)
    return HealthOverviewApiResponse(data=overview)


@health_router.get("/database", response_model=DatabaseOverviewApiResponse)
def get_database_overview(request: Request) -> DatabaseOverviewApiResponse:
    settings = load_settings()
    overview = DatabaseOverviewService(
        catalog_workflow=CatalogWorkflowService(runtime=request.app.state.backup_job_runtime),
    ).run(settings)
    return DatabaseOverviewApiResponse(data=overview)
