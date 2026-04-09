from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from immich_doctor.api.models import (
    SettingsOverviewApiResponse,
    SettingsSchemaApiResponse,
    SettingsUpdateApiResponse,
    TestbedDumpImportApiResponse,
    TestbedDumpOverviewApiResponse,
)
from immich_doctor.core.config import load_settings
from immich_doctor.services.settings_service import SettingsService, SettingsUpdatePayload
from immich_doctor.services.testbed_dump_service import (
    TestbedDumpImportService,
    TestbedDumpServiceError,
)

settings_router = APIRouter(prefix="/settings", tags=["settings"])


class TestbedDumpImportRequest(BaseModel):
    path: str | None = None
    format: str = "auto"
    force: bool = False


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


@settings_router.get("/testbed/dump", response_model=TestbedDumpOverviewApiResponse)
def get_testbed_dump_overview() -> TestbedDumpOverviewApiResponse:
    settings = load_settings()
    overview = TestbedDumpImportService().get_overview(settings)
    if not overview.enabled:
        raise HTTPException(status_code=404, detail="Testbed dump import is unavailable.")
    return TestbedDumpOverviewApiResponse(data=overview.model_dump(by_alias=True, mode="json"))


@settings_router.post("/testbed/dump/import", response_model=TestbedDumpImportApiResponse)
def import_testbed_dump(payload: TestbedDumpImportRequest) -> TestbedDumpImportApiResponse:
    settings = load_settings()
    try:
        result = TestbedDumpImportService().import_dump(
            settings,
            requested_path=payload.path,
            dump_format=payload.format,
            force=payload.force,
        )
    except TestbedDumpServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TestbedDumpImportApiResponse(data=result.model_dump(by_alias=True, mode="json"))
