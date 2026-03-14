from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from immich_doctor.cli._common import emit_report
from immich_doctor.core.config import load_settings
from immich_doctor.runtime.health.service import RuntimeHealthCheckService
from immich_doctor.runtime.validate.service import RuntimeValidationService

runtime_app = typer.Typer(help="Execution environment validation commands.")
runtime_health_app = typer.Typer(help="Runtime reachability and readiness checks.")

runtime_app.add_typer(runtime_health_app, name="health")


@runtime_app.command("validate")
def runtime_validate(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
) -> None:
    settings = load_settings(env_file=env_file)
    report = RuntimeValidationService().run(settings)
    emit_report(report, output)


@runtime_health_app.command("check")
def runtime_health_check(
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
) -> None:
    report = RuntimeHealthCheckService().run()
    emit_report(report, output)
