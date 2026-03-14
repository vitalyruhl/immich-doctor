import json

from typer.testing import CliRunner

from immich_doctor.cli.main import app


def test_health_ping_json_output() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["health", "ping", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "health ping"
    assert payload["overall_status"] == "pass"


def test_config_validate_with_sample_directories(tmp_path, monkeypatch) -> None:
    runner = CliRunner()

    library_root = tmp_path / "library"
    uploads = library_root / "upload"
    thumbs = library_root / "thumbs"
    profile = library_root / "profile"
    video = library_root / "encoded-video"

    for path in [library_root, uploads, thumbs, profile, video]:
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("IMMICH_DOCTOR_IMMICH_LIBRARY_ROOT", str(library_root))
    monkeypatch.setenv("IMMICH_DOCTOR_IMMICH_UPLOADS_PATH", str(uploads))
    monkeypatch.setenv("IMMICH_DOCTOR_IMMICH_THUMBS_PATH", str(thumbs))
    monkeypatch.setenv("IMMICH_DOCTOR_IMMICH_PROFILE_PATH", str(profile))
    monkeypatch.setenv("IMMICH_DOCTOR_IMMICH_VIDEO_PATH", str(video))

    result = runner.invoke(app, ["config", "validate", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "config validate"
    assert payload["overall_status"] == "warn"
