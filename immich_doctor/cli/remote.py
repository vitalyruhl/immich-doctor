from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from immich_doctor.cli._common import emit_report
from immich_doctor.core.config import load_settings
from immich_doctor.remote.sync.repair_service import RemoteSyncRepairService
from immich_doctor.remote.sync.service import RemoteSyncValidationService

remote_app = typer.Typer(help="Remote-sync validation and diagnostics.")
remote_sync_app = typer.Typer(help="Remote sync checks.")

remote_app.add_typer(remote_sync_app, name="sync")


@remote_sync_app.command("validate")
def remote_sync_validate(
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
    report = RemoteSyncValidationService().run(settings)
    emit_report(report, output, verbose=verbose)


@remote_sync_app.command("repair")
def remote_sync_repair(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show full diagnostic details in text output."),
    ] = False,
    apply: Annotated[
        bool,
        typer.Option(
            "--apply",
            help=(
                "Apply orphan album_asset deletions. Without this flag the command is dry-run only."
            ),
        ),
    ] = False,
) -> None:
    settings = load_settings(env_file=env_file)
    report = RemoteSyncRepairService().run(settings, apply=apply)
    emit_report(report, output, verbose=verbose)
