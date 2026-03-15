# Architecture

## Purpose

`immich-doctor` is designed as a CLI-first maintenance tool that can grow into an
API-backed and UI-driven system without rewriting core logic.

## Architectural principles

- keep business rules out of the CLI layer
- keep integrations behind adapters
- keep services reusable by CLI, API, and future background jobs
- keep repair behavior non-destructive by default
- keep reports and journals as first-class outputs
- keep the CLI hierarchy stable enough for future GUI and API mapping

## Canonical command hierarchy

All project commands must follow:

```text
immich-doctor <domain> <subdomain> <action> [options]
```

Top-level domains:

- `runtime`
- `consistency`
- `db`
- `remote`
- `storage`
- `backup`
- `diagnostics`
- `system`

Current canonical command surface:

```text
immich-doctor runtime validate
immich-doctor runtime health check
immich-doctor runtime integrity inspect
immich-doctor runtime metadata-failures inspect
immich-doctor runtime metadata-failures repair
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

Placement rules:

- consistency: canonical category-first validation and repair planning/execution
  for supported server-side PostgreSQL and direct container-path consistency work
- runtime: process-level readiness and execution-environment checks
- runtime.integrity: physical source and derivative file integrity inspection for
  the currently supported Immich PostgreSQL runtime schema
- runtime.metadata-failures: metadata extraction diagnostics and repair planning
  that consume physical file findings before classifying job-level failures
- db.health: reachability, login, session creation, round-trip queries
- db.performance.indexes: index existence, invalid indexes, usage, size, missing FK indexes
- storage.paths: storage path existence and structural relationships
- storage.permissions: readability, writability, and mount safety
- backup.files: versioned local file backup execution through the backup application layer
- backup.verify: backup target readiness and required tool presence
- remote.sync: older separate remote-scope diagnostics and repair flow; not the
  canonical consistency command family

Forbidden patterns:

- flat domain-specific flags
- one-off commands like `check-indexes`
- health commands that perform integrity or performance analysis
- legacy concepts like `config validate` as a primary command

Output expectation:

- default text output should stay concise for interactive terminal use
- `--verbose` should reveal the full diagnostic detail set when needed
- collectors keep rich data; renderers decide how much to show

## Migration mapping

Current old-to-new mapping:

- `health ping` -> `runtime health check`
- `config validate` -> `runtime validate`
- `config validate` -> `storage paths check`
- `config validate` -> `storage permissions check`
- `config validate` -> `db health check`
- `backup validate` -> `backup verify`
- `db validate-indexes` -> `db performance indexes check`

No temporary compatibility aliases are kept.

## Module boundaries

### `immich_doctor.cli`

Contains only command definitions, option parsing, exit-code handling, and output
selection. It should never become the only place where workflow logic lives.

### `immich_doctor.services`

Contains the application use cases. Services orchestrate adapters and build
structured reports for CLI or future API responses.

Current examples include runtime validation, runtime integrity inspection,
runtime metadata failure diagnostics and repair planning, storage checks, backup
verification, database health checks, database index inspection, the
consistency framework, remote-sync FK validation, and dashboard health
aggregation for the API/UI layer.

### `immich_doctor.adapters`

Contains infrastructure-facing code such as:

- filesystem checks
- PostgreSQL connectivity
- external tool detection

### `immich_doctor.db`

Reserved for PostgreSQL-specific connection and query helpers that may later grow
beyond simple connectivity checks.

## Backup domain foundation (WIP)

The backup domain now has a dedicated internal foundation package layout that is
prepared for later implementation work without exposing new user-facing commands.

Current internal backup packages:

- `immich_doctor.backup.core`
- `immich_doctor.backup.db`
- `immich_doctor.backup.files`
- `immich_doctor.backup.metadata`
- `immich_doctor.backup.orchestration`
- `immich_doctor.backup.scheduler`
- `immich_doctor.backup.remote`

Responsibilities:

- `backup.core`: shared backup data contracts such as context, jobs, targets,
  artifacts, manifests, results, and location resolution
- `backup.db`: future PostgreSQL backup coordination
- `backup.files`: future filesystem artifact collection
- `backup.metadata`: future metadata and manifest enrichment
- `backup.orchestration`: future sequential backup planning, locking, and reporting
- `backup.scheduler`: future scheduler integration boundary
- `backup.remote`: future remote transport integration boundary

This step is intentionally structural only:

- no subprocess integration
- no storage writes
- no remote transfer
- no scheduling logic

Phase 1 created the package structure and shared contracts. Phase 2 added the
local rsync foundation. Phase 3 now adds the first thin user-facing backup
command without expanding into DB backup, metadata capture, remote targets, or
backup-all orchestration.

### Backup files rsync foundation (WIP)

Phase 2 adds a local file-backup foundation under `immich_doctor.backup.files`.

Current file-backup internals are limited to:

- request and execution-plan models for local source to local target flows
- deterministic versioned destination path generation
- safe rsync command construction with non-destructive defaults
- a local executor abstraction that runs rsync via argument lists only

Explicit constraints for this phase:

- local paths only
- no remote transport
- no database backup coupling
- no scheduling
- no retention
- no destructive rsync flags such as `--delete`

### Backup files application flow (WIP)

Phase 3 adds a thin `backup files` command on top of the Phase 1 and Phase 2
backup foundation.

Current flow:

1. CLI parses arguments and loads settings
2. `BackupFilesService` creates one backup operation context
3. `BackupLocationResolver` resolves the configured local target
4. file backup request and execution plan are created
5. rsync command construction stays in `immich_doctor.backup.files`
6. local execution returns one shared `BackupResult`

Current constraints:

- `BackupContext.started_at` is the authoritative timestamp for one backup set
- rsync remains confined to `backup.files`
- CLI does not import subprocess or rsync internals
- artifact paths must stay traceable from the backup root
- no retention, remote transport, DB backup, scheduler, or backup-all logic

Implemented now:

- one local source to local target file backup flow
- versioned destination generation from one authoritative backup context timestamp
- target resolution through `BackupLocationResolver`
- structured `BackupResult` and traceable `BackupArtifact` metadata

Planned next:

- manifest persistence
- DB backup integration
- metadata backup integration
- higher-level backup orchestration across multiple artifacts

### `immich_doctor.reports`

Transforms service results into stable text or JSON output and later into persisted
artifacts.

### `immich_doctor.api`

Contains thin API routes that call the same services as the CLI instead of
duplicating business rules.

Current API surface:

- `GET /api/health/overview`
- `GET /api/runtime/integrity/inspect`
- `GET /api/runtime/metadata-failures/inspect`
- `POST /api/runtime/metadata-failures/repair`
- `GET /api/settings`
- `GET /api/settings/schema`
- `PUT /api/settings`

Current API constraints:

- dashboard health is aggregated conservatively from existing backend checks
- unimplemented capabilities remain `unknown`
- API routes stay orchestration-thin and defer logic to services
- runtime integrity inspection must classify physical file defects before
  metadata failure diagnostics consume those results
- metadata failure diagnostics must treat proven file defects as root causes
  instead of presenting them as unexplained job failures
- metadata repair remains dry-run by default and may only apply actions with
  explicit safe execution primitives
- settings routes use `/api/settings` as the canonical global contract; nested
  domain-specific settings prefixes are not allowed
- `PUT /api/settings` is reserved but remains non-persistent until a safe
  settings write workflow exists

## CLI, API, and UI relationship

The intended long-term flow is:

1. services contain the workflow logic
2. CLI calls services directly
3. API calls the same services
4. Web UI calls the API and renders reports, status, and workflow controls

This keeps the Web UI as an orchestration layer instead of a second source of truth.

## UI-to-backend contract rule

UI routes must never imply backend capability.

Implications:

- navigation to a page must not depend on the backend route already existing
- a route such as `/settings` may exist before the backend supports full settings
  read/write behavior
- the UI must render capability state such as `READY`, `PARTIAL`, or
  `NOT_IMPLEMENTED` instead of exposing raw transport errors as the primary UX
- runtime UI flows must distinguish physical file damage from secondary metadata
  job symptoms and keep `UNKNOWN` and `SKIP` states visible
- canonical API prefixes stay stable under `/api`

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
- physical file integrity must be checked before metadata extraction failures are
  classified
- unknown runtime states remain unsafe until explicitly resolved
- future repair actions must be traceable in reports and journals
