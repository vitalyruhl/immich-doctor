from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from immich_doctor.api.models import (
    RuntimeIntegrityApiResponse,
    RuntimeMetadataFailuresInspectApiResponse,
    RuntimeMetadataFailuresRepairApiResponse,
    RuntimeRepairReadinessApiResponse,
)
from immich_doctor.core.config import load_settings
from immich_doctor.runtime.integrity.service import RuntimeIntegrityInspectService
from immich_doctor.runtime.metadata_failures.repair_service import (
    RuntimeMetadataFailuresRepairService,
)
from immich_doctor.runtime.metadata_failures.service import (
    RuntimeMetadataFailuresInspectService,
)
from immich_doctor.services.runtime_repair_readiness_service import (
    RuntimeRepairReadinessService,
)

runtime_router = APIRouter(prefix="/runtime", tags=["runtime"])


class RuntimeMetadataFailuresRepairRequest(BaseModel):
    apply: bool = False
    limit: int | None = Field(default=100, ge=1)
    offset: int = Field(default=0, ge=0)
    diagnostic_ids: list[str] = Field(default_factory=list)
    retry_jobs: bool = False
    requeue: bool = False
    fix_permissions: bool = False
    quarantine_corrupt: bool = False
    mark_unrecoverable: bool = False


@runtime_router.get("/integrity/inspect", response_model=RuntimeIntegrityApiResponse)
def inspect_runtime_integrity(
    limit: int = 100,
    offset: int = 0,
    include_derivatives: bool = True,
) -> RuntimeIntegrityApiResponse:
    result = RuntimeIntegrityInspectService().run(
        load_settings(),
        limit=limit,
        offset=offset,
        include_derivatives=include_derivatives,
    )
    return RuntimeIntegrityApiResponse(data=result)


@runtime_router.get(
    "/metadata-failures/inspect",
    response_model=RuntimeMetadataFailuresInspectApiResponse,
)
def inspect_runtime_metadata_failures(
    limit: int = 100,
    offset: int = 0,
) -> RuntimeMetadataFailuresInspectApiResponse:
    result = RuntimeMetadataFailuresInspectService().run(
        load_settings(),
        limit=limit,
        offset=offset,
    )
    return RuntimeMetadataFailuresInspectApiResponse(data=result)


@runtime_router.post(
    "/metadata-failures/repair",
    response_model=RuntimeMetadataFailuresRepairApiResponse,
)
def repair_runtime_metadata_failures(
    payload: RuntimeMetadataFailuresRepairRequest,
) -> RuntimeMetadataFailuresRepairApiResponse:
    result = RuntimeMetadataFailuresRepairService().run(
        load_settings(),
        apply=payload.apply,
        limit=payload.limit,
        offset=payload.offset,
        diagnostic_ids=tuple(payload.diagnostic_ids),
        retry_jobs=payload.retry_jobs,
        requeue=payload.requeue,
        fix_permissions=payload.fix_permissions,
        quarantine_corrupt=payload.quarantine_corrupt,
        mark_unrecoverable=payload.mark_unrecoverable,
    )
    return RuntimeMetadataFailuresRepairApiResponse(data=result)


@runtime_router.get(
    "/metadata-failures/repair-readiness",
    response_model=RuntimeRepairReadinessApiResponse,
)
def runtime_metadata_failures_repair_readiness() -> RuntimeRepairReadinessApiResponse:
    data = RuntimeRepairReadinessService().run(load_settings())
    return RuntimeRepairReadinessApiResponse(data=data)
