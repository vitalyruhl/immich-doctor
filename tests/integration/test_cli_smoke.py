import json

from typer.testing import CliRunner

from immich_doctor.cli import db as db_cli
from immich_doctor.cli.main import app
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport, ValidationSection


def test_runtime_health_check_json_output() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["runtime", "health", "check", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["domain"] == "runtime.health"
    assert payload["action"] == "check"
    assert payload["status"] == "PASS"


def test_storage_paths_check_with_sample_directories(tmp_path, monkeypatch) -> None:
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

    reports = tmp_path / "reports"
    manifests = tmp_path / "manifests"
    quarantine = tmp_path / "quarantine"
    logs = tmp_path / "logs"
    tmp_dir = tmp_path / "tmp"

    for path in [reports, manifests, quarantine, logs, tmp_dir]:
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("REPORTS_PATH", str(reports))
    monkeypatch.setenv("MANIFESTS_PATH", str(manifests))
    monkeypatch.setenv("QUARANTINE_PATH", str(quarantine))
    monkeypatch.setenv("LOG_PATH", str(logs))
    monkeypatch.setenv("TMP_PATH", str(tmp_dir))

    result = runner.invoke(app, ["storage", "paths", "check", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["domain"] == "storage.paths"
    assert payload["action"] == "check"
    assert payload["status"] == "PASS"


def test_runtime_validate_with_safe_paths(tmp_path, monkeypatch) -> None:
    runner = CliRunner()

    library_root = tmp_path / "library"
    uploads = library_root / "upload"
    thumbs = library_root / "thumbs"
    profile = library_root / "profile"
    video = library_root / "encoded-video"
    config_dir = tmp_path / "config"

    for path in [
        library_root,
        uploads,
        thumbs,
        profile,
        video,
        config_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("IMMICH_STORAGE_PATH", str(library_root))
    monkeypatch.setenv("IMMICH_UPLOADS_PATH", str(uploads))
    monkeypatch.setenv("IMMICH_THUMBS_PATH", str(thumbs))
    monkeypatch.setenv("IMMICH_PROFILE_PATH", str(profile))
    monkeypatch.setenv("IMMICH_VIDEO_PATH", str(video))
    result = runner.invoke(app, ["runtime", "validate", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["domain"] == "runtime"
    assert payload["action"] == "validate"
    assert payload["status"] == "PASS"


def test_backup_verify_json_output(tmp_path, monkeypatch) -> None:
    runner = CliRunner()

    backup = tmp_path / "backup"
    backup.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("BACKUP_TARGET_PATH", str(backup))

    result = runner.invoke(app, ["backup", "verify", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["domain"] == "backup"
    assert payload["action"] == "verify"


def test_db_validate_indexes_json_output(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setenv("DB_HOST", "postgres")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "immich")
    monkeypatch.setenv("DB_USER", "immich")
    monkeypatch.setenv("DB_PASSWORD", "secret")

    def fake_run(self, settings):
        return ValidationReport(
            domain="db.performance.indexes",
            action="check",
            summary="Database index checks completed.",
            checks=[],
            sections=[
                ValidationSection(
                    name="INDEX_LIST",
                    status=CheckStatus.PASS,
                    rows=[
                        {
                            "schemaname": "public",
                            "tablename": "assets",
                            "indexname": "assets_pkey",
                            "indexdef": (
                                "CREATE UNIQUE INDEX assets_pkey ON public.assets USING btree (id)"
                            ),
                        }
                    ],
                ),
                ValidationSection(name="INVALID_INDEXES", status=CheckStatus.PASS),
                ValidationSection(name="UNUSED_INDEXES", status=CheckStatus.PASS),
                ValidationSection(name="LARGE_INDEXES", status=CheckStatus.PASS),
                ValidationSection(name="MISSING_FK_INDEXES", status=CheckStatus.PASS),
            ],
        )

    monkeypatch.setattr(db_cli.DbPerformanceIndexesCheckService, "run", fake_run)

    result = runner.invoke(app, ["db", "performance", "indexes", "check", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["domain"] == "db.performance.indexes"
    assert payload["sections"][0]["name"] == "INDEX_LIST"


def test_db_health_check_json_output(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setenv("DB_HOST", "postgres")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "immich")
    monkeypatch.setenv("DB_USER", "immich")
    monkeypatch.setenv("DB_PASSWORD", "secret")

    def fake_run(self, settings):
        return ValidationReport(
            domain="db.health",
            action="check",
            summary="Database health checks completed.",
            checks=[
                CheckResult(
                    name="postgres_connection",
                    status=CheckStatus.PASS,
                    message="PostgreSQL connection established.",
                )
            ],
        )

    monkeypatch.setattr(db_cli.DbHealthCheckService, "run", fake_run)

    result = runner.invoke(app, ["db", "health", "check", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["domain"] == "db.health"
    assert payload["action"] == "check"
