# immich-doctor

`immich-doctor` is a modular maintenance and repair toolkit for Immich installations.
The project starts as a safe, CLI-first validation tool and is intentionally designed
so that a later API or Web UI can orchestrate the same underlying services.

## Why this project exists

Immich users and self-hosters often need more than a simple health check when their
instance grows:

- storage layouts need verification
- backup targets need validation before changes happen
- database connectivity needs to be checked during maintenance windows
- future repair workflows need reports, traceability, and operational guardrails

The goal of this repository is to provide a future-proof foundation for backup,
analysis, repair, healthcheck, and automation workflows without mixing business
logic into one-off CLI scripts.

## Current status

Project phase: validation + backup snapshot foundation + repair safety foundation + GUI safety visibility + minimal restore/undo orchestration

Current MVP scope:

- safe hierarchical CLI commands only
- configuration loading from environment or `.env`
- runtime environment validation
- physical source and derivative file integrity inspection
- metadata extraction failure diagnostics with root-cause classification
- persisted repair-run and repair-journal foundation for later reversible repair flows
- drift-protected plan tokens for inspect -> plan -> apply binding
- quarantine index foundation for later quarantine-first file handling
- persisted backup snapshot records with manifest metadata and explicit
  files-only vs paired coverage modeling
- pre-repair snapshot creation for integrated mutating repair flows
- GUI visibility for repair runs, journal entries, backup snapshots, and quarantine foundation
- targeted undo for journal-backed runtime permission repairs
- structured full-restore simulation with restore readiness and blockers
- storage path validation
- storage permission validation
- file backup execution through a thin backup application flow
- backup target validation
- non-blocking backup size estimation with persisted background job state
- explicit manual backup target configuration for local, SSH, rsync, and SMB planning
- target validation state and manual backup execution state in the API/UI
- tiered backup execution reporting with explicit verification level
- minimal API health endpoint for the dashboard
- database health validation
- database index inspection
- persistent file catalog foundation with SQLite-backed inventory snapshots
- category-based consistency validation and repair for the supported current PostgreSQL schema
- remote-sync diagnostics with server-side PostgreSQL album/asset link checks
- validation of required external tools when configured
- structured text or JSON reports

Not in scope yet:

- no destructive cleanup phase
- no quarantine moves yet
- no DB backup
- no metadata backup
- no productive SMB backup execution
- no password-based SSH execution support
- no aggressive parallel rsync default
- no automated retention deletion
- no broad full restore execution yet
- no backup-all orchestration

## Safety warning

This repository is not production-safe yet.

Do not treat the current scaffold as a proven one-click rollback tool. The current
phase adds targeted undo for journal-backed runtime permission repairs and
deterministic full-restore simulation, but it still does not provide broad
automated restore execution across all repair domains.

## Development philosophy

- backup first
- analyze before repair
- quarantine before delete
- dry-run before apply
- no automatic destructive repair in the MVP
- integrated mutating repairs must prepare a real pre-repair snapshot before apply
- future repair actions must be traceable through reports and journals

## Planned modules

- backup
- analyze
- repair
- healthcheck
- automations
- future API orchestration layer
- future Web UI orchestration layer

## Canonical command architecture

The CLI is now treated as a stable product contract for future GUI and API work.
All commands must follow this hierarchy:

```text
immich-doctor <domain> <subdomain> <action> [options]
```

Current canonical commands:

```text
immich-doctor runtime validate
immich-doctor analyze catalog scan
immich-doctor analyze catalog status
immich-doctor analyze catalog zero-byte
immich-doctor analyze catalog scan-job status
immich-doctor analyze catalog scan-job start
immich-doctor analyze catalog scan-job pause
immich-doctor analyze catalog scan-job resume
immich-doctor analyze catalog scan-job stop
immich-doctor analyze catalog scan-job workers
immich-doctor runtime health check
immich-doctor runtime integrity inspect
immich-doctor runtime metadata-failures inspect
immich-doctor runtime metadata-failures repair
immich-doctor storage paths check
immich-doctor storage permissions check
immich-doctor backup files
immich-doctor backup verify
immich-doctor backup restore simulate
immich-doctor consistency validate
immich-doctor consistency repair
immich-doctor db health check
immich-doctor db performance indexes check
immich-doctor repair undo plan
immich-doctor repair undo apply
immich-doctor remote sync validate
immich-doctor remote sync repair
```

