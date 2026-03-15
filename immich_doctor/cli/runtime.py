from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from immich_doctor.cli._common import emit_report
from immich_doctor.core.config import load_settings
from immich_doctor.runtime.health.service import RuntimeHealthCheckService
from immich_doctor.runtime.integrity.service import RuntimeIntegrityInspectService
from immich_doctor.runtime.metadata_failures.repair_service import (
    RuntimeMetadataFailuresRepairService,
)
from immich_doctor.runtime.metadata_failures.service import (
    RuntimeMetadataFailuresInspectService,
)
from immich_doctor.runtime.validate.service import RuntimeValidationService

runtime_app = typer.Typer(help="Execution environment validation commands.")
runtime_health_app = typer.Typer(help="Runtime reachability and readiness checks.")
runtime_integrity_app = typer.Typer(help="Physical file integrity diagnostics.")
runtime_metadata_failures_app = typer.Typer(help="Metadata extraction failure diagnostics.")

runtime_app.add_typer(runtime_health_app, name="health")
runtime_app.add_typer(runtime_integrity_app, name="integrity")
runtime_app.add_typer(runtime_metadata_failures_app, name="metadata-failures")


@runtime_app.command("validate")
def runtime_validate(
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
    report = RuntimeValidationService().run(settings)
    emit_report(report, output, verbose=verbose)


@runtime_health_app.command("check")
def runtime_health_check(
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show full diagnostic details in text output."),
    ] = False,
) -> None:
    report = RuntimeHealthCheckService().run()
    emit_report(report, output, verbose=verbose)


@runtime_integrity_app.command("inspect")
def runtime_integrity_inspect(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1)] = 100,
    offset: Annotated[int, typer.Option("--offset", min=0)] = 0,
    include_derivatives: Annotated[bool, typer.Option("--include-derivatives")] = True,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show full diagnostic details in text output."),
    ] = False,
) -> None:
    settings = load_settings(env_file=env_file)
    report = RuntimeIntegrityInspectService().run(
        settings,
        limit=limit,
        offset=offset,
        include_derivatives=include_derivatives,
    )
    emit_report(report, output, verbose=verbose)


@runtime_metadata_failures_app.command("inspect")
def runtime_metadata_failures_inspect(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1)] = 100,
    offset: Annotated[int, typer.Option("--offset", min=0)] = 0,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show full diagnostic details in text output."),
    ] = False,
) -> None:
    settings = load_settings(env_file=env_file)
    report = RuntimeMetadataFailuresInspectService().run(
        settings,
        limit=limit,
        offset=offset,
    )
    emit_report(report, output, verbose=verbose)


@runtime_metadata_failures_app.command("repair")
def runtime_metadata_failures_repair(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1)] = 100,
    offset: Annotated[int, typer.Option("--offset", min=0)] = 0,
    diagnostic_ids: Annotated[list[str] | None, typer.Option("--diagnostic-id")] = None,
    apply: Annotated[bool, typer.Option("--apply")] = False,
    retry_jobs: Annotated[bool, typer.Option("--retry-jobs")] = False,
    requeue: Annotated[bool, typer.Option("--requeue")] = False,
    fix_permissions: Annotated[bool, typer.Option("--fix-permissions")] = False,
    quarantine_corrupt: Annotated[bool, typer.Option("--quarantine-corrupt")] = False,
    mark_unrecoverable: Annotated[bool, typer.Option("--mark-unrecoverable")] = False,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show full diagnostic details in text output."),
    ] = False,
) -> None:
    settings = load_settings(env_file=env_file)
    report = RuntimeMetadataFailuresRepairService().run(
        settings,
        apply=apply,
        limit=limit,
        offset=offset,
        diagnostic_ids=tuple(diagnostic_ids or ()),
        retry_jobs=retry_jobs,
        requeue=requeue,
        fix_permissions=fix_permissions,
        quarantine_corrupt=quarantine_corrupt,
        mark_unrecoverable=mark_unrecoverable,
    )
    emit_report(report, output, verbose=verbose)
