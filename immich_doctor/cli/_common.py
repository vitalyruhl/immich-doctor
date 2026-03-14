from __future__ import annotations

import json

import typer

from immich_doctor.core.models import ValidationReport
from immich_doctor.reports.json_writer import render_json_report
from immich_doctor.reports.text_writer import render_text_report


def emit_report(report: ValidationReport, output_format: str) -> None:
    if output_format == "json":
        typer.echo(json.dumps(render_json_report(report), indent=2))
    else:
        typer.echo(render_text_report(report))
    raise typer.Exit(code=report.exit_code)