No legacy aliases are kept.

## Architecture direction

The repository is split into clear layers:

- `immich_doctor.cli`: command-line interface only
- `immich_doctor.services`: reusable application services
- `immich_doctor.adapters`: filesystem, PostgreSQL, and external tool integrations
- `immich_doctor.reports`: structured report output
- `immich_doctor.api`: reserved boundary for future API endpoints

This keeps the CLI as the first interface while ensuring later API or Web UI
implementations can call the same services without duplicating logic.

The first backend-to-UI integration is now available through:

```text
GET /api/health/overview
```

It powers the dashboard health cards with conservative backend-derived states.

## Quick start

1. Create a virtual environment.
2. Install the project in editable mode:

```bash
uv sync --dev
```

1. Copy `.env.example` to `.env` and adjust your paths and PostgreSQL DSN.
2. Run the safe MVP commands:

```bash
uv run python -m immich_doctor runtime health check
uv run python -m immich_doctor runtime validate
uv run python -m immich_doctor analyze catalog scan --root uploads
uv run python -m immich_doctor analyze catalog status
uv run python -m immich_doctor analyze catalog zero-byte --root uploads
uv run python -m immich_doctor analyze catalog scan-job status
uv run python -m immich_doctor analyze catalog scan-job start --force
uv run python -m immich_doctor analyze catalog scan-job pause
uv run python -m immich_doctor analyze catalog scan-job resume
uv run python -m immich_doctor analyze catalog scan-job stop
uv run python -m immich_doctor analyze catalog scan-job workers --workers 8
uv run python -m immich_doctor runtime integrity inspect
uv run python -m immich_doctor runtime metadata-failures inspect
uv run python -m immich_doctor runtime metadata-failures repair
uv run python -m immich_doctor runtime metadata-failures repair --diagnostic-id metadata_failure:asset-123 --fix-permissions --apply
uv run python -m immich_doctor storage paths check
uv run python -m immich_doctor storage permissions check
uv run python -m immich_doctor backup files
uv run python -m immich_doctor backup verify
uv run python -m immich_doctor backup restore simulate --repair-run-id <repair-run-id>
uv run python -m immich_doctor consistency validate
uv run python -m immich_doctor consistency repair --category db.orphan.album_asset.missing_asset
uv run python -m immich_doctor consistency repair --all-safe --apply
uv run python -m immich_doctor db health check
uv run python -m immich_doctor db performance indexes check
uv run python -m immich_doctor db performance indexes check --verbose
uv run python -m immich_doctor repair undo plan --repair-run-id <repair-run-id>
uv run python -m immich_doctor repair undo apply --repair-run-id <repair-run-id>
uv run python -m immich_doctor remote sync validate
uv run python -m immich_doctor remote sync repair
uv run python -m immich_doctor remote sync repair --apply
```

For local dashboard development, start the API runtime and the frontend:

```bash
uv run uvicorn immich_doctor.api.app:create_api_app --factory --reload --host 127.0.0.1 --port 8000
cd ui/frontend
npm install
npm run dev
```

For containerized UI testing, the runtime image now serves both API and UI on:

```text
http://<host>:8000/
```

API example:

```text
http://<host>:8000/api/health/overview
```

Default text output is concise for interactive terminal use.
Use `--verbose` to show full diagnostic details.

Implemented now:

- validation commands across runtime, storage, backup target, and DB health
- `analyze catalog` with mounted SQLite catalog bootstrap, resumable per-root
  inventory sessions, committed snapshots, scan status visibility, and
  zero-byte reporting from persisted catalog data
- `analyze catalog scan-job` lifecycle controls with truthful runtime state:
  - exposed worker visibility: configured count + active count + scan state
  - cooperative pause/resume/stop transitions at safe boundaries
  - runtime worker resize explicitly reported as next-run-only (not immediate)
- runtime file integrity checks for missing, empty, unreadable, truncated,
  corrupted, container-broken, type-mismatched, and unknown-problem files in
  the supported schema
- metadata extraction diagnostics that classify per-asset root cause after file
  integrity inspection
- DB index inspection with compact default output and verbose details
- `backup files` as a thin local file backup flow on top of the backup foundation,
  now with persisted snapshot metadata
- manual files-only execution through the API/UI for local plus safe-subset
  SSH/rsync targets, with SMB kept at configuration and validation planning only

Planned next:

