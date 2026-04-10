import json
from datetime import UTC, datetime

from typer.testing import CliRunner

from immich_doctor.backup.core.models import BackupContext, BackupResult, BackupTarget
from immich_doctor.backup.restore import RestoreReadiness, RestoreSimulationResult
from immich_doctor.cli import analyze as analyze_cli
from immich_doctor.cli import backup as backup_cli
from immich_doctor.cli import consistency as consistency_cli
from immich_doctor.cli import db as db_cli
from immich_doctor.cli import remote as remote_cli
from immich_doctor.cli import repair as repair_cli
from immich_doctor.cli import runtime as runtime_cli
from immich_doctor.cli import testbed as testbed_cli
from immich_doctor.cli.main import app
from immich_doctor.consistency.models import (
    ConsistencyCategory,
    ConsistencyRepairAction,
    ConsistencyRepairMode,
    ConsistencyRepairPlan,
    ConsistencyRepairResult,
    ConsistencyRepairStatus,
    ConsistencySeverity,
    ConsistencySummary,
    ConsistencyValidationReport,
)
from immich_doctor.core.models import (
    CheckResult,
    CheckStatus,
    RepairItemStatus,
    RepairPlanItem,
    RepairReport,
    ValidationReport,
    ValidationSection,
)
from immich_doctor.repair import (
    UndoEligibility,
    UndoExecutionItem,
    UndoExecutionResult,
    UndoExecutionStatus,
    UndoPlanResult,
)
from immich_doctor.runtime.integrity.models import (
    FileIntegrityFinding,
    FileIntegrityInspectResult,
    FileIntegrityStatus,
    FileIntegritySummaryItem,
    FileRole,
    MediaKind,
)
from immich_doctor.runtime.metadata_failures.models import (
    ConfidenceLevel,
    MetadataFailureCause,
    MetadataFailureDiagnostic,
    MetadataFailureInspectResult,
    MetadataFailureLevel,
    MetadataFailureRepairResult,
    MetadataFailureSummaryItem,
    MetadataRepairAction,
    MetadataRepairStatus,
    SuggestedAction,
)
from immich_doctor.services.testbed_dump_service import TestbedDumpImportResult


