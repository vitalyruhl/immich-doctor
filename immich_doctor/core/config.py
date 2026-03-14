from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IMMICH_DOCTOR_",
        env_file=".env",
        extra="ignore",
    )

    environment: str = "development"

    immich_library_root: Path | None = None
    immich_uploads_path: Path | None = None
    immich_thumbs_path: Path | None = None
    immich_profile_path: Path | None = None
    immich_video_path: Path | None = None

    backup_target_path: Path | None = None

    reports_path: Path = Path("data/reports")
    manifests_path: Path = Path("data/manifests")
    quarantine_path: Path = Path("data/quarantine")
    logs_path: Path = Path("data/logs")
    tmp_path: Path = Path("data/tmp")

    postgres_dsn: SecretStr | None = None
    postgres_connect_timeout_seconds: int = 3

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

    def postgres_dsn_value(self) -> str | None:
        return self.postgres_dsn.get_secret_value() if self.postgres_dsn else None


def load_settings(env_file: Path | None = None) -> AppSettings:
    if env_file is None:
        return AppSettings()
    return AppSettings(_env_file=env_file)
