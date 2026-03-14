from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from immich_doctor.cli._common import emit_report
from immich_doctor.core.config import load_settings
from immich_doctor.storage.paths.service import StoragePathsCheckService
from immich_doctor.storage.permissions.service import StoragePermissionsCheckService

storage_app = typer.Typer(help="Filesystem and mount state checks.")
paths_app = typer.Typer(help="Storage path existence and relationship checks.")
permissions_app = typer.Typer(help="Storage readability and writability checks.")

storage_app.add_typer(paths_app, name="paths")
storage_app.add_typer(permissions_app, name="permissions")


@paths_app.command("check")
def storage_paths_check(
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
    report = StoragePathsCheckService().run(settings)
    emit_report(report, output, verbose=verbose)


@permissions_app.command("check")
def storage_permissions_check(
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
    report = StoragePermissionsCheckService().run(settings)
    emit_report(report, output, verbose=verbose)