def test_runtime_health_check_json_output() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["runtime", "health", "check", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["domain"] == "runtime.health"
    assert payload["action"] == "check"
    assert payload["status"] == "PASS"


def test_analyze_catalog_scan_job_status_json_output(monkeypatch) -> None:
    runner = CliRunner()

    def fake_call(*, api_base_url, method, endpoint, payload=None, timeout=8.0):
        del api_base_url, method, endpoint, payload, timeout
        return {
            "data": {
                "jobId": "catalog-scan-1",
                "jobType": "catalog_inventory_scan",
                "state": "running",
                "summary": "Catalog scan is running.",
                "result": {
                    "runtime": {
                        "scanState": "running",
                        "configuredWorkerCount": 6,
                        "activeWorkerCount": 3,
                        "workerResize": {
                            "supported": False,
                            "semantics": "next_run_only",
                        },
                    }
                },
            }
        }

    monkeypatch.setattr(analyze_cli, "_catalog_scan_job_api_call", fake_call)

    result = runner.invoke(
        app,
        ["analyze", "catalog", "scan-job", "status", "--output", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["state"] == "running"
    assert payload["result"]["runtime"]["configuredWorkerCount"] == 6
    assert payload["result"]["runtime"]["activeWorkerCount"] == 3


def test_testbed_import_dump_json_output(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setenv("IMMICH_DOCTOR_ENVIRONMENT", "dev-testbed")
    monkeypatch.setenv("TESTBED_DUMP_PATH", r"C:\Temp\immich.sql")
    monkeypatch.setenv("DB_HOST", "postgres")
    monkeypatch.setenv("DB_NAME", "immich")
    monkeypatch.setenv("DB_USER", "postgres")
    monkeypatch.setenv("DB_PASSWORD", "secret")

    def fake_import_dump(self, settings, *, requested_path=None, dump_format=None, force=False):
        del self, settings
        return TestbedDumpImportResult(
            state="completed",
            classification="success",
            summary="Testbed dump import completed successfully.",
            requestedPath=requested_path or r"C:\Temp\immich.sql",
            effectivePath="/mnt/testbed/dumps/immich.sql",
            dumpFormat=dump_format or "auto",
            generatedAt="2026-04-09T10:00:00+00:00",
            dbWasEmpty=False,
            expectedSkippedStatements=0,
            structuralErrorCount=0,
            meaningfulErrorCount=0,
            warnings=[],
        )

    monkeypatch.setattr(testbed_cli.TestbedDumpImportService, "import_dump", fake_import_dump)

    result = runner.invoke(app, ["testbed", "import-dump", "--force", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["classification"] == "success"
    assert payload["effectivePath"] == "/mnt/testbed/dumps/immich.sql"


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


def test_runtime_integrity_inspect_json_output(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setenv("DB_HOST", "postgres")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "immich")
    monkeypatch.setenv("DB_USER", "immich")
    monkeypatch.setenv("DB_PASSWORD", "secret")

    def fake_run(self, settings, *, limit, offset, include_derivatives):
        return FileIntegrityInspectResult(
            domain="runtime.integrity",
            action="inspect",
            summary="Runtime integrity inspection checked 1 files.",
            checks=[
                CheckResult(
                    name="postgres_connection",
                    status=CheckStatus.PASS,
                    message="PostgreSQL connection established.",
                )
            ],
            findings=[
                FileIntegrityFinding(
                    finding_id="file_integrity:asset-1:source:asset.jpg",
                    asset_id="asset-1",
                    file_role=FileRole.SOURCE,
                    media_kind=MediaKind.IMAGE,
                    path="/library/asset.jpg",
                    status=FileIntegrityStatus.FILE_OK,
                    message="File passed the current physical integrity checks.",
                )
            ],
            summary_items=[FileIntegritySummaryItem(status=FileIntegrityStatus.FILE_OK, count=1)],
        )

    monkeypatch.setattr(runtime_cli.RuntimeIntegrityInspectService, "run", fake_run)

    result = runner.invoke(app, ["runtime", "integrity", "inspect", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["domain"] == "runtime.integrity"
    assert payload["action"] == "inspect"
    assert payload["findings"][0]["status"] == "FILE_OK"


def test_runtime_metadata_failures_inspect_json_output(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setenv("DB_HOST", "postgres")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "immich")
    monkeypatch.setenv("DB_USER", "immich")
    monkeypatch.setenv("DB_PASSWORD", "secret")

    def fake_run(self, settings, *, limit, offset):
        return MetadataFailureInspectResult(
            domain="runtime.metadata_failures",
            action="inspect",
            summary="1 metadata failure detected.",
            checks=[
                CheckResult(
                    name="postgres_connection",
                    status=CheckStatus.PASS,
                    message="PostgreSQL connection established.",
                )
            ],
            integrity_summary=[
                {"status": FileIntegrityStatus.FILE_PERMISSION_DENIED.value, "count": 1}
            ],
            metadata_summary=[
                MetadataFailureSummaryItem(
                    root_cause=MetadataFailureCause.CAUSED_BY_PERMISSION_ERROR,
                    count=1,
                )
            ],
            diagnostics=[
                MetadataFailureDiagnostic(
                    diagnostic_id="metadata_failure:asset-1",
                    asset_id="asset-1",
                    job_name="metadata_extraction",
                    root_cause=MetadataFailureCause.CAUSED_BY_PERMISSION_ERROR,
                    failure_level=MetadataFailureLevel.SECONDARY,
                    suggested_action=SuggestedAction.FIX_PERMISSIONS,
                    confidence=ConfidenceLevel.HIGH,
                    source_path="/library/asset.jpg",
                    source_file_status=FileIntegrityStatus.FILE_PERMISSION_DENIED.value,
                    source_message="Permission denied.",
                    available_actions=(
                        SuggestedAction.FIX_PERMISSIONS,
                        SuggestedAction.REPORT_ONLY,
                    ),
                )
            ],
        )

    monkeypatch.setattr(runtime_cli.RuntimeMetadataFailuresInspectService, "run", fake_run)

    result = runner.invoke(
        app,
        ["runtime", "metadata-failures", "inspect", "--output", "json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["domain"] == "runtime.metadata_failures"
    assert payload["action"] == "inspect"
    assert payload["diagnostics"][0]["root_cause"] == "CAUSED_BY_PERMISSION_ERROR"


def test_runtime_metadata_failures_repair_json_output(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setenv("DB_HOST", "postgres")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "immich")
    monkeypatch.setenv("DB_USER", "immich")
    monkeypatch.setenv("DB_PASSWORD", "secret")

    def fake_run(
        self,
        settings,
        *,
        apply,
        limit,
        offset,
        diagnostic_ids,
        retry_jobs,
        requeue,
        fix_permissions,
        quarantine_corrupt,
        mark_unrecoverable,
    ):
        diagnostic = MetadataFailureDiagnostic(
            diagnostic_id="metadata_failure:asset-1",
            asset_id="asset-1",
            job_name="metadata_extraction",
            root_cause=MetadataFailureCause.CAUSED_BY_PERMISSION_ERROR,
            failure_level=MetadataFailureLevel.SECONDARY,
            suggested_action=SuggestedAction.FIX_PERMISSIONS,
            confidence=ConfidenceLevel.HIGH,
            source_path="/library/asset.jpg",
            source_file_status=FileIntegrityStatus.FILE_PERMISSION_DENIED.value,
            source_message="Permission denied.",
            available_actions=(SuggestedAction.FIX_PERMISSIONS,),
        )
        return MetadataFailureRepairResult(
            domain="runtime.metadata_failures",
            action="repair",
            summary=(
                "Metadata failure repair planned 1 actions and skipped 0 without mutating data."
            ),
            checks=[
                CheckResult(
                    name="postgres_connection",
                    status=CheckStatus.PASS,
                    message="PostgreSQL connection established.",
                )
            ],
            diagnostics=[diagnostic],
            repair_actions=[
                MetadataRepairAction(
                    action=SuggestedAction.FIX_PERMISSIONS,
                    diagnostic_id=diagnostic.diagnostic_id,
                    status=MetadataRepairStatus.PLANNED,
                    reason="Dry-run planned a permission fix.",
                    path=diagnostic.source_path,
                    supports_apply=True,
                    dry_run=True,
                    applied=False,
                )
            ],
        )

    monkeypatch.setattr(runtime_cli.RuntimeMetadataFailuresRepairService, "run", fake_run)

    result = runner.invoke(
        app,
        ["runtime", "metadata-failures", "repair", "--output", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["domain"] == "runtime.metadata_failures"
    assert payload["action"] == "repair"
    assert payload["repair_actions"][0]["status"] == "planned"


def test_backup_verify_json_output(tmp_path, monkeypatch) -> None:
    runner = CliRunner()

    backup = tmp_path / "backup"
    manifests = tmp_path / "manifests"
    quarantine = tmp_path / "quarantine"
    backup.mkdir(parents=True, exist_ok=True)
    manifests.mkdir(parents=True, exist_ok=True)
    quarantine.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("BACKUP_TARGET_PATH", str(backup))
    monkeypatch.setenv("MANIFESTS_PATH", str(manifests))
    monkeypatch.setenv("QUARANTINE_PATH", str(quarantine))

    result = runner.invoke(app, ["backup", "verify", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["domain"] == "backup"
    assert payload["action"] == "verify"


def test_backup_files_json_output(monkeypatch) -> None:
    runner = CliRunner()

    def fake_run(self, settings):
        return BackupResult(
            domain="backup.files",
            action="run",
            status="success",
            summary="File backup execution completed.",
            context=BackupContext(
                job_name="backup-files",
                requested_components=("files",),
                target=BackupTarget(
                    kind="local",
                    reference="/backups/immich",
                    display_name="immich",
                ),
                started_at=datetime(2026, 3, 14, 21, 30, tzinfo=UTC),
            ),
            details={"backup_root_path": "/backups/immich/20260314T213000Z"},
        )

    monkeypatch.setattr(backup_cli.BackupFilesService, "run", fake_run)

    result = runner.invoke(app, ["backup", "files", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["domain"] == "backup.files"
    assert payload["action"] == "run"
    assert payload["status"] == "SUCCESS"


def test_backup_restore_simulate_json_output(monkeypatch) -> None:
    runner = CliRunner()

    def fake_simulate(self, settings, *, snapshot_id, repair_run_id):
        return RestoreSimulationResult(
            domain="backup.restore",
            action="simulate",
            summary="Full restore simulation generated deterministic manual steps.",
            readiness=RestoreReadiness.SIMULATION_ONLY,
            checks=[],
            selected_snapshot={
                "snapshot_id": "snapshot-1",
                "coverage": "paired",
                "selection_source": "manual",
            },
            metadata={"instruction_profile": "docker-unraid"},
        )

    monkeypatch.setattr(
        backup_cli.BackupRestoreSimulationService,
        "simulate",
        fake_simulate,
    )

    result = runner.invoke(
        app,
        ["backup", "restore", "simulate", "--snapshot-id", "snapshot-1", "--output", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["domain"] == "backup.restore"
    assert payload["readiness"] == "simulation_only"


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
            summary=(
                "Remote sync validation found no server-side PostgreSQL album/asset link issues."
            ),
            checks=[
                CheckResult(
                    name="postgres_connection",
                    status=CheckStatus.PASS,
                    message="PostgreSQL connection established.",
                ),
                CheckResult(
                    name="remote_sync_scope_boundary",
                    status=CheckStatus.PASS,
                    message="The reported signature matches a likely client-side SQLite issue.",
                    details={
                        "severity": "info",
                    },
                ),
                CheckResult(
                    name="album_asset_missing_assets",
                    status=CheckStatus.PASS,
                    message="No missing asset references found in server PostgreSQL tables.",
                    details={
                        "severity": "info",
                        "count": 0,
                        "impacted_tables": [
                            "public.album_asset",
                            "public.asset",
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


def test_repair_undo_plan_json_output(monkeypatch) -> None:
    runner = CliRunner()

    def fake_plan(self, settings, *, repair_run_id, entry_ids):
        return UndoPlanResult(
            domain="repair.undo",
            action="plan",
            summary="Undo planning classified 1 journal entries as `reversible_now`.",
            repair_run_id=repair_run_id,
            target_repair_run_status="completed",
            eligibility=UndoEligibility.REVERSIBLE_NOW,
            apply_allowed=True,
            checks=[],
            metadata={"selected_entry_ids": ["entry-1"]},
        )

    monkeypatch.setattr(repair_cli.RepairUndoService, "plan", fake_plan)

    result = runner.invoke(
        app,
        ["repair", "undo", "plan", "--repair-run-id", "repair-run-1", "--output", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["domain"] == "repair.undo"
    assert payload["eligibility"] == "reversible_now"


def test_repair_undo_apply_json_output(monkeypatch) -> None:
    runner = CliRunner()

    def fake_execute(self, settings, *, repair_run_id, entry_ids, apply):
        return UndoExecutionResult(
            domain="repair.undo",
            action="apply",
            summary="Targeted undo restored 1 journal entries and failed 0.",
            repair_run_id="undo-run-1",
            target_repair_run_id=repair_run_id,
            eligibility=UndoEligibility.REVERSIBLE_NOW,
            checks=[],
            execution_items=[
                UndoExecutionItem(
                    entry_id="entry-1",
                    operation_type="fix_permissions",
                    status=UndoExecutionStatus.APPLIED,
                    message="Permission mode was restored from journal data.",
                    original_path="/library/asset.jpg",
                )
            ],
        )

    monkeypatch.setattr(repair_cli.RepairUndoService, "execute", fake_execute)

    result = runner.invoke(
        app,
        ["repair", "undo", "apply", "--repair-run-id", "repair-run-1", "--output", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["domain"] == "repair.undo"
    assert payload["execution_items"][0]["status"] == "applied"


def test_remote_sync_repair_json_output(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setenv("DB_HOST", "postgres")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "immich")
    monkeypatch.setenv("DB_USER", "immich")
    monkeypatch.setenv("DB_PASSWORD", "secret")

    def fake_run(self, settings, *, apply):
        return RepairReport(
            domain="remote.sync",
            action="repair",
            summary="Remote sync repair dry-run planned deletion of 1 orphan album_asset row.",
            checks=[
                CheckResult(
                    name="postgres_connection",
                    status=CheckStatus.PASS,
                    message="PostgreSQL connection established.",
                )
            ],
            plans=[
                RepairPlanItem(
                    action="delete",
                    target_table="public.album_asset",
                    reason="orphan album_asset rows with missing asset references",
                    key_columns=("assetsId", "albumId"),
                    row_count=1,
                    sample_rows=[{"albumId": "album-1", "assetsId": "asset-missing-1"}],
                    dry_run=True,
                    applied=False,
                    status=RepairItemStatus.PLANNED,
                    backup_sql="CREATE TABLE backup AS SELECT * FROM public.album_asset;",
                )
            ],
        )

    monkeypatch.setattr(remote_cli.RemoteSyncRepairService, "run", fake_run)

    result = runner.invoke(app, ["remote", "sync", "repair", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["domain"] == "remote.sync"
    assert payload["action"] == "repair"
    assert payload["plans"][0]["status"] == "planned"


def test_consistency_validate_json_output(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setenv("DB_HOST", "postgres")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "immich")
    monkeypatch.setenv("DB_USER", "immich")
    monkeypatch.setenv("DB_PASSWORD", "secret")

    def fake_run(self, settings):
        return ConsistencyValidationReport(
            domain="consistency",
            action="validate",
            summary="Consistency validation found no issues in the supported schema categories.",
            checks=[
                CheckResult(
                    name="postgres_connection",
                    status=CheckStatus.PASS,
                    message="PostgreSQL connection established.",
                )
            ],
            categories=[
                ConsistencyCategory(
                    name="db.orphan.album_asset.missing_asset",
                    severity=ConsistencySeverity.FAIL,
                    repair_mode=ConsistencyRepairMode.SAFE_DELETE,
                    status=CheckStatus.PASS,
                    count=0,
                    repairable=True,
                    message="No findings in category `db.orphan.album_asset.missing_asset`.",
                )
            ],
            findings=[],
            consistency_summary=ConsistencySummary(
                profile_name="immich_current_postgres_profile",
                profile_supported=True,
                executed_categories=("db.orphan.album_asset.missing_asset",),
            ),
        )

    monkeypatch.setattr(consistency_cli.ConsistencyValidationService, "run", fake_run)

    result = runner.invoke(app, ["consistency", "validate", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["domain"] == "consistency"
    assert payload["action"] == "validate"
    assert payload["categories"][0]["name"] == "db.orphan.album_asset.missing_asset"


def test_consistency_repair_json_output(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setenv("DB_HOST", "postgres")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "immich")
    monkeypatch.setenv("DB_USER", "immich")
    monkeypatch.setenv("DB_PASSWORD", "secret")

    def fake_run(self, settings, *, categories, finding_ids, all_safe, apply):
        return ConsistencyRepairResult(
            domain="consistency",
            action="repair",
            summary="Consistency repair dry-run planned changes for 1 selected repairable rows.",
            checks=[
                CheckResult(
                    name="postgres_connection",
                    status=CheckStatus.PASS,
                    message="PostgreSQL connection established.",
                )
            ],
            repair_plan=ConsistencyRepairPlan(
                selected_categories=categories,
                selected_ids=finding_ids,
                all_safe=all_safe,
                actions=(
                    ConsistencyRepairAction(
                        category="db.orphan.album_asset.missing_asset",
                        repair_mode=ConsistencyRepairMode.SAFE_DELETE,
                        status=ConsistencyRepairStatus.WOULD_REPAIR,
                        message=(
                            "Dry-run would repair category `db.orphan.album_asset.missing_asset`."
                        ),
                        target_table="public.album_asset",
                        finding_ids=("album_asset:missing_asset:album-1:asset-missing-1",),
                        row_count=1,
                        dry_run=True,
                        applied=False,
                    ),
                ),
            ),
            consistency_summary=ConsistencySummary(
                profile_name="immich_current_postgres_profile",
                profile_supported=True,
            ),
        )

    monkeypatch.setattr(consistency_cli.ConsistencyRepairService, "run", fake_run)

    result = runner.invoke(
        app,
        [
            "consistency",
            "repair",
            "--category",
            "db.orphan.album_asset.missing_asset",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["domain"] == "consistency"
    assert payload["action"] == "repair"
    assert payload["repair_plan"]["actions"][0]["status"] == "would_repair"
