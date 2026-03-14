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
