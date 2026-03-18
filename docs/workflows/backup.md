# Backup workflow

Status: active

## Implemented now

- `backup verify`
  - validates current backup target-readiness and configured required tools
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
  - target validation state
  - manual files-only backup execution for local plus safe-subset SSH/rsync targets
- GUI also shows quarantine foundation status separately from snapshot coverage

Manual backup target behavior now includes:

- local folder targets with absolute path validation
- SSH and rsync targets with explicit host key strategy and secret-reference-based private key handling
- SMB targets as configuration + validation + mount-planning only
- persisted target validation summary and last successful backup metadata
- explicit restore-readiness signaling of `not_implemented`

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
- restore readiness: `not_implemented`, `partial`
- snapshot basic validity: `valid`, `invalid`

Meaning rules:

- `completed` means the current implementation finished; it does not mean verified, complete for disaster recovery, or restore-ready
- target validation always means only the currently implemented checks
- `files_only` must always be shown to humans as `files-only`
- `snapshot` means the persisted backup record plus its manifest metadata, not an automatic full restore point
- `manifest` means the persisted JSON metadata record, not artifact-content verification
- `stale` means a cached size estimate is older than the freshness window

Current verification semantics stay conservative:

- `transport_success_only` means the transfer process reported success
- `destination_exists` adds a destination path existence check only
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
- executable GUI backup coverage is still files-only, even for `pre_repair`
- productive SMB backup execution is still intentionally disabled
- password-based SSH execution is still intentionally unsupported
- snapshot cards report manifest structure only and must not be read as artifact verification
- restore is simulation-only and targeted undo is not yet exposed as a GUI action
