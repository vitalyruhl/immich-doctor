from __future__ import annotations

import typer

from immich_doctor.cli.backup import backup_app
from immich_doctor.cli.db import db_app
from immich_doctor.cli.remote import remote_app
from immich_doctor.cli.runtime import runtime_app
from immich_doctor.cli.storage import storage_app

app = typer.Typer(
    help="Safe CLI-first validation toolkit for Immich environments.",
    no_args_is_help=True,
)
app.add_typer(backup_app, name="backup")
app.add_typer(db_app, name="db")
app.add_typer(remote_app, name="remote")
app.add_typer(runtime_app, name="runtime")
app.add_typer(storage_app, name="storage")