- DB backup inclusion
- metadata capture
- paired DB + file snapshots
- backup-all orchestration
- stronger restore-readiness verification
- scheduled backup orchestration on top of the same target model

`consistency validate` is the canonical server-side consistency overview. It
groups findings by stable categories, supports only
`immich_current_postgres_profile` for now, and reports unsupported schemas
explicitly instead of guessing other Immich variants.

`consistency repair` is dry-run by default and supports selection via
`--category`, `--id`, and `--all-safe`. Only `safe_delete` categories are
eligible for mutation, and only when `--apply` is set. `inspect_only`
categories remain visible under repair but are reported as `SKIPPED`, not as
errors.

Current consistency categories:

- `db.orphan.album_asset.missing_asset`
- `db.orphan.album_asset.missing_album`
- `db.asset_file.path_missing.preview`
- `db.asset_file.path_missing.thumbnail`

For `asset_file.path_missing.*`, the check uses the exact `asset_file.path`
value from PostgreSQL as the container/runtime path. No path rewriting or
library-root inference is applied in this step.

`remote sync validate` is read-only. It distinguishes likely client-side mobile
app SQLite sync errors from server-side PostgreSQL checks. On the server it only
uses detected `album`, `asset`, and `album_asset` tables, resolves foreign keys
from PostgreSQL metadata where possible, reports orphaned join rows when present,
and never repairs or mutates DB content.

`remote sync repair` is separate from validation and defaults to dry-run. It only
targets confirmed orphan rows in `album_asset`, prints planned deletions plus
backup SQL snippets, and writes to PostgreSQL only when `--apply` is set. It does
not modify `asset`, `album`, storage files, thumbnails, or mobile app SQLite sync
state.

`GET /api/health/overview` now provides the first real UI health contract. It
already reports backend-driven states for:

- DB reachability
- storage reachability
- path readiness
- backup readiness
- runtime readiness

Immich API configuration/reachability and scheduler-specific health remain
`unknown` until dedicated backend adapters exist.

The same runtime container now also serves the built Vue frontend over HTTP. The
FastAPI app returns `index.html` on `/`, serves hashed static assets under
`/assets`, and falls back to `index.html` for SPA routes such as `/dashboard`.

The GUI now exposes real safety context before broader repair rollout:

- runtime apply readiness and blocking preconditions
- pre-repair snapshot visibility for integrated runtime apply
- persisted `RepairRun` and journal visibility
- backup snapshot visibility with explicit files-only coverage labeling
- real backup execution actions for:
  - `Start Files-Only Backup`
  - `Create Files-Only Pre-Repair Snapshot`
- quarantine foundation visibility without pretending move/restore is already implemented

Undo visibility now exists in the GUI through persisted journal data. Automated
undo and restore orchestration are still not implemented.

`runtime integrity inspect` is the first physical-file inspection workflow for
the currently supported Immich PostgreSQL runtime schema. It inspects source
files first, optionally includes derivative `asset_file` rows, and classifies
missing, empty, unreadable, truncated, corrupted, container-broken,
type-mismatched, and unknown-problem files without mutating data.

`runtime metadata-failures inspect` consumes those physical file results before
classifying unresolved metadata extraction candidates. Proven file defects are
reported as the root cause of the metadata symptom instead of vague failed-job
counts.

`runtime metadata-failures repair` is dry-run by default. It plans recovery
actions from classified findings and only applies currently safe primitives. In
this step, `fix_permissions` is the only apply-capable action; retry, requeue,
quarantine, and mark-unrecoverable stay report/plan oriented until dedicated
safe execution primitives exist.

Applied runtime metadata permission repair now persists a `RepairRun`,
`plan-token.json`, and `journal.jsonl` under `data/manifests/repair/`. The
journal records old/new mode values for later undo design. Before apply, the
integrated runtime repair flow now also creates a real files-only `pre_repair`
snapshot and stores its `snapshot_id` on the `RepairRun`.

`repair undo plan` and `repair undo apply` now use that persisted journal data
for the first real targeted undo path. In this phase, only runtime permission
repairs with recorded old/new mode values are actually undo-capable. DB-delete
repairs are still not undoable through the tool.

`backup files` now persists one snapshot manifest under
`data/manifests/backup/snapshots/<snapshot_id>.json` for every successful run.
Snapshot metadata includes kind, coverage, source fingerprint, file artifacts,
nullable DB artifact, a persisted internal verification flag, and optional
`repair_run_id`. The API/UI expose only conservative manifest-structure status,
not end-to-end artifact verification.

