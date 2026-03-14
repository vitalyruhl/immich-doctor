from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from immich_doctor.cli._common import emit_report
from immich_doctor.core.config import load_settings
from immich_doctor.db.health.service import DbHealthCheckService
from immich_doctor.db.performance.indexes.service import DbPerformanceIndexesCheckService

db_app = typer.Typer(help="Database-specific checks and diagnostics.")
db_health_app = typer.Typer(help="Database reachability and readiness checks.")
db_performance_app = typer.Typer(help="Database performance checks.")
db_performance_indexes_app = typer.Typer(help="Database index checks.")

db_app.add_typer(db_health_app, name="health")
db_app.add_typer(db_performance_app, name="performance")
db_performance_app.add_typer(db_performance_indexes_app, name="indexes")


@db_health_app.command("check")
def db_health_check(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
) -> None:
    settings = load_settings(env_file=env_file)
    report = DbHealthCheckService().run(settings)
    emit_report(report, output)


@db_performance_indexes_app.command("check")
def db_performance_indexes_check(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
) -> None:
    settings = load_settings(env_file=env_file)
    report = DbPerformanceIndexesCheckService().run(settings)
    emit_report(report, output)
