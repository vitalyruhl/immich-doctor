from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from immich_doctor.cli._common import emit_report
from immich_doctor.core.config import load_settings
from immich_doctor.repair import RepairUndoService

repair_app = typer.Typer(help="Repair safety and undo commands.")
repair_undo_app = typer.Typer(help="Targeted undo planning and execution.")

repair_app.add_typer(repair_undo_app, name="undo")


@repair_undo_app.command("plan")
def repair_undo_plan(
    repair_run_id: Annotated[str, typer.Option("--repair-run-id")],
    entry_ids: Annotated[list[str] | None, typer.Option("--entry-id")] = None,
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
    report = RepairUndoService().plan(
        settings,
        repair_run_id=repair_run_id,
        entry_ids=tuple(entry_ids or ()),
    )
    emit_report(report, output, verbose=verbose)


@repair_undo_app.command("apply")
def repair_undo_apply(
    repair_run_id: Annotated[str, typer.Option("--repair-run-id")],
    entry_ids: Annotated[list[str] | None, typer.Option("--entry-id")] = None,
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
    report = RepairUndoService().execute(
        settings,
        repair_run_id=repair_run_id,
        entry_ids=tuple(entry_ids or ()),
        apply=True,
    )
    emit_report(report, output, verbose=verbose)
