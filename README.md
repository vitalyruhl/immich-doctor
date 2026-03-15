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

Project phase: validation + early backup foundation

Current MVP scope:

- safe hierarchical CLI commands only
- configuration loading from environment or `.env`
- runtime environment validation
- storage path validation
- storage permission validation
- file backup execution through a thin backup application flow
- backup target verification
- minimal API health endpoint for the dashboard
- database health validation
- database index inspection
- category-based consistency validation and repair for the supported current PostgreSQL schema
- remote-sync diagnostics with server-side PostgreSQL album/asset link checks
- validation of required external tools when configured
- structured text or JSON reports

Not in scope yet:

- no destructive repair actions
- no file modifications
- no quarantine moves
- no DB backup
- no metadata backup
- no remote backup targets
- no retention
- no restore
- no backup-all orchestration

## Safety warning

This repository is not production-safe yet.

Do not treat the current scaffold as a proven repair tool. The MVP only provides
safe validation flows and report generation. Any future repair capability must be
introduced carefully, documented, reviewed, and validated before real-world use.

## Development philosophy

- backup first
- analyze before repair
- quarantine before delete
- dry-run before apply
- no automatic destructive repair in the MVP
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
immich-doctor runtime health check
immich-doctor storage paths check
immich-doctor storage permissions check
immich-doctor backup files
immich-doctor backup verify
immich-doctor consistency validate
immich-doctor consistency repair
immich-doctor db health check
immich-doctor db performance indexes check
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

3. Copy `.env.example` to `.env` and adjust your paths and PostgreSQL DSN.
4. Run the safe MVP commands:

```bash
uv run python -m immich_doctor runtime health check
uv run python -m immich_doctor runtime validate
uv run python -m immich_doctor storage paths check
uv run python -m immich_doctor storage permissions check
uv run python -m immich_doctor backup files
uv run python -m immich_doctor backup verify
uv run python -m immich_doctor consistency validate
uv run python -m immich_doctor consistency repair --category db.orphan.album_asset.missing_asset
uv run python -m immich_doctor consistency repair --all-safe --apply
uv run python -m immich_doctor db health check
uv run python -m immich_doctor db performance indexes check
uv run python -m immich_doctor db performance indexes check --verbose
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

Default text output is concise for interactive terminal use.
Use `--verbose` to show full diagnostic details.

Implemented now:

- validation commands across runtime, storage, backup target, and DB health
- DB index inspection with compact default output and verbose details
- `backup files` as a thin local file backup flow on top of the backup foundation

Planned next:

- backup manifests
- DB backup inclusion
- metadata capture
- backup-all orchestration

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

The default container command remains safe and non-destructive:

```bash
python -m immich_doctor runtime validate
```

## License recommendation

This repository currently uses the MIT license.


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

