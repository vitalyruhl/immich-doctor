from __future__ import annotations

import typer

from immich_doctor.cli.backup import backup_app
from immich_doctor.cli.config import config_app
from immich_doctor.cli.health import health_app

app = typer.Typer(
    help="Safe CLI-first validation toolkit for Immich environments.",
    no_args_is_help=True,
)
app.add_typer(health_app, name="health")
app.add_typer(config_app, name="config")
app.add_typer(backup_app, name="backup")

