from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from immich_doctor.cli._common import emit_report
from immich_doctor.core.config import load_settings
from immich_doctor.db.corruption import DbCorruptionRepairService, DbCorruptionScanService
from immich_doctor.db.health.service import DbHealthCheckService
from immich_doctor.db.performance.indexes.service import DbPerformanceIndexesCheckService

db_app = typer.Typer(help="Database-specific checks and diagnostics.")
db_health_app = typer.Typer(help="Database reachability and readiness checks.")
db_corruption_app = typer.Typer(help="Targeted corruption detection and guarded repair planning.")
db_performance_app = typer.Typer(help="Database performance checks.")
db_performance_indexes_app = typer.Typer(help="Database index checks.")

db_app.add_typer(db_health_app, name="health")
db_app.add_typer(db_corruption_app, name="corruption")
db_app.add_typer(db_performance_app, name="performance")
db_performance_app.add_typer(db_performance_indexes_app, name="indexes")


@db_health_app.command("check")
def db_health_check(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show full diagnostic details in text output."),
    ] = False,
) -> None:
    settings = load_settings(env_file=env_file)
    report = DbHealthCheckService().run(settings)
    emit_report(report, output, verbose=verbose)


@db_performance_indexes_app.command("check")
def db_performance_indexes_check(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show full diagnostic details in text output."),
    ] = False,
) -> None:
    settings = load_settings(env_file=env_file)
    report = DbPerformanceIndexesCheckService().run(settings)
    emit_report(report, output, verbose=verbose)


@db_corruption_app.command("scan")
def db_corruption_scan(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show full diagnostic details in text output."),
    ] = False,
) -> None:
    settings = load_settings(env_file=env_file)
    report = DbCorruptionScanService().run(settings)
    emit_report(report, output, verbose=verbose)


@db_corruption_app.command("repair")
def db_corruption_repair(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    repair_run_id: Annotated[
        str | None,
        typer.Option("--repair-run-id", help="Existing preview repair run id for apply."),
    ] = None,
    selected_delete_id: Annotated[
        list[str],
        typer.Option("--selected-delete-id", help="Asset ids selected for duplicate deletion."),
    ] = [],
    backup_confirmed: Annotated[
        bool,
        typer.Option("--backup-confirmed", help="Confirm that a recent backup exists."),
    ] = False,
    override_backup_requirement: Annotated[
        bool,
        typer.Option("--override-backup-requirement", help="Explicitly override the backup precondition."),
    ] = False,
    maintenance_mode_confirmed: Annotated[
        bool,
        typer.Option("--maintenance-mode-confirmed", help="Confirm the application is in maintenance mode."),
    ] = False,
    system_index_duplicate_error_text: Annotated[
        str | None,
        typer.Option("--system-index-duplicate-error-text", help="Captured duplicate-key evidence from a failed system index rebuild."),
    ] = None,
    high_risk_clear_pg_statistic_approval: Annotated[
        bool,
        typer.Option("--high-risk-clear-pg-statistic-approval", help="Separate explicit approval for the exceptional pg_statistic clear step."),
    ] = False,
    force_reindex_database: Annotated[
        bool,
        typer.Option("--force-reindex-database", help="Force the conditional REINDEX DATABASE step into the plan."),
    ] = False,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Execute a previously previewed repair run."),
    ] = False,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show full diagnostic details in text output."),
    ] = False,
) -> None:
    settings = load_settings(env_file=env_file)
    service = DbCorruptionRepairService()
    if apply:
        if repair_run_id is None:
            raise typer.BadParameter("--repair-run-id is required with --apply.")
        report = service.apply(settings, repair_run_id=repair_run_id)
    else:
        report = service.preview(
            settings,
            selected_delete_ids=tuple(selected_delete_id),
            backup_confirmed=backup_confirmed,
            override_backup_requirement=override_backup_requirement,
            maintenance_mode_confirmed=maintenance_mode_confirmed,
            system_index_duplicate_error_text=system_index_duplicate_error_text,
            high_risk_clear_pg_statistic_approval=high_risk_clear_pg_statistic_approval,
            force_reindex_database=force_reindex_database,
        )
    emit_report(report, output, verbose=verbose)
