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


def test_runtime_validate_with_safe_paths(tmp_path, monkeypatch) -> None:
    runner = CliRunner()

    library_root = tmp_path / "library"
    uploads = library_root / "upload"
    thumbs = library_root / "thumbs"
    profile = library_root / "profile"
    video = library_root / "encoded-video"
    backup = tmp_path / "backup"
    reports = tmp_path / "reports"
    manifests = tmp_path / "manifests"
    quarantine = tmp_path / "quarantine"
    logs = tmp_path / "logs"
    tmp_dir = tmp_path / "tmp"
    config_dir = tmp_path / "config"

    for path in [
        library_root,
        uploads,
        thumbs,
        profile,
        video,
        backup,
        reports,
        manifests,
        quarantine,
        logs,
        tmp_dir,
        config_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("IMMICH_STORAGE_PATH", str(library_root))
    monkeypatch.setenv("IMMICH_UPLOADS_PATH", str(uploads))
    monkeypatch.setenv("IMMICH_THUMBS_PATH", str(thumbs))
    monkeypatch.setenv("IMMICH_PROFILE_PATH", str(profile))
    monkeypatch.setenv("IMMICH_VIDEO_PATH", str(video))
    monkeypatch.setenv("BACKUP_TARGET_PATH", str(backup))
    monkeypatch.setenv("REPORTS_PATH", str(reports))
    monkeypatch.setenv("MANIFESTS_PATH", str(manifests))
    monkeypatch.setenv("QUARANTINE_PATH", str(quarantine))
    monkeypatch.setenv("LOG_PATH", str(logs))
    monkeypatch.setenv("TMP_PATH", str(tmp_dir))
    monkeypatch.setenv("CONFIG_PATH", str(config_dir))

    result = runner.invoke(app, ["runtime", "validate", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "runtime validate"
    assert payload["overall_status"] == "warn"
