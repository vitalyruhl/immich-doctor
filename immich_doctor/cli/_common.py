from __future__ import annotations

import json

import typer

from immich_doctor.backup.core.models import BackupResult
from immich_doctor.consistency.models import ConsistencyRepairResult, ConsistencyValidationReport
from immich_doctor.core.models import RepairReport, ValidationReport
from immich_doctor.reports.backup_result import render_backup_result_json, render_backup_result_text
from immich_doctor.reports.json_writer import render_json_report
from immich_doctor.reports.text_writer import render_text_report
from immich_doctor.runtime.integrity.models import FileIntegrityInspectResult
from immich_doctor.runtime.metadata_failures.models import (
    MetadataFailureInspectResult,
    MetadataFailureRepairResult,
)


def emit_report(
    report: ValidationReport
    | RepairReport
    | ConsistencyValidationReport
    | ConsistencyRepairResult
    | FileIntegrityInspectResult
    | MetadataFailureInspectResult
    | MetadataFailureRepairResult,
    output_format: str,
    verbose: bool = False,
) -> None:
    if output_format == "json":
        typer.echo(json.dumps(render_json_report(report), indent=2))
    else:
        typer.echo(render_text_report(report, verbose=verbose))
    raise typer.Exit(code=report.exit_code)


def emit_backup_result(result: BackupResult, output_format: str) -> None:
    if output_format == "json":
        typer.echo(json.dumps(render_backup_result_json(result), indent=2))
    else:
        typer.echo(render_backup_result_text(result))
    raise typer.Exit(code=result.exit_code)
