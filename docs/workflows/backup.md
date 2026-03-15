# Backup workflow

Status: active

## Implemented now

- `backup verify`
  - validates backup target readiness and configured required tools
  - validates persisted backup snapshot manifest structure when manifests exist
- `backup files`
  - runs one local, versioned file backup from the configured Immich library root
  - uses the backup application layer, not direct CLI subprocess calls
  - uses non-destructive rsync defaults
  - persists one backup snapshot manifest per successful run
- persisted `BackupSnapshot` metadata now includes:
  - `snapshot_id`
  - `kind`
  - `coverage`
  - `source_fingerprint`
  - `file_artifacts`
  - nullable `db_artifact`
  - `manifest_path`
  - `verified`
  - optional `repair_run_id`
- repair safety foundation now reserves nullable `pre_repair_snapshot_id` and
  `post_repair_snapshot_id` fields on persisted `RepairRun` records
- integrated runtime repair apply now requests a real `pre_repair` snapshot and
  stores its `snapshot_id` on the `RepairRun`
- GUI visibility now exposes persisted snapshot manifests with:
  - `snapshot_id`
  - `created_at`
  - `kind`
  - `coverage`
  - optional `repair_run_id`
  - verification/basic validity signal
- GUI also shows quarantine foundation status separately from snapshot coverage

## Snapshot coverage semantics

- `files_only`: file backup artifacts exist, DB artifact is absent and that gap is explicit
- `db_only`: reserved for later DB-only snapshot phases
- `paired`: reserved for later DB + file snapshot phases

## Snapshot kinds

- `manual`: default for current `backup files`
- `pre_repair`: created before an integrated mutating repair apply run
- `post_repair`: reserved for later stabilization snapshots
- `periodic`: reserved for later scheduled backup flows

## Planned next

- DB backup inclusion
- metadata capture
- backup-all orchestration
- retention
- remote targets
- pre-repair and post-repair snapshot integration for mutating repair flows
- paired DB + file snapshot creation

## Still out of scope

- restore orchestration is still not implemented, but remains a required later safety layer
- destructive cleanup defaults
- scheduler / cron

Current UI limitation:

- snapshots are visible and linkable from repair history
- current executable snapshot creation is still files-only
- restore and targeted undo are not yet executable through GUI or API
