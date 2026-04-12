from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from immich_doctor.runtime.integrity.models import FileIntegrityInspectResult
from immich_doctor.runtime.metadata_failures.models import (
    MetadataFailureInspectResult,
    MetadataFailureRepairResult,
)
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


class DatabaseOverviewApiResponse(BaseModel):
    data: dict[str, Any]
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


class TestbedDumpOverviewApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class TestbedDumpImportApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class RuntimeIntegrityApiResponse(BaseModel):
    data: FileIntegrityInspectResult
    source: Literal["backend"] = "backend"
    mocked: bool = False


class RuntimeMetadataFailuresInspectApiResponse(BaseModel):
    data: MetadataFailureInspectResult
    source: Literal["backend"] = "backend"
    mocked: bool = False


class RuntimeMetadataFailuresRepairApiResponse(BaseModel):
    data: MetadataFailureRepairResult
    source: Literal["backend"] = "backend"
    mocked: bool = False


class RuntimeRepairReadinessApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class CatalogScanApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class CatalogStatusApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class CatalogZeroByteApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class CatalogScanJobApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class CatalogConsistencyJobApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class MissingAssetScanApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class MissingAssetPreviewApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class MissingAssetApplyApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class MissingAssetRestorePointsApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class MissingAssetRestoreApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class MissingAssetRestorePointDeleteApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class CatalogRemediationScanApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class CatalogRemediationPreviewApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class CatalogRemediationApplyApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class CatalogRemediationStateApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class RepairRunsApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class RepairRunDetailApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class QuarantineSummaryApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class BackupSnapshotsApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class BackupExecutionApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class BackupSizeEstimateApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class BackupTargetsApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class BackupTargetValidationApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class BackupExecutionStatusApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class BackupAssetWorkflowApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class BackupTestCopyApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class BackupRestoreActionApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class UndoPlanApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class UndoExecutionApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False


class RestoreSimulationApiResponse(BaseModel):
    data: dict[str, Any]
    source: Literal["backend"] = "backend"
    mocked: bool = False
