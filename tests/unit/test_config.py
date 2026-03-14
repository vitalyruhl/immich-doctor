from pathlib import Path

from immich_doctor.core.config import AppSettings


def test_external_tools_csv_parsing() -> None:
    settings = AppSettings(
        _env_file=None,
        required_external_tools="restic, pg_dump",
        optional_external_tools="psql",
    )

    assert settings.required_external_tools == ["restic", "pg_dump"]
    assert settings.optional_external_tools == ["psql"]


def test_path_settings_accept_path_objects(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        immich_library_root=tmp_path,
        backup_target_path=tmp_path / "backup",
    )

    assert settings.immich_library_root == tmp_path
    assert settings.backup_target_path == tmp_path / "backup"


def test_short_aliases_build_postgres_dsn() -> None:
    settings = AppSettings(
        _env_file=None,
        IMMICH_STORAGE_PATH="/mnt/immich/storage",
        BACKUP_TARGET_PATH="/mnt/backups/immich",
        DB_HOST="postgres",
        DB_PORT="5432",
        DB_NAME="immich",
        DB_USER="immich",
        DB_PASSWORD="secret",
    )

    assert settings.immich_library_root == Path("/mnt/immich/storage")
    assert settings.backup_target_path == Path("/mnt/backups/immich")
    assert settings.postgres_dsn_value() == "postgresql://immich:secret@postgres:5432/immich"
