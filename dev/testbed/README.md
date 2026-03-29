# Dev Testbed: DB-Backed Repair Environment

This directory defines a reusable local database testbed for `immich-doctor`.
It is designed for repair development, dependency analysis, and scenario-based
testing against a real Immich PostgreSQL clone. By default it uses synthetic or
empty storage paths, but it can also mount a real Immich storage tree
read-only for local inspect-only verification.

## Purpose

The testbed gives you:

- a real PostgreSQL database clone for Immich
- a safe environment where missing assets are naturally reproducible when real
  asset storage is not mounted
- an optional local runtime/UI path for inspecting the current branch without
  rebuilding on Unraid
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
4. Start PostgreSQL:

```bash
docker compose --env-file dev/testbed/.env -f dev/testbed/docker-compose.yml up -d postgres
```

Start the local UI/runtime service:

```bash
docker compose --env-file dev/testbed/.env -f dev/testbed/docker-compose.yml --profile doctor up -d --build immich-doctor
```

Optional shell container for ad-hoc `uv run ...` commands:

```bash
docker compose --env-file dev/testbed/.env -f dev/testbed/docker-compose.yml --profile doctor-shell up -d immich-doctor-shell
```

The local UI is then available at:

```text
http://localhost:8000
```

## Initialization Modes

### `FROM_DUMP`

Use this mode when you want to restore a real Immich PostgreSQL dump into the
testbed database.

Expected behavior:

- PostgreSQL starts with an empty data volume
- the init script restores the supplied `pg_dump` file into the database
- the dump path comes from `.env` or `--dump`
- PowerShell and Bash both use `.env` dump settings when `--dump` / `-Dump` and format flags are omitted
- relative dump paths are resolved from `dev/testbed/`
- plain SQL `.sql` dumps are handled explicitly
- canonical PostgreSQL cluster dumps are replayed from the maintenance database `postgres`
- bootstrap role statements for the active testbed login role are skipped intentionally to avoid self-drop conflicts and to preserve local testbed access

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

## Asset Storage Modes

By default, the testbed should use a synthetic or empty storage path.

That means:

- filesystem asset lookups should naturally fail
- missing assets are reproducible without touching production files
- the default setup stays suitable for repair and dependency analysis, not media access

Optional local verification mode:

- set `TESTBED_REAL_STORAGE_PATH` in `dev/testbed/.env`
- mount the real Immich storage tree read-only into `/mnt/immich/storage`
- keep all writable doctor paths isolated under `/data/*` and `/config`
- use this only for inspect/scan verification, not for repair/apply against the mounted storage

Windows network-share note:

- source storage path: `\\192.168.2.3\images\immich`
- Docker Desktop bind mounts usually work more reliably with the UNC form `//192.168.2.3/images/immich` inside `.env`

Required runtime mapping stays fixed:

- `IMMICH_STORAGE_PATH=/mnt/immich/storage`
- `IMMICH_UPLOADS_PATH=/mnt/immich/storage/upload`
- `IMMICH_THUMBS_PATH=/mnt/immich/storage/thumbs`
- `IMMICH_PROFILE_PATH=/mnt/immich/storage/profile`
- `IMMICH_VIDEO_PATH=/mnt/immich/storage/encoded-video`

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

Restore result classification:

- `success`
  - no meaningful restore errors were observed
- `partial success`
  - replay completed and the target database exists, but one or more SQL errors were reported
  - this is still usable for debugging when the remaining errors come from source-data inconsistencies or extension/index compatibility issues
- `failure`
  - replay is still structurally wrong, the command failed, or the target database was not recreated

Known plain SQL handling notes:

- Windows CRLF line endings are normalized before replay inside the container
- cluster dumps are not replayed into an already-open target database session
- remaining restore errors are surfaced honestly and are not reported as full success

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

Optional shell-service equivalent:

```bash
docker compose --env-file dev/testbed/.env -f dev/testbed/docker-compose.yml exec immich-doctor-shell \
  uv run python -m immich_doctor consistency validate
```

## Local UI Verification

Example `dev/testbed/.env` additions for local Windows verification:

```text
TESTBED_DOCTOR_PORT=8000
TESTBED_REAL_STORAGE_PATH=//192.168.2.3/images/immich
TESTBED_REPORTS_PATH=../../data/reports
TESTBED_MANIFESTS_PATH=../../data/manifests
TESTBED_QUARANTINE_PATH=../../data/quarantine
TESTBED_LOG_PATH=../../data/logs
TESTBED_TMP_PATH=../../data/tmp
TESTBED_CONFIG_PATH=../../config
```

Recommended start flow:

1. Set `TESTBED_REAL_STORAGE_PATH` only when you intentionally want read-only media inspection.
2. Start PostgreSQL.
3. Restore or initialize the database.
4. Start `immich-doctor` with profile `doctor`.
5. Open `http://localhost:${TESTBED_DOCTOR_PORT}`.
6. Run inspect/scan workflows only.

Safe local verification commands on Windows PowerShell:

```powershell
docker compose --env-file dev/testbed/.env -f dev/testbed/docker-compose.yml up -d postgres
powershell -ExecutionPolicy Bypass -File dev/testbed/scripts/init-db.ps1
docker compose --env-file dev/testbed/.env -f dev/testbed/docker-compose.yml --profile doctor up -d --build immich-doctor
```

Quick checks:

- confirm the UI responds on `http://localhost:8000`
- confirm the mounted storage is read-only:
  - `docker compose --env-file dev/testbed/.env -f dev/testbed/docker-compose.yml exec immich-doctor mount | findstr /C:\"/mnt/immich/storage\"`
- confirm the path-resolution fix against the local stack:
  - `docker compose --env-file dev/testbed/.env -f dev/testbed/docker-compose.yml exec immich-doctor uv run python -m immich_doctor consistency validate`

## Missing Assets Behavior

When no real asset storage is mounted:

- missing asset references should appear naturally during inspection
- `public.asset.originalPath` remains the scan source of truth
- repair preview and apply can be tested against database-only scenarios

When real storage is mounted read-only for local verification:

- `public.asset.originalPath` remains the logical scan source of truth
- the doctor resolves known Immich logical paths against `/mnt/immich/storage`
- findings should report both the logical path and the resolved physical path
- this path is still intended for inspect-oriented verification, not production repair execution

## Safety Notes

- keep database data outside git
- use named volumes for repeatability
- treat snapshots as disposable test artifacts
- prefer dry-run or preview before any destructive step
- document any dump source used for the testbed outside the repository
- if you need a completely clean start, run `reset-db` and then `init-db` again
- keep `TESTBED_REAL_STORAGE_PATH` mounted read-only only
- keep repair/apply against real mounted storage out of scope for this local verification path
