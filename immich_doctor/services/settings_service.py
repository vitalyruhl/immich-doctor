from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from immich_doctor.core.config import AppSettings

SETTINGS_SCHEMA_VERSION = "v1"


class SettingsCapabilityState(StrEnum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


class SettingsCapability(BaseModel):
    id: str
    title: str
    state: SettingsCapabilityState
    summary: str
    details: str
    blocking: bool = False


class SettingsFieldSchema(BaseModel):
    key: str
    label: str
    value_type: str = Field(alias="valueType")
    secret: bool = False
    editable: bool = False
    source: str


class SettingsFieldValue(SettingsFieldSchema):
    model_config = ConfigDict(populate_by_name=True)

    value: str
    present: bool


class SettingsSectionSchema(BaseModel):
    id: str
    title: str
    description: str
    fields: list[SettingsFieldSchema]


class SettingsSection(BaseModel):
    id: str
    title: str
    description: str
    state: SettingsCapabilityState
    summary: str
    fields: list[SettingsFieldValue]


class SettingsOverview(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    generated_at: str = Field(alias="generatedAt")
    schema_version: str = Field(alias="schemaVersion")
    capability_state: SettingsCapabilityState = Field(alias="capabilityState")
    summary: str
    capabilities: list[SettingsCapability]
    sections: list[SettingsSection]


class SettingsSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: str = Field(alias="schemaVersion")
    sections: list[SettingsSectionSchema]


class SettingsUpdatePayload(BaseModel):
    sections: dict[str, dict[str, str | None]] = Field(default_factory=dict)


class SettingsUpdateResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    capability_state: SettingsCapabilityState = Field(alias="capabilityState")
    applied: bool
    summary: str
    details: str
    accepted_sections: list[str] = Field(alias="acceptedSections")


@dataclass(slots=True)
class SettingsService:
    def get_overview(self, settings: AppSettings) -> SettingsOverview:
        generated_at = datetime.now(UTC).isoformat()
        schema_sections = self.get_schema().sections
        sections = [
            self._build_section(schema_section, settings) for schema_section in schema_sections
        ]
        capabilities = [
            SettingsCapability(
                id="read_settings",
                title="Read settings",
                state=SettingsCapabilityState.READY,
                summary="The backend can expose a read-only settings overview.",
                details="GET /api/settings returns a structured configuration tree.",
            ),
            SettingsCapability(
                id="settings_schema",
                title="Read settings schema",
                state=SettingsCapabilityState.READY,
                summary="The backend exposes a versioned settings schema.",
                details="GET /api/settings/schema returns the canonical field layout.",
            ),
            SettingsCapability(
                id="update_settings",
                title="Update settings",
                state=SettingsCapabilityState.NOT_IMPLEMENTED,
                summary="Settings mutation is intentionally not implemented yet.",
                details=(
                    "PUT /api/settings is reserved, but no persistence or write flow exists in "
                    "this phase."
                ),
                blocking=True,
            ),
        ]
        return SettingsOverview(
            generatedAt=generated_at,
            schemaVersion=SETTINGS_SCHEMA_VERSION,
            capabilityState=self._derive_capability_state(capabilities),
            summary=(
                "Settings inspection is available, but mutation remains intentionally disabled "
                "until a safe persistence workflow exists."
            ),
            capabilities=capabilities,
            sections=sections,
        )

    def get_schema(self) -> SettingsSchema:
        return SettingsSchema(
            schemaVersion=SETTINGS_SCHEMA_VERSION,
            sections=[
                SettingsSectionSchema(
                    id="immich",
                    title="Immich",
                    description="Immich path configuration and future API connectivity settings.",
                    fields=[
                        self._schema_field("immich_library_root", "Library root", "path"),
                        self._schema_field("immich_uploads_path", "Uploads path", "path"),
                        self._schema_field("immich_thumbs_path", "Thumbs path", "path"),
                        self._schema_field("immich_profile_path", "Profile path", "path"),
                        self._schema_field("immich_video_path", "Encoded video path", "path"),
                    ],
                ),
                SettingsSectionSchema(
                    id="database",
                    title="Database",
                    description="PostgreSQL connectivity settings used by server-side checks.",
                    fields=[
                        self._schema_field("db_host", "DB host", "string"),
                        self._schema_field("db_port", "DB port", "integer"),
                        self._schema_field("db_name", "DB name", "string"),
                        self._schema_field("db_user", "DB user", "string"),
                        self._schema_field("db_password", "DB password", "secret", secret=True),
                        self._schema_field("postgres_dsn", "PostgreSQL DSN", "secret", secret=True),
                        self._schema_field(
                            "postgres_connect_timeout_seconds",
                            "Connect timeout",
                            "integer",
                        ),
                    ],
                ),
                SettingsSectionSchema(
                    id="storage",
                    title="Storage",
                    description="Runtime paths for reports, manifests, quarantine, logs, and tmp.",
                    fields=[
                        self._schema_field("reports_path", "Reports path", "path"),
                        self._schema_field("manifests_path", "Manifests path", "path"),
                        self._schema_field("quarantine_path", "Quarantine path", "path"),
                        self._schema_field("logs_path", "Logs path", "path"),
                        self._schema_field("tmp_path", "Tmp path", "path"),
                        self._schema_field("config_path", "Config path", "path"),
                    ],
                ),
                SettingsSectionSchema(
                    id="backup",
                    title="Backup",
                    description="Backup target and external tool expectations.",
                    fields=[
                        self._schema_field("backup_target_path", "Backup target path", "path"),
                        self._schema_field(
                            "required_external_tools",
                            "Required external tools",
                            "list",
                        ),
                        self._schema_field(
                            "optional_external_tools",
                            "Optional external tools",
                            "list",
                        ),
                    ],
                ),
                SettingsSectionSchema(
                    id="scheduler-runtime",
                    title="Scheduler / Runtime",
                    description="Runtime environment metadata and future scheduler settings.",
                    fields=[
                        self._schema_field("environment", "Environment", "string"),
                    ],
                ),
            ],
        )

    def update_settings(self, payload: SettingsUpdatePayload) -> SettingsUpdateResult:
        return SettingsUpdateResult(
            capabilityState=SettingsCapabilityState.NOT_IMPLEMENTED,
            applied=False,
            summary="Settings mutation is not implemented in this phase.",
            details=(
                "The request was accepted for capability reporting only. No settings were "
                "persisted or mutated."
            ),
            acceptedSections=sorted(payload.sections.keys()),
        )

    def _build_section(
        self,
        schema_section: SettingsSectionSchema,
        settings: AppSettings,
    ) -> SettingsSection:
        fields = [
            self._build_field(field_schema, settings) for field_schema in schema_section.fields
        ]
        state, summary = self._summarize_section(schema_section.id, fields)
        return SettingsSection(
            id=schema_section.id,
            title=schema_section.title,
            description=schema_section.description,
            state=state,
            summary=summary,
            fields=fields,
        )

    def _build_field(
        self,
        field_schema: SettingsFieldSchema,
        settings: AppSettings,
    ) -> SettingsFieldValue:
        raw_value = getattr(settings, field_schema.key)
        if field_schema.secret:
            present = raw_value is not None
            value = "Configured" if present else "Not configured"
        else:
            present = raw_value is not None and raw_value != []
            value = self._stringify_value(raw_value)

        return SettingsFieldValue(
            key=field_schema.key,
            label=field_schema.label,
            valueType=field_schema.value_type,
            secret=field_schema.secret,
            editable=field_schema.editable,
            source=field_schema.source,
            value=value,
            present=present,
        )

    def _summarize_section(
        self,
        section_id: str,
        fields: list[SettingsFieldValue],
    ) -> tuple[SettingsCapabilityState, str]:
        present_count = sum(1 for field in fields if field.present)

        if section_id == "scheduler-runtime":
            return (
                SettingsCapabilityState.PARTIAL,
                (
                    "Runtime inspection is available, but scheduler-specific settings "
                    "are not implemented."
                ),
            )

        if section_id == "immich":
            if present_count == 0:
                return (
                    SettingsCapabilityState.PARTIAL,
                    (
                        "Immich path settings are not configured yet, and API "
                        "connectivity settings do not exist yet."
                    ),
                )
            return (
                SettingsCapabilityState.PARTIAL,
                (
                    "Immich path settings are visible, but dedicated Immich API "
                    "configuration is not implemented yet."
                ),
            )

        if present_count == 0:
            return (
                SettingsCapabilityState.PARTIAL,
                "No values are configured for this section yet.",
            )

        if present_count < len(fields):
            return (
                SettingsCapabilityState.PARTIAL,
                "This section is only partially configured.",
            )

        return (
            SettingsCapabilityState.READY,
            "This section is fully populated for the current backend contract.",
        )

    def _derive_capability_state(
        self,
        capabilities: list[SettingsCapability],
    ) -> SettingsCapabilityState:
        states = {capability.state for capability in capabilities}
        if SettingsCapabilityState.NOT_IMPLEMENTED in states:
            return SettingsCapabilityState.PARTIAL
        if SettingsCapabilityState.PARTIAL in states:
            return SettingsCapabilityState.PARTIAL
        return SettingsCapabilityState.READY

    def _schema_field(
        self,
        key: str,
        label: str,
        value_type: str,
        *,
        secret: bool = False,
    ) -> SettingsFieldSchema:
        return SettingsFieldSchema(
            key=key,
            label=label,
            valueType=value_type,
            secret=secret,
            editable=False,
            source="env",
        )

    def _stringify_value(self, value: object) -> str:
        if value is None:
            return "Not configured"
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, list):
            return ", ".join(str(item) for item in value) if value else "Not configured"
        return str(value)
