from __future__ import annotations

import typer

from immich_doctor.cli.analyze import analyze_app
from immich_doctor.cli.backup import backup_app
from immich_doctor.cli.consistency import consistency_app
from immich_doctor.cli.db import db_app
from immich_doctor.cli.remote import remote_app
from immich_doctor.cli.repair import repair_app
from immich_doctor.cli.runtime import runtime_app
from immich_doctor.cli.storage import storage_app
from immich_doctor.cli.testbed import testbed_app

app = typer.Typer(
    help="Safe CLI-first validation toolkit for Immich environments.",
    no_args_is_help=True,
)
app.add_typer(analyze_app, name="analyze")
app.add_typer(backup_app, name="backup")
app.add_typer(consistency_app, name="consistency")
app.add_typer(db_app, name="db")
app.add_typer(repair_app, name="repair")
app.add_typer(remote_app, name="remote")
app.add_typer(runtime_app, name="runtime")
app.add_typer(storage_app, name="storage")
app.add_typer(testbed_app, name="testbed")
