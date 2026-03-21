# Backup workflow

Status: active

## Current scope / non-goals / safety limits

- current scope: non-blocking backup size collection, target validation, asset-aware path-like check/sync/verify plus selective restore, conservative files-only manual execution for safe-subset SSH/rsync targets, persisted snapshot records, and snapshot manifest visibility
- non-goals: productive SMB system-mount execution, full bidirectional sync, automatic overwrite on mismatch, DB-inclusive backup coverage, metadata backup coverage, aggressive parallel rsync by default
- safety limits: `completed` does not mean globally deep-verified or disaster-recovery-ready, target validation covers only currently implemented checks, and `stale` size-estimate data must be treated as aged cache data or as a pre-restart previous result

## Implemented now

- `backup verify`
  - validates current backup target-readiness and configured required tools
  - validates persisted backup snapshot manifest structure when manifests exist
- `backup files`
  - remains available as one legacy local, versioned file backup from the configured Immich library root
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
  - a persisted internal verification flag that is not exposed as end-to-end integrity proof
  - optional `repair_run_id`
- repair safety foundation now reserves nullable `pre_repair_snapshot_id` and
  `post_repair_snapshot_id` fields on persisted `RepairRun` records
- integrated runtime repair apply now requests a real `pre_repair` snapshot and
  stores its `snapshot_id` on the `RepairRun`
- `backup restore simulate`
  - selects a repair-linked or manually requested snapshot deterministically
  - reports restore blockers such as missing DB artifact or insufficient coverage
  - generates environment-aware manual restore instructions
- GUI visibility now exposes persisted snapshot records with manifest metadata:
  - `snapshot_id`
  - `created_at`
  - `kind`
  - `coverage`
  - optional `repair_run_id`
  - verification/basic validity signal
- GUI now also exposes real backup execution actions for:
  - explicit manual target selection
  - non-blocking backup size collection
  - automatic source-size recalculation on doctor startup
  - manual source-size refresh with explicit queued/running/stale status
  - target validation state
  - path-like check plus sync-missing execution with asset comparison and review samples
  - path-like representative test copy with real copy plus SHA-256 verification
  - path-like selective restore/overwrite from backup to source storage after explicit review
  - conservative files-only execution for safe-subset SSH/rsync targets
- GUI also shows quarantine foundation status separately from snapshot coverage

Primary execution ownership now sits with the target-based manual backup flow:

- `ManualBackupExecutionService` is the canonical backup execution orchestrator
- prepared target access and destination semantics are explicit before dispatch
- `backup files` remains legacy and must not grow into a competing primary path

Manual backup target behavior now includes:

- local folder targets with absolute path validation
- local hidden workflow roots under `_immich-doctor/current` and `_immich-doctor/tests`
- path-like staged comparison: existence -> size -> mtime -> SHA-256 only when needed
- path-like mismatch/conflict visibility with source/backup size, timestamp, and hash details where available
- path-like folder-level heuristics for file-count and total-size drift
- path-like restore overwrite protection via quarantine-first move before replacement
- SSH and rsync targets with shared remote auth modelling, connection-string parsing, known-host mode handling, and secret-reference-based key/password storage
- SSH validation now reports doctor-runtime-specific causes such as missing agent socket, known-hosts path preparation, unwritable remote destinations, and SSH probe timeout
- SSH and rsync validation now separate connectivity/path success from execution readiness; local `rsync` is required in the doctor runtime before files-only remote execution is treated as runnable
- SMB targets with executable `pre_mounted_path` semantics and `system_mount` planning rules plus authentication requirements for system-mount mode only
- persisted target validation summary and last successful backup metadata
- explicit restore-readiness signaling of `partial` for path-like selective restore and `not_implemented` for remote targets

Manual execution reporting now includes:

- source scope
- target type
- bytes planned when a fresh source size estimate exists
- bytes transferred when rsync stats are available
- file counts when available
- duration
- warnings
- verification level
- version/snapshot identifier

## Canonical terminology

Machine values stay stable and UI/doc labels should mirror them conservatively:

- job states: `pending`, `running`, `partial`, `completed`, `failed`, `unsupported`, `cancel_requested`, `canceled`
- snapshot coverage: `files_only`, `db_only`, `paired`
- verification levels: `none`, `transport_success_only`, `destination_exists`, `basic_manifest_verified`
- local sync verification may also report `copied_files_sha256` for copied items
- restore readiness: `not_implemented`, `partial`
- snapshot basic validity: `valid`, `invalid`
- asset comparison statuses: `pending`, `identical`, `missing_in_backup`, `mismatch`, `conflict`, `restore_candidate`, `restored`, `skipped`, `failed`

Meaning rules:

- `completed` means the current implementation finished; it does not mean verified, complete for disaster recovery, or restore-ready
- `copied_files_sha256` means copied items were hash-verified after copy; it is not a claim that every target file was globally re-hashed
- target validation always means only the currently implemented checks
- `files_only` must always be shown to humans as `files-only`
- `snapshot` means the persisted backup record plus its manifest metadata, not an automatic full restore point
- `manifest` means the persisted JSON metadata record, not artifact-content verification
- `stale` means a cached size estimate is older than the freshness window or predates the current doctor restart
- a source size estimate from before the current doctor restart must also be treated as `stale`, even if its cache age would otherwise still be fresh

Current verification semantics stay conservative:

- `transport_success_only` means the transfer process reported success
- `destination_exists` adds a destination path existence check only
- local `check/sync` hashes copied items and suspicious same-size pairs only; it does not claim a full deep hash over the whole backup tree
- snapshot visibility reports manifest structure separately from artifact-content verification
- no current backup result claims full restore-readiness or end-to-end integrity proof

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
- stronger remote host verification support beyond current safe subset
- pre-repair and post-repair snapshot integration for mutating repair flows
- paired DB + file snapshot creation

## Still out of scope

- broad automated full restore execution is still not implemented
- destructive cleanup defaults
- scheduler / cron

Current UI limitation:

- snapshots are visible and linkable from repair history
- local asset-aware restore is still limited to filesystem copy-back only; no DB repair or DB rollback is implied
- executable GUI backup coverage is still files-only, even for `pre_repair`
- SMB `system_mount` execution is still intentionally disabled
- SMB `system_mount` remains planned only; pre-mounted path is the only currently supported SMB-style execution mode
- password-based SSH/rsync execution is still intentionally unsupported
- snapshot cards report manifest structure only and must not be read as artifact verification
- remote asset preview and selective restore are intentionally unsupported
- broad full restore remains simulation-only and targeted undo is not yet exposed as a GUI action
