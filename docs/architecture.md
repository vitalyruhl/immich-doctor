# Architecture

## Purpose

`immich-doctor` is designed as a CLI-first maintenance tool that can grow into an
API-backed and UI-driven system later without rewriting core logic.

## Architectural principles

- keep business rules out of the CLI layer
- keep integrations behind adapters
- keep services reusable by CLI, API, and future background jobs
- keep repair behavior non-destructive by default
- keep reports and journals as first-class outputs

## Module boundaries

### `immich_doctor.cli`

Contains only command definitions, option parsing, exit-code handling, and output
selection. It should never become the only place where workflow logic lives.

### `immich_doctor.services`

Contains the application use cases. Services orchestrate adapters and build
structured reports for CLI or future API responses.

### `immich_doctor.adapters`

Contains infrastructure-facing code such as:

- filesystem checks
- PostgreSQL connectivity
- external tool detection

### `immich_doctor.db`

Reserved for PostgreSQL-specific connection and query helpers that may later grow
beyond simple connectivity checks.

### `immich_doctor.reports`

Transforms service results into stable text or JSON output and later into persisted
artifacts.

### `immich_doctor.api`

Reserved integration boundary for future API routes. The API must call the same
services as the CLI instead of duplicating business rules.

## CLI, API, and UI relationship

The intended long-term flow is:

1. services contain the workflow logic
2. CLI calls services directly
3. API calls the same services
4. Web UI calls the API and renders reports, status, and workflow controls

This keeps the Web UI as an orchestration layer instead of a second source of truth.

## Future background jobs

Background jobs should eventually trigger the same service methods as the CLI and
API. They should produce reports and journals with enough metadata for later review.

## Runtime data locations

The repository already reserves runtime-oriented paths under `data/`:

- `data/reports/`
- `data/manifests/`
- `data/quarantine/`
- `data/logs/`
- `data/tmp/`

These locations are intentionally separated so future workflows can remain traceable
and so destructive behavior is not hidden inside temporary scripting.

## Safety rules

- backup first
- analyze before repair
- quarantine before delete
- dry-run before apply
- no automatic destructive repair in the MVP
- future repair actions must be traceable in reports and journals

