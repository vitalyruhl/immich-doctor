from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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
analyze_catalog_scan_job_app = typer.Typer(help="Catalog scan runtime lifecycle commands.")

analyze_app.add_typer(analyze_catalog_app, name="catalog")
analyze_catalog_app.add_typer(analyze_catalog_scan_job_app, name="scan-job")


def _catalog_scan_job_api_call(
    *,
    api_base_url: str,
    method: str,
    endpoint: str,
    payload: dict[str, object] | None = None,
    timeout: float = 8.0,
) -> dict[str, object]:
    base = api_base_url.rstrip("/")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{base}{endpoint}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise typer.BadParameter(
            f"Catalog scan-job API request failed with HTTP {exc.code}: {detail}"
        ) from exc
    except URLError as exc:
        raise typer.BadParameter(
            f"Catalog scan-job API request failed: {exc.reason}"
        ) from exc


def _emit_catalog_scan_job_response(payload: dict[str, object], output: str) -> None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        typer.echo("Catalog scan-job response was not a JSON object.")
        raise typer.Exit(code=1)

    if output == "json":
        typer.echo(json.dumps(data, indent=2))
    else:
        state = str(data.get("state") or "unknown")
        summary = str(data.get("summary") or "No summary available.")
        runtime = (
            data.get("result", {}).get("runtime")
            if isinstance(data.get("result"), dict)
            else None
        )
        if not isinstance(runtime, dict):
            runtime = {}
        typer.echo(f"State: {state}")
        typer.echo(f"Summary: {summary}")
        typer.echo(f"Scan state: {runtime.get('scanState', 'idle')}")
        typer.echo(f"Configured workers: {runtime.get('configuredWorkerCount', 'n/a')}")
        typer.echo(f"Active workers: {runtime.get('activeWorkerCount', 'n/a')}")
        worker_resize = runtime.get("workerResize")
        if isinstance(worker_resize, dict):
            typer.echo(
                "Worker resize: "
                f"{worker_resize.get('semantics', 'unknown')} "
                f"(supported={worker_resize.get('supported', False)})"
            )

    state = str(data.get("state") or "")
    raise typer.Exit(code=1 if state == "failed" else 0)


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


@analyze_catalog_scan_job_app.command("status")
def analyze_catalog_scan_job_status(
    api_base_url: Annotated[str, typer.Option("--api-base-url")] = "http://127.0.0.1:8000/api",
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
) -> None:
    payload = _catalog_scan_job_api_call(
        api_base_url=api_base_url,
        method="GET",
        endpoint="/analyze/catalog/scan-job",
    )
    _emit_catalog_scan_job_response(payload, output)


@analyze_catalog_scan_job_app.command("start")
def analyze_catalog_scan_job_start(
    api_base_url: Annotated[str, typer.Option("--api-base-url")] = "http://127.0.0.1:8000/api",
    force: Annotated[bool, typer.Option("--force")] = False,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
) -> None:
    payload = _catalog_scan_job_api_call(
        api_base_url=api_base_url,
        method="POST",
        endpoint="/analyze/catalog/scan-job/start",
        payload={"force": force},
    )
    _emit_catalog_scan_job_response(payload, output)


@analyze_catalog_scan_job_app.command("pause")
def analyze_catalog_scan_job_pause(
    api_base_url: Annotated[str, typer.Option("--api-base-url")] = "http://127.0.0.1:8000/api",
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
) -> None:
    payload = _catalog_scan_job_api_call(
        api_base_url=api_base_url,
        method="POST",
        endpoint="/analyze/catalog/scan-job/pause",
    )
    _emit_catalog_scan_job_response(payload, output)


@analyze_catalog_scan_job_app.command("resume")
def analyze_catalog_scan_job_resume(
    api_base_url: Annotated[str, typer.Option("--api-base-url")] = "http://127.0.0.1:8000/api",
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
) -> None:
    payload = _catalog_scan_job_api_call(
        api_base_url=api_base_url,
        method="POST",
        endpoint="/analyze/catalog/scan-job/resume",
    )
    _emit_catalog_scan_job_response(payload, output)


@analyze_catalog_scan_job_app.command("stop")
def analyze_catalog_scan_job_stop(
    api_base_url: Annotated[str, typer.Option("--api-base-url")] = "http://127.0.0.1:8000/api",
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
) -> None:
    payload = _catalog_scan_job_api_call(
        api_base_url=api_base_url,
        method="POST",
        endpoint="/analyze/catalog/scan-job/stop",
    )
    _emit_catalog_scan_job_response(payload, output)


@analyze_catalog_scan_job_app.command("workers")
def analyze_catalog_scan_job_workers(
    workers: Annotated[int, typer.Option("--workers", min=1)],
    api_base_url: Annotated[str, typer.Option("--api-base-url")] = "http://127.0.0.1:8000/api",
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
) -> None:
    payload = _catalog_scan_job_api_call(
        api_base_url=api_base_url,
        method="POST",
        endpoint="/analyze/catalog/scan-job/workers",
        payload={"workers": workers},
    )
    _emit_catalog_scan_job_response(payload, output)
