# Dev Testbed: DB-Backed Repair Environment

This directory defines a reusable local database testbed for `immich-doctor`.
It is designed for repair development, dependency analysis, and scenario-based
testing against a real Immich PostgreSQL clone without mounting real asset
storage.

## Purpose

The testbed gives you:

- a real PostgreSQL database clone for Immich
- a safe environment where missing assets are naturally reproducible because
  asset storage is not mounted
- snapshot and restore operations for the database volume
- a clean base for future repair and FK-analysis scenarios

It does not include production asset files, and it should not contain any
git-tracked database data.

## Layout

Expected files in this folder:

- `dev/testbed/docker-compose.yml`
- `dev/testbed/.env.example`
- `dev/testbed/scripts/init-db.sh` and/or `init-db.ps1`
- `dev/testbed/scripts/snapshot-db.sh` and/or `snapshot-db.ps1`
- `dev/testbed/scripts/restore-db.sh` and/or `restore-db.ps1`
- `dev/testbed/scripts/reset-db.sh` and/or `reset-db.ps1`
- `dev/testbed/scripts/export-db.sh` and/or `export-db.ps1`

Planned volumes:

- `immich_dev_pgdata`
- `immich_dev_pgdata_snapshot`

## Prerequisites

- Docker Desktop on Windows or Docker Engine on Linux
- a PostgreSQL dump file if you want to initialize from a real Immich database
- `immich-doctor` installed locally or available in a container image

## Start

1. Copy `.env.example` to `.env`.
2. Set the database credentials.
3. If you use `FROM_DUMP`, set `TESTBED_DUMP_PATH` to a dump file path.
4. Start the stack:

```bash
docker compose --env-file dev/testbed/.env -f dev/testbed/docker-compose.yml up -d postgres
```

Optional developer container:

```bash
docker compose --env-file dev/testbed/.env -f dev/testbed/docker-compose.yml --profile doctor up -d
```

## Initialization Modes

### `FROM_DUMP`

Use this mode when you want to restore a real Immich PostgreSQL dump into the
testbed database.

Expected behavior:

- PostgreSQL starts with an empty data volume
- the init script restores the supplied `pg_dump` file into the database
- the dump path comes from `.env` or `--dump`
- relative dump paths are resolved from `dev/testbed/`

Example:

```bash
sh dev/testbed/scripts/init-db.sh --mode FROM_DUMP --dump /absolute/path/to/immich.dump
```

### `EMPTY`

Use this mode when you want a clean database for synthetic scenarios.

Expected behavior:

- PostgreSQL starts with an empty named volume
- no dump restore is attempted
- the schema can be created later by your scenario setup

Example:

```powershell
powershell -ExecutionPolicy Bypass -File dev/testbed/scripts/init-db.ps1 -Mode EMPTY
```

Basic EMPTY workflow:

1. `init-db` in `EMPTY` mode
2. reproduce missing-asset scenarios against the DB-only stack
3. `snapshot-db` before manual experiments
4. `export-db` if you want a logical backup
5. `reset-db` to return to a clean empty volume

## No Asset Storage

This testbed intentionally does not mount real Immich asset storage.

That means:

- filesystem asset lookups should naturally fail
- missing assets are reproducible without touching production files
- the testbed is suitable for repair and dependency analysis, not media access

If a placeholder path is mounted, it should be empty or synthetic only.

## Snapshot and Restore

The primary snapshot method is volume copy:

- snapshot: copy `immich_dev_pgdata` to `immich_dev_pgdata_snapshot`
- restore: overwrite `immich_dev_pgdata` from the snapshot volume
- the snapshot volume is created automatically on first snapshot
- repeated snapshots safely overwrite the existing snapshot volume
- restore requires an existing snapshot volume and fails loudly if none exists

Scripts should fail loudly and confirm the target before destructive operations.

Examples:

```bash
sh dev/testbed/scripts/snapshot-db.sh
sh dev/testbed/scripts/restore-db.sh --force
sh dev/testbed/scripts/reset-db.sh --force
```

Optional fallback:

- export a logical backup with `pg_dump`
- restore from the dump when volume copy is not sufficient or not available

Examples:

```bash
sh dev/testbed/scripts/export-db.sh
```

```powershell
powershell -ExecutionPolicy Bypass -File dev/testbed/scripts/export-db.ps1
```

Export behavior:

- if `TESTBED_EXPORT_PATH` or `--output` / `-Output` is provided, that path is used
- otherwise the scripts export to:
  - `dev/testbed/exports/immich-testbed-export.dump` for `custom`
  - `dev/testbed/exports/immich-testbed-export.sql` for `plain`
- the export directory is created automatically
- `dev/testbed/exports/` is ignored by git

## Reset

Reset should return the testbed to a clean, known state.

Recommended reset behavior:

- stop the stack
- remove the active database volume
- optionally remove the snapshot volume
- restart with `EMPTY` or reinitialize from dump
- if the active volume is already absent, reset continues safely
- after reset, `postgres` is started again on a fresh empty volume

Reset must not silently delete anything.

## Connecting `immich-doctor`

Configure `immich-doctor` to point at the testbed database through environment
variables or a PostgreSQL DSN.

Example DSN:

```text
postgresql://postgres:postgres@localhost:5432/immich
```

Typical environment values:

```text
DB_HOST=localhost
DB_PORT=5432
DB_NAME=immich
DB_USER=postgres
DB_PASSWORD=postgres
```

Run consistency commands against the testbed after startup:

```bash
uv run python -m immich_doctor consistency validate
uv run python -m immich_doctor consistency repair --all-safe
```

To run inside the optional container:

```bash
docker compose --env-file dev/testbed/.env -f dev/testbed/docker-compose.yml exec immich-doctor \
  uv run python -m immich_doctor consistency validate
```

## Missing Assets Behavior

Because no real asset storage is mounted:

- missing asset references should appear naturally during inspection
- `public.asset.originalPath` remains the scan source of truth
- repair preview and apply can be tested against database-only scenarios

This environment is intended to support future blocked-asset analysis and
reversible repair development, not production media workflows.

## Safety Notes

- keep database data outside git
- use named volumes for repeatability
- treat snapshots as disposable test artifacts
- prefer dry-run or preview before any destructive step
- document any dump source used for the testbed outside the repository
- if you need a completely clean start, run `reset-db` and then `init-db` again
