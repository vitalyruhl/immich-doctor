from __future__ import annotations

from typing import Annotated

import typer

from immich_doctor.cli._common import emit_report
from immich_doctor.services.health_service import HealthService

health_app = typer.Typer(help="Health-oriented safe checks.")


@health_app.command("ping")
def health_ping(
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
) -> None:
    report = HealthService().run_ping()
    emit_report(report, output)

