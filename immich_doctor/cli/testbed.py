from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from immich_doctor.core.config import load_settings
from immich_doctor.services.testbed_dump_service import (
    TestbedDumpImportService,
    TestbedDumpServiceError,
)

testbed_app = typer.Typer(help="Local-only dev-testbed commands.")


@testbed_app.command("import-dump")
def testbed_import_dump(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    dump: Annotated[str | None, typer.Option("--dump")] = None,
    dump_format: Annotated[str, typer.Option("--format")] = "auto",
    force: Annotated[bool, typer.Option("--force")] = False,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
) -> None:
    settings = load_settings(env_file=env_file)
    try:
        result = TestbedDumpImportService().import_dump(
            settings,
            requested_path=dump,
            dump_format=dump_format,
            force=force,
        )
    except TestbedDumpServiceError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if output == "json":
        typer.echo(json.dumps(result.model_dump(by_alias=True, mode="json"), indent=2))
        raise typer.Exit(code=0)

    typer.echo(result.summary)
    typer.echo(f"classification: {result.classification}")
    typer.echo(f"requested path: {result.requested_path}")
    typer.echo(f"effective path: {result.effective_path}")
    typer.echo(f"dump format: {result.dump_format}")
    if result.meaningful_error_count:
        typer.echo(f"meaningful errors: {result.meaningful_error_count}")
    raise typer.Exit(code=0)
