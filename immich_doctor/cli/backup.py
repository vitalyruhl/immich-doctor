from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from immich_doctor.backup.orchestration import BackupFilesService
from immich_doctor.backup.restore import BackupRestoreSimulationService
from immich_doctor.backup.verify.service import BackupVerifyService
from immich_doctor.cli._common import emit_backup_result, emit_report
from immich_doctor.core.config import load_settings

backup_app = typer.Typer(help="Backup commands.")
backup_restore_app = typer.Typer(help="Restore simulation commands.")

backup_app.add_typer(backup_restore_app, name="restore")


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


@backup_restore_app.command("simulate")
def backup_restore_simulate(
    snapshot_id: Annotated[str | None, typer.Option("--snapshot-id")] = None,
    repair_run_id: Annotated[str | None, typer.Option("--repair-run-id")] = None,
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
    report = BackupRestoreSimulationService().simulate(
        settings,
        snapshot_id=snapshot_id,
        repair_run_id=repair_run_id,
    )
    emit_report(report, output, verbose=verbose)
