from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from immich_doctor.cli._common import emit_report
from immich_doctor.consistency.repair_service import ConsistencyRepairService
from immich_doctor.consistency.service import ConsistencyValidationService
from immich_doctor.core.config import load_settings

consistency_app = typer.Typer(help="Category-based consistency validation and repair.")


@consistency_app.command("validate")
def consistency_validate(
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
    report = ConsistencyValidationService().run(settings)
    emit_report(report, output, verbose=verbose)


@consistency_app.command("repair")
def consistency_repair(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    category: Annotated[
        list[str] | None,
        typer.Option("--category", help="Select one or more consistency categories."),
    ] = None,
    finding_id: Annotated[
        list[str] | None,
        typer.Option("--id", help="Select one or more finding IDs."),
    ] = None,
    all_safe: Annotated[
        bool,
        typer.Option("--all-safe", help="Select all safe_delete categories."),
    ] = False,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Apply writes. Without this flag the run stays dry-run."),
    ] = False,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show full diagnostic details in text output."),
    ] = False,
) -> None:
    settings = load_settings(env_file=env_file)
    report = ConsistencyRepairService().run(
        settings,
        categories=tuple(category or []),
        finding_ids=tuple(finding_id or []),
        all_safe=all_safe,
        apply=apply,
    )
    emit_report(report, output, verbose=verbose)
