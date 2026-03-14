from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from immich_doctor.backup.orchestration import BackupFilesService
from immich_doctor.backup.verify.service import BackupVerifyService
from immich_doctor.cli._common import emit_backup_result, emit_report
from immich_doctor.core.config import load_settings

backup_app = typer.Typer(help="Backup commands.")


@backup_app.command("verify")
def backup_verify(
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
    report = BackupVerifyService().run(settings)
    emit_report(report, output, verbose=verbose)


@backup_app.command("files")
def backup_files(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
) -> None:
    settings = load_settings(env_file=env_file)
    result = BackupFilesService().run(settings)
    emit_backup_result(result, output)
