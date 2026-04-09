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
- `dev/testbed/scripts/compose.sh` and/or `compose.ps1`
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

1. Review the tracked `dev/testbed/.env` defaults.
2. Copy `.env.example` to `.env.local` when you need machine-specific overrides or credentials.
3. If you use `FROM_DUMP`, set `TESTBED_DUMP_PATH` in `.env.local` or pass it to the init script.
4. Start the stack:

```bash
sh dev/testbed/scripts/compose.sh up -d postgres
```

Optional runtime/UI container:

```bash
sh dev/testbed/scripts/compose.sh --profile doctor up -d --build
```

The wrapper resolves `TESTBED_STORAGE_SOURCE_MODE` and injects the correct bind source for
mock or real storage before delegating to `docker compose`.

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

## Storage Modes

The testbed now keeps storage intent explicit:

- `TESTBED_STORAGE_SOURCE_MODE=mock`
  - mounts `TESTBED_MOCK_STORAGE_PATH`
  - intended for small synthetic or repo-local datasets
- `TESTBED_STORAGE_SOURCE_MODE=real`
  - mounts `TESTBED_REAL_STORAGE_PATH` when `TESTBED_REAL_STORAGE_MODE=host-bind`
  - mounts `TESTBED_REAL_STORAGE_SMB_SOURCE` from inside the doctor container when `TESTBED_REAL_STORAGE_MODE=cifs`
  - intended for realistic validation against a read-only copy or direct read-only SMB view of real Immich storage

Real-storage semantics remain first-class:

- `TESTBED_REAL_STORAGE_PATH` is the bind source used for realistic validation
- `TESTBED_REAL_STORAGE_MODE`, `TESTBED_REAL_STORAGE_SMB_SOURCE`, and `TESTBED_REAL_STORAGE_SMB_VERS`
  document how that storage is provided to the local host
- `TESTBED_REAL_STORAGE_SMB_USERNAME` and `TESTBED_REAL_STORAGE_SMB_PASSWORD`
  remain supported as local-only settings and must stay in `.env.local`
- `TESTBED_REAL_STORAGE_SMB_DOMAIN`, `TESTBED_REAL_STORAGE_SMB_UID`, and `TESTBED_REAL_STORAGE_SMB_GID`
  tune optional CIFS mount behavior inside the doctor container

Safety rules:

- the storage mount is always read-only inside the doctor container
- doctor-owned writable paths stay separate:
  - `TESTBED_REPORTS_PATH`
  - `TESTBED_MANIFESTS_PATH`
  - `TESTBED_QUARANTINE_PATH`
  - `TESTBED_LOG_PATH`
  - `TESTBED_TMP_PATH`
- the persistent catalog always lives under `MANIFESTS_PATH/catalog/`
- the catalog must never be written into the storage mount itself

When `TESTBED_REAL_STORAGE_MODE=cifs`, the wrapper automatically layers
`dev/testbed/docker-compose.real-storage.yml` on top of the base compose file,
starts the doctor container as root, mounts the SMB share read-only inside the
container, and keeps doctor-owned writable paths outside that mount.

When `TESTBED_REAL_STORAGE_MODE=host-bind`, Windows can still use a host-prepared
mount such as a mapped drive or `subst` path.

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

To start the runtime UI container:

```bash
sh dev/testbed/scripts/compose.sh --profile doctor up -d --build
```

The browser UI is then available at `http://localhost:${TESTBED_DOCTOR_PORT}`.

If you run raw `docker compose` commands instead of the helper wrapper, you must export
`TESTBED_SELECTED_STORAGE_PATH` yourself so it matches `TESTBED_STORAGE_SOURCE_MODE`.

Catalog Phase 1 validation:

- `POST /api/analyze/catalog/scan` starts a non-destructive inventory scan
- `GET /api/analyze/catalog/status` shows persisted snapshot/session state
- `GET /api/analyze/catalog/zero-byte` shows zero-byte findings from the latest committed snapshot
- the SQLite catalog lives at `MANIFESTS_PATH/catalog/file-catalog.sqlite3`

## Missing Assets Behavior

In `mock` mode, missing-asset scenarios are easy to reproduce with synthetic content.
In `real` mode, the testbed can validate a real DB copy against a read-only view of real
storage while still keeping all doctor-owned writes isolated from that mount.

`public.asset.originalPath` remains the scan source of truth for database-side checks.

## Safety Notes

- keep database data outside git
- keep `.env.local` and any credentials outside git
- use named volumes for repeatability
- treat snapshots as disposable test artifacts
- prefer dry-run or preview before any destructive step
- document any dump source used for the testbed outside the repository
- if you need a completely clean start, run `reset-db` and then `init-db` again