`backup verify` still checks current backup target-readiness and now also
validates persisted snapshot-manifest structure and declared coverage. It does
not yet
claim full artifact-content verification or restore readiness.

`backup restore simulate` now provides deterministic restore-readiness output,
snapshot selection, blockers, and environment-aware manual steps. It does not
execute destructive full restore operations in this phase.

Manual backup targets in the API/UI are intentionally constrained:

- local targets can execute files-only manual backups
- SSH and rsync targets can execute files-only manual backups only for the
  current private-key transport subset
- SMB targets are configuration, validation, and mount-planning only
- reported verification levels remain limited to transport or destination
  existence checks unless stronger verification is implemented later

The API/UI surface for current repair and backup safety visibility now also includes:

- `GET /api/runtime/metadata-failures/repair-readiness`
- `GET /api/repair/runs`
- `GET /api/repair/runs/{repair_run_id}`
- `GET /api/repair/runs/{repair_run_id}/undo-plan`
- `POST /api/repair/runs/{repair_run_id}/undo`
- `GET /api/repair/quarantine/summary`
- `GET /api/backup/snapshots`
- `GET /api/backup/size-estimate`
- `POST /api/backup/size-estimate/collect`
- `GET /api/backup/targets`
- `POST /api/backup/targets`
- `PUT /api/backup/targets/{target_id}`
- `DELETE /api/backup/targets/{target_id}`
- `GET /api/backup/targets/{target_id}/validation`
- `POST /api/backup/targets/{target_id}/validate`
- `GET /api/backup/executions/current`
- `POST /api/backup/executions`
- `POST /api/backup/executions/cancel`
- `GET /api/restore/simulate`

## Docker

Docker and Compose files live in [`docker/`](./docker).
They are prepared for:

- mounting Immich storage source paths read-only
- mounting backup, report, manifest, quarantine, log, and temp output paths
- mounting an optional config directory
- connecting to Immich PostgreSQL through `DB_*` values or `IMMICH_DOCTOR_POSTGRES_DSN`
- non-root execution by default, with optional `PUID`, `PGID`, and `UMASK` for Unraid

Useful commands:

```bash
docker compose -f docker/docker-compose.yml up --build
docker compose -f docker/docker-compose.dev.yml run --rm immich-doctor
docker compose --env-file .env -f docker/docker-compose.unraid.yml up -d
```

Published image for Unraid and other prebuilt deployments:

```text
ghcr.io/vitalyruhl/immich-doctor:latest
```

Unraid users should prefer the published GHCR image over a local Docker build.

The default container command now starts the HTTP server for both API and UI:

```bash
uvicorn immich_doctor.api:app --host 0.0.0.0 --port 8000
```

Set the Unraid Web UI field to:

```text
http://[IP]:[PORT]/
```

## License

Copyright 2026 Vitaly Ruhl

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

[http://www.apache.org/licenses/LICENSE-2.0](http://www.apache.org/licenses/LICENSE-2.0)

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

## Documentation

- [`docs/roadmap.md`](./docs/roadmap.md)
- [`docs/architecture.md`](./docs/architecture.md)
- [`docs/configuration.md`](./docs/configuration.md)
- [`docs/development.md`](./docs/development.md)
- [`docs/docker.md`](./docs/docker.md)
- [`docs/ready-to-use-commands.md`](./docs/ready-to-use-commands.md)

## Open source workflow

- Contribution guide: [`CONTRIBUTING.md`](./CONTRIBUTING.md)
- Security policy: [`.github/SECURITY.md`](./.github/SECURITY.md)
- Pull requests are required for changes to `main`
- CI and lint checks are intended to be required before merge


<br>
<br>


## Donate

<table align="center" width="100%" border="0" bgcolor:=#3f3f3f>
<tr align="center">
<td align="center">  
if you prefer a one-time donation

[![donate-Paypal](https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif)](https://paypal.me/FamilieRuhl)

</td>

<td align="center">  
Become a patron, by simply clicking on this button (**very appreciated!**):

[![Become a patron](https://c5.patreon.com/external/logo/become_a_patron_button.png)](https://www.patreon.com/join/6555448/checkout?ru=undefined)

</td>
</tr>
</table>

<br>
<br>
