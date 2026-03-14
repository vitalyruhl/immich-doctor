# Roadmap

Status markers:

- `[done]` completed
- `[active]` in progress
- `[next]` planned next
- `[later]` planned later
- `[hold]` intentionally deferred

## Phase 0 - Repository foundation

Status: `[active]`

Goal:

- create a beginner-friendly, modular Python repository
- keep CLI as the first interface
- reserve clean boundaries for future API, Web UI, and background jobs

Milestones:

- `[done]` initial package layout
- `[done]` safe MVP CLI commands
- `[done]` Docker and Compose scaffold
- `[done]` core documentation set
- `[done]` CI and lint workflows

## Phase 1 - Safe validation MVP

Status: `[active]`

In scope now:

- `runtime health check`
- `runtime validate`
- `storage paths check`
- `storage permissions check`
- `backup verify`
- `db health check`
- `db performance indexes check`
- environment-driven configuration
- structured text and JSON output
- validation-only PostgreSQL connectivity checks
- validation-only filesystem and tool checks
- Docker and Unraid-oriented runtime validation

Exit criteria:

- stable local CLI usage
- clear configuration docs
- basic test coverage for services and CLI smoke flow

## Phase 2 - Analysis workflows

Status: `[next]`

Goals:

- inventory Immich storage and database metadata
- generate analysis reports and manifests
- compare filesystem and metadata without changing data

## Phase 3 - Backup workflows

Status: `[next]`

Goals:

- define backup manifests
- validate backup strategy end to end
- add optional backup command orchestration
- journal all backup actions and outputs

## Phase 4 - Guided repair preparation

Status: `[later]`

Goals:

- report-only repair recommendations
- dry-run planning for repair actions
- quarantine-first action design
- no destructive delete as the first implementation

## Phase 5 - API and Web orchestration

Status: `[later]`

Goals:

- expose service layer through an API boundary
- add a lightweight Web UI for reports and orchestration
- keep UI as an orchestrator, not a separate logic layer

## Phase 6 - Automations and background jobs

Status: `[later]`

Goals:

- scheduled health and validation jobs
- recurring report generation
- notification hooks
- job journaling and operational history
