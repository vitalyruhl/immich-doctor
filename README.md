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

Project phase: initial scaffold / MVP skeleton

Current MVP scope:

- safe CLI commands only
- configuration loading from environment or `.env`
- validation of configured Immich paths
- validation of expected configured path relationships
- validation of PostgreSQL connectivity when a DSN is configured
- validation of backup target writability
- runtime validation for container identity, mounted paths, and database reachability
- validation of required external tools when configured
- structured text or JSON reports

Not in scope yet:

- no destructive repair actions
- no file modifications
- no quarantine moves
- no backup execution
- no API or Web UI runtime yet

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

## Architecture direction

The repository is split into clear layers:

- `immich_doctor.cli`: command-line interface only
- `immich_doctor.services`: reusable application services
- `immich_doctor.adapters`: filesystem, PostgreSQL, and external tool integrations
- `immich_doctor.reports`: structured report output
- `immich_doctor.api`: reserved boundary for future API endpoints

This keeps the CLI as the first interface while ensuring later API or Web UI
implementations can call the same services without duplicating logic.

## Quick start

1. Create a virtual environment.
2. Install the project in editable mode:

```bash
uv sync --dev
```

3. Copy `.env.example` to `.env` and adjust your paths and PostgreSQL DSN.
4. Run the safe MVP commands:

```bash
uv run python -m immich_doctor health ping
uv run python -m immich_doctor config validate
uv run python -m immich_doctor backup validate
uv run python -m immich_doctor runtime validate
```

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

The choice is pragmatic for an operational helper tool that may need easy reuse in
private homelab setups, internal automation, and downstream wrappers. If you later
want stronger copyleft guarantees for hosted derivatives or community governance,
re-evaluating AGPL-3.0-or-later before wider adoption would be reasonable.

## Documentation

- [`docs/roadmap.md`](./docs/roadmap.md)
- [`docs/architecture.md`](./docs/architecture.md)
- [`docs/configuration.md`](./docs/configuration.md)
- [`docs/development.md`](./docs/development.md)
- [`docs/docker.md`](./docs/docker.md)

## Open source workflow

- Contribution guide: [`CONTRIBUTING.md`](./CONTRIBUTING.md)
- Security policy: [`.github/SECURITY.md`](./.github/SECURITY.md)
- Pull requests are required for changes to `main`
- CI and lint checks are intended to be required before merge

Changes that could become destructive in future repair workflows require explicit
review and must not bypass the safety principles documented in this repository.
