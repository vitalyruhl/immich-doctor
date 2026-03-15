from __future__ import annotations

from fastapi import APIRouter

from immich_doctor.api.models import (
    SettingsOverviewApiResponse,
    SettingsSchemaApiResponse,
    SettingsUpdateApiResponse,
)
from immich_doctor.core.config import load_settings
from immich_doctor.services.settings_service import SettingsService, SettingsUpdatePayload

settings_router = APIRouter(prefix="/settings", tags=["settings"])


@settings_router.get("", response_model=SettingsOverviewApiResponse)
def get_settings() -> SettingsOverviewApiResponse:
    overview = SettingsService().get_overview(load_settings())
    return SettingsOverviewApiResponse(data=overview)


@settings_router.get("/schema", response_model=SettingsSchemaApiResponse)
def get_settings_schema() -> SettingsSchemaApiResponse:
    schema = SettingsService().get_schema()
    return SettingsSchemaApiResponse(data=schema)


@settings_router.put("", response_model=SettingsUpdateApiResponse)
def update_settings(payload: SettingsUpdatePayload) -> SettingsUpdateApiResponse:
    result = SettingsService().update_settings(payload)
    return SettingsUpdateApiResponse(data=result)
