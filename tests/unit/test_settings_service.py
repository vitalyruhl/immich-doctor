from __future__ import annotations

from immich_doctor.core.config import AppSettings
from immich_doctor.services.settings_service import (
    SETTINGS_SCHEMA_VERSION,
    SettingsCapabilityState,
    SettingsService,
    SettingsUpdatePayload,
)


def test_settings_service_returns_safe_overview_without_secret_leakage() -> None:
    service = SettingsService()

    overview = service.get_overview(
        AppSettings(
            db_host="postgres",
            db_name="immich",
            db_user="immich",
            db_password="super-secret",
        )
    )

    database_section = next(section for section in overview.sections if section.id == "database")
    password_field = next(field for field in database_section.fields if field.key == "db_password")

    assert overview.schema_version == SETTINGS_SCHEMA_VERSION
    assert overview.capability_state == SettingsCapabilityState.PARTIAL
    assert password_field.value == "Configured"
    assert "super-secret" not in password_field.value
    assert password_field.secret is True


def test_settings_service_exposes_versioned_schema() -> None:
    schema = SettingsService().get_schema()

    assert schema.schema_version == SETTINGS_SCHEMA_VERSION
    assert {section.id for section in schema.sections} == {
        "immich",
        "database",
        "storage",
        "backup",
        "scheduler-runtime",
    }


def test_settings_service_update_reports_not_implemented() -> None:
    result = SettingsService().update_settings(
        SettingsUpdatePayload(sections={"storage": {"reports_path": "/data/reports"}})
    )

    assert result.capability_state == SettingsCapabilityState.NOT_IMPLEMENTED
    assert result.applied is False
    assert result.accepted_sections == ["storage"]
