from immich_doctor.core.config import AppSettings
from immich_doctor.core.paths import configured_immich_paths, runtime_paths


def test_configured_immich_paths_include_only_values(tmp_path) -> None:
    settings = AppSettings(
        _env_file=None,
        immich_library_root=tmp_path,
        immich_uploads_path=tmp_path / "upload",
    )

    path_map = configured_immich_paths(settings)

    assert set(path_map) == {"immich_library_root", "immich_uploads_path"}


def test_runtime_paths_are_available() -> None:
    settings = AppSettings(_env_file=None)

    paths = runtime_paths(settings)

    assert "reports_path" in paths
    assert "tmp_path" in paths
