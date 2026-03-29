from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from psycopg.conninfo import conninfo_to_dict
from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IMMICH_DOCTOR_",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    environment: str = "development"

    immich_library_root: Path | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_IMMICH_LIBRARY_ROOT",
            "IMMICH_STORAGE_PATH",
        ),
    )
    immich_uploads_path: Path | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_IMMICH_UPLOADS_PATH",
            "IMMICH_UPLOADS_PATH",
        ),
    )
    immich_thumbs_path: Path | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_IMMICH_THUMBS_PATH",
            "IMMICH_THUMBS_PATH",
        ),
    )
    immich_profile_path: Path | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_IMMICH_PROFILE_PATH",
            "IMMICH_PROFILE_PATH",
        ),
    )
    immich_video_path: Path | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_IMMICH_VIDEO_PATH",
            "IMMICH_VIDEO_PATH",
        ),
    )

    backup_target_path: Path | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_BACKUP_TARGET_PATH",
            "BACKUP_TARGET_PATH",
        ),
    )

    reports_path: Path = Field(
        default=Path("data/reports"),
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_REPORTS_PATH",
            "REPORTS_PATH",
        ),
    )
    manifests_path: Path = Field(
        default=Path("data/manifests"),
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_MANIFESTS_PATH",
            "MANIFESTS_PATH",
        ),
    )
    quarantine_path: Path = Field(
        default=Path("data/quarantine"),
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_QUARANTINE_PATH",
            "QUARANTINE_PATH",
        ),
    )
    logs_path: Path = Field(
        default=Path("data/logs"),
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_LOGS_PATH",
            "LOG_PATH",
            "LOGS_PATH",
        ),
    )
    tmp_path: Path = Field(
        default=Path("data/tmp"),
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_TMP_PATH",
            "TMP_PATH",
        ),
    )
    config_path: Path | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_CONFIG_PATH",
            "CONFIG_PATH",
        ),
    )

    postgres_dsn: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_POSTGRES_DSN",
            "POSTGRES_DSN",
            "DATABASE_URL",
        ),
    )
    db_host: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_DB_HOST",
            "DB_HOST",
        ),
    )
    db_port: int = Field(
        default=5432,
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_DB_PORT",
            "DB_PORT",
        ),
    )
    db_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_DB_NAME",
            "DB_NAME",
        ),
    )
    db_user: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_DB_USER",
            "DB_USER",
        ),
    )
    db_password: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_DB_PASSWORD",
            "DB_PASSWORD",
        ),
    )
    postgres_connect_timeout_seconds: int = Field(
        default=3,
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_POSTGRES_CONNECT_TIMEOUT_SECONDS",
            "DB_CONNECT_TIMEOUT_SECONDS",
        ),
    )
    missing_asset_scan_concurrency: int = Field(
        default=20,
        validation_alias=AliasChoices(
            "IMMICH_DOCTOR_MISSING_ASSET_SCAN_CONCURRENCY",
            "MISSING_ASSET_SCAN_CONCURRENCY",
        ),
    )

    required_external_tools: list[str] = Field(default_factory=list)
    optional_external_tools: list[str] = Field(default_factory=list)

    @field_validator("required_external_tools", "optional_external_tools", mode="before")
    @classmethod
    def split_csv_tools(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise TypeError("External tool configuration must be a list or comma-separated string.")

    @field_validator("missing_asset_scan_concurrency", mode="before")
    @classmethod
    def normalize_missing_asset_scan_concurrency(cls, value: object) -> int:
        if value is None or value == "":
            return 20
        return max(1, int(value))

    @field_validator(
        "immich_library_root",
        "immich_uploads_path",
        "immich_thumbs_path",
        "immich_profile_path",
        "immich_video_path",
        "backup_target_path",
        "config_path",
        "postgres_dsn",
        "db_host",
        "db_name",
        "db_user",
        "db_password",
        mode="before",
    )
    @classmethod
    def empty_values_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def postgres_dsn_value(self) -> str | None:
        if self.postgres_dsn:
            return self.postgres_dsn.get_secret_value()

        if not all([self.db_host, self.db_name, self.db_user, self.db_password]):
            return None

        encoded_user = quote(self.db_user)
        encoded_password = quote(self.db_password.get_secret_value())
        encoded_name = quote(self.db_name)
        return (
            f"postgresql://{encoded_user}:{encoded_password}"
            f"@{self.db_host}:{self.db_port}/{encoded_name}"
        )

    def postgres_target(self) -> tuple[str | None, int | None]:
        if self.db_host:
            return self.db_host, self.db_port

        dsn = self.postgres_dsn_value()
        if not dsn:
            return None, None

        parsed = conninfo_to_dict(dsn)
        host = parsed.get("host")
        port = parsed.get("port")
        return host, int(port) if port else 5432


def load_settings(env_file: Path | None = None) -> AppSettings:
    if env_file is None:
        return AppSettings()
    return AppSettings(_env_file=env_file)
