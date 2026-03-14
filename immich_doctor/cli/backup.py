from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from immich_doctor.cli._common import emit_report
from immich_doctor.core.config import load_settings
from immich_doctor.services.backup_validation_service import BackupValidationService

backup_app = typer.Typer(help="Backup validation commands.")


@backup_app.command("validate")
def backup_validate(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
) -> None:
    settings = load_settings(env_file=env_file)
    report = BackupValidationService().run(settings)
    emit_report(report, output)
