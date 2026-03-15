import json

from typer.testing import CliRunner

from immich_doctor.cli import db as db_cli
from immich_doctor.cli import remote as remote_cli
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


def test_db_validate_indexes_default_text_output_is_compact(monkeypatch) -> None:
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
                            "tablename": "face_search",
                            "indexname": "face_index",
                            "indexdef": "CREATE INDEX face_index ON public.face_search USING hnsw",
                        }
                    ],
                ),
                ValidationSection(
                    name="UNUSED_INDEXES",
                    status=CheckStatus.WARN,
                    rows=[
                        {"table_name": "a", "index_name": "a_idx", "idx_scan": 0},
                        {"table_name": "b", "index_name": "b_idx", "idx_scan": 0},
                        {"table_name": "c", "index_name": "c_idx", "idx_scan": 0},
                        {"table_name": "d", "index_name": "d_idx", "idx_scan": 0},
                    ],
                ),
                ValidationSection(
                    name="LARGE_INDEXES",
                    status=CheckStatus.PASS,
                    rows=[
                        {
                            "table_name": "face_search",
                            "index_name": "face_index",
                            "index_size": "0 bytes",
                        },
                        {
                            "table_name": "assets",
                            "index_name": "assets_pkey",
                            "index_size": "16 kB",
                        },
                    ],
                ),
                ValidationSection(name="INVALID_INDEXES", status=CheckStatus.PASS),
                ValidationSection(name="MISSING_FK_INDEXES", status=CheckStatus.PASS),
            ],
        )

    monkeypatch.setattr(db_cli.DbPerformanceIndexesCheckService, "run", fake_run)

    result = runner.invoke(app, ["db", "performance", "indexes", "check"])

    assert result.exit_code == 0
    assert "CREATE INDEX face_index" not in result.stdout
    assert "0 bytes" not in result.stdout
    assert "index_name=d_idx" not in result.stdout
    assert "Hint: Use --verbose for full diagnostic details." in result.stdout


def test_db_validate_indexes_verbose_text_output_shows_full_details(monkeypatch) -> None:
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
                            "tablename": "face_search",
                            "indexname": "face_index",
                            "indexdef": "CREATE INDEX face_index ON public.face_search USING hnsw",
                        }
                    ],
                ),
                ValidationSection(
                    name="UNUSED_INDEXES",
                    status=CheckStatus.WARN,
                    rows=[
                        {"table_name": "a", "index_name": "a_idx", "idx_scan": 0},
                        {"table_name": "b", "index_name": "b_idx", "idx_scan": 0},
                        {"table_name": "c", "index_name": "c_idx", "idx_scan": 0},
                        {"table_name": "d", "index_name": "d_idx", "idx_scan": 0},
                    ],
                ),
                ValidationSection(
                    name="LARGE_INDEXES",
                    status=CheckStatus.PASS,
                    rows=[
                        {
                            "table_name": "face_search",
                            "index_name": "face_index",
                            "index_size": "0 bytes",
                        },
                    ],
                ),
            ],
        )

    monkeypatch.setattr(db_cli.DbPerformanceIndexesCheckService, "run", fake_run)

    result = runner.invoke(app, ["db", "performance", "indexes", "check", "--verbose"])

    assert result.exit_code == 0
    assert "CREATE INDEX face_index" in result.stdout
    assert "0 bytes" in result.stdout
    assert "index_name': 'd_idx'" in result.stdout


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


def test_remote_sync_validate_json_output(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setenv("DB_HOST", "postgres")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "immich")
    monkeypatch.setenv("DB_USER", "immich")
    monkeypatch.setenv("DB_PASSWORD", "secret")

    def fake_run(self, settings):
        return ValidationReport(
            domain="remote.sync",
            action="validate",
            summary="Remote sync validation completed with no foreign key inconsistencies.",
            checks=[
                CheckResult(
                    name="postgres_connection",
                    status=CheckStatus.PASS,
                    message="PostgreSQL connection established.",
                ),
                CheckResult(
                    name="remote_album_asset_missing_assets",
                    status=CheckStatus.PASS,
                    message="No missing asset references found.",
                    details={
                        "severity": "info",
                        "count": 0,
                        "samples": [],
                        "impacted_tables": [
                            "public.remote_album_asset_entity",
                            "public.asset_entity",
                        ],
                    },
                ),
            ],
        )

    monkeypatch.setattr(remote_cli.RemoteSyncValidationService, "run", fake_run)

    result = runner.invoke(app, ["remote", "sync", "validate", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["domain"] == "remote.sync"
    assert payload["action"] == "validate"
    assert payload["status"] == "PASS"
