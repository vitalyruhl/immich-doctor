from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from immich_doctor.catalog.consistency_service import CatalogConsistencyValidationService
from immich_doctor.catalog.service import (
    CatalogInventoryScanService,
    CatalogStatusService,
    CatalogZeroByteReportService,
)
from immich_doctor.cli._common import emit_report
from immich_doctor.core.config import load_settings

analyze_app = typer.Typer(help="Analysis and catalog commands.")
analyze_catalog_app = typer.Typer(help="Persistent file catalog commands.")

analyze_app.add_typer(analyze_catalog_app, name="catalog")


@analyze_catalog_app.command("scan")
def analyze_catalog_scan(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    root: Annotated[str | None, typer.Option("--root")] = None,
    resume_session_id: Annotated[str | None, typer.Option("--resume-session-id")] = None,
    max_files: Annotated[int | None, typer.Option("--max-files", min=1)] = None,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show full diagnostic details in text output."),
    ] = False,
) -> None:
    settings = load_settings(env_file=env_file)
    report = CatalogInventoryScanService().run(
        settings,
        root_slug=root,
        resume_session_id=resume_session_id,
        max_files=max_files,
    )
    emit_report(report, output, verbose=verbose)


@analyze_catalog_app.command("status")
def analyze_catalog_status(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    root: Annotated[str | None, typer.Option("--root")] = None,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show full diagnostic details in text output."),
    ] = False,
) -> None:
    settings = load_settings(env_file=env_file)
    report = CatalogStatusService().run(settings, root_slug=root)
    emit_report(report, output, verbose=verbose)


@analyze_catalog_app.command("zero-byte")
def analyze_catalog_zero_byte(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    root: Annotated[str | None, typer.Option("--root")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1)] = 100,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show full diagnostic details in text output."),
    ] = False,
) -> None:
    settings = load_settings(env_file=env_file)
    report = CatalogZeroByteReportService().run(settings, root_slug=root, limit=limit)
    emit_report(report, output, verbose=verbose)


@analyze_catalog_app.command("consistency")
def analyze_catalog_consistency(
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
    report = CatalogConsistencyValidationService().run(settings)
    emit_report(report, output, verbose=verbose)
