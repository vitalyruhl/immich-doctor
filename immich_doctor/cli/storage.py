from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from immich_doctor.cli._common import emit_report
from immich_doctor.core.config import load_settings
from immich_doctor.storage.empty_folders import EmptyDirQuarantineManager, EmptyFolderScanner
from immich_doctor.storage.paths.service import StoragePathsCheckService
from immich_doctor.storage.permissions.service import StoragePermissionsCheckService

storage_app = typer.Typer(help="Filesystem and mount state checks.")
paths_app = typer.Typer(help="Storage path existence and relationship checks.")
permissions_app = typer.Typer(help="Storage readability and writability checks.")
empty_folders_app = typer.Typer(help="Empty folder detection and quarantine workflows.")

storage_app.add_typer(paths_app, name="paths")
storage_app.add_typer(permissions_app, name="permissions")
storage_app.add_typer(empty_folders_app, name="empty-folders")


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


@empty_folders_app.command("scan")
def empty_folders_scan(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    root: Annotated[
        str | None,
        typer.Option("--root", help="Filter scan to a single storage root slug."),
    ] = None,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show full diagnostic details in text output."),
    ] = False,
) -> None:
    settings = load_settings(env_file=env_file)
    report = EmptyFolderScanner().scan(settings, root_slug=root)
    emit_report(report, output, verbose=verbose)


@empty_folders_app.command("quarantine")
def empty_folders_quarantine(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    root: Annotated[
        list[str] | None,
        typer.Option("--root", help="Select root slugs to quarantine from."),
    ] = None,
    path: Annotated[
        list[str] | None,
        typer.Option("--path", help="Select relative paths or absolute paths to quarantine."),
    ] = None,
    all_items: Annotated[
        bool,
        typer.Option("--all", help="Quarantine every empty directory found in the current scan."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview the quarantine plan without moving directories."),
    ] = False,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
) -> None:
    settings = load_settings(env_file=env_file)
    result = EmptyDirQuarantineManager().quarantine(
        settings,
        root_slugs=tuple(root or ()),
        paths=tuple(path or ()),
        quarantine_all=all_items,
        dry_run=dry_run,
    )
    _emit_action_result(result.to_dict(), output)


@empty_folders_app.command("quarantine-list")
def empty_folders_quarantine_list(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    session_id: Annotated[
        str | None,
        typer.Option("--session-id", help="Optional quarantine session to filter by."),
    ] = None,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
) -> None:
    settings = load_settings(env_file=env_file)
    items = EmptyDirQuarantineManager().list_quarantined(settings, session_id=session_id)
    _emit_action_result(
        {
            "summary": f"Loaded {len(items)} quarantined empty directories.",
            "session_id": session_id,
            "count": len(items),
            "items": [item.to_dict() for item in items],
        },
        output,
    )


@empty_folders_app.command("restore")
def empty_folders_restore(
    session_id: Annotated[
        str,
        typer.Option("--session-id", help="Quarantine session id to restore from."),
    ],
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    path: Annotated[
        list[str] | None,
        typer.Option("--path", help="Selected quarantined paths or item ids to restore."),
    ] = None,
    all_items: Annotated[
        bool,
        typer.Option("--all", help="Restore every active item from the session."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview restore actions without moving directories."),
    ] = False,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
) -> None:
    settings = load_settings(env_file=env_file)
    result = EmptyDirQuarantineManager().restore(
        settings,
        session_id=session_id,
        paths=tuple(path or ()),
        restore_all=all_items,
        dry_run=dry_run,
    )
    _emit_action_result(result.to_dict(), output)


@empty_folders_app.command("delete")
def empty_folders_delete(
    session_id: Annotated[
        str,
        typer.Option("--session-id", help="Quarantine session id to delete from."),
    ],
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", exists=True, file_okay=True),
    ] = None,
    path: Annotated[
        list[str] | None,
        typer.Option("--path", help="Selected quarantined paths or item ids to delete."),
    ] = None,
    all_items: Annotated[
        bool,
        typer.Option("--all", help="Delete every active item from the session."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview delete actions without removing directories."),
    ] = False,
    output: Annotated[str, typer.Option("--output", help="text or json")] = "text",
) -> None:
    settings = load_settings(env_file=env_file)
    result = EmptyDirQuarantineManager().finalize_delete(
        settings,
        session_id=session_id,
        paths=tuple(path or ()),
        delete_all=all_items,
        dry_run=dry_run,
    )
    _emit_action_result(result.to_dict(), output)


def _emit_action_result(payload: dict[str, object], output_format: str) -> None:
    if output_format == "json":
        typer.echo(json.dumps(payload, indent=2))
        raise typer.Exit(code=0)

    typer.echo(f"Summary: {payload.get('summary', 'Action completed.')}")
    if "session_id" in payload and payload.get("session_id"):
        typer.echo(f"Session: {payload['session_id']}")
    if "count" in payload:
        typer.echo(f"Count: {payload['count']}")
    if "quarantined_count" in payload:
        typer.echo(f"Quarantined: {payload['quarantined_count']}")
    if "restored_count" in payload:
        typer.echo(f"Restored: {payload['restored_count']}")
    if "deleted_count" in payload:
        typer.echo(f"Deleted: {payload['deleted_count']}")
    items = payload.get("items") or payload.get("restored") or payload.get("deleted") or []
    if isinstance(items, list) and items:
        typer.echo("Items:")
        for item in items[:10]:
            relative_path = item.get("relative_path", item.get("original_path", ""))
            typer.echo(f"- {item.get('root_slug', '?')}:{relative_path}")
        if len(items) > 10:
            typer.echo("- ...")
    failed = payload.get("failed") or []
    if isinstance(failed, list) and failed:
        typer.echo("Failures:")
        for item in failed:
            typer.echo(f"- {item.get('path', '?')}: {item.get('reason', 'Unknown failure.')}")
    raise typer.Exit(code=0)
