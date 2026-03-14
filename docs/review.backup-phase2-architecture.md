# Backup Architecture Review after Phase 2

## Scope reviewed

Reviewed sources:

- `docs/roadmap.backup-v1.md`
- `docs/architecture.md`
- `immich_doctor/backup/core`
- `immich_doctor/backup/files`
- `immich_doctor/backup/orchestration`
- `immich_doctor/backup/db`
- `immich_doctor/backup/metadata`
- `immich_doctor/backup/scheduler`
- `immich_doctor/backup/remote`

Validation checks executed during review:

- `uv run ruff check immich_doctor tests`
- `uv run pytest`
- `uv run python -m immich_doctor --help`

## Summary verdict

APPROVED FOR PHASE 3 WITH CONSTRAINTS

The current implementation stays within Phase 1 and Phase 2 boundaries and keeps
the CLI unchanged. Layer separation is mostly intact, rsync is still scoped to
file backups, and the current request/plan/execution split is good enough to
start `backup files`.

Phase 3 should proceed only if it preserves the current separation and corrects
the two main design pressures already visible:

- file backup code currently bypasses `BackupLocationResolver` and works directly
  with raw `Path` values
- file backup artifact metadata is still too thin for the mandatory manifest work

## Findings by category

### 1. Layer separation

- INFO: `backup/core` currently contains only shared contracts and models in
  `immich_doctor/backup/core/models.py` and `immich_doctor/backup/core/resolver.py`.
  No rsync-specific imports or subprocess logic leaked into core.
- INFO: rsync-specific logic is isolated under `immich_doctor/backup/files/rsync.py`
  and execution logic is isolated under `immich_doctor/backup/files/executor.py`.
- WARNING: `immich_doctor/backup/files/executor.py` creates destination directories
  directly via `plan.destination_path.parent.mkdir(...)`. This is acceptable for
  Phase 2, but it means infrastructure-side effects already live inside the file
  backup executor rather than behind a narrower infrastructure adapter.

### 2. Rsync placement

- INFO: rsync is currently only used as a file-backup strategy under
  `immich_doctor/backup/files`.
- INFO: `backup/core`, `backup/db`, `backup/metadata`, `backup/scheduler`, and
  `backup/remote` do not reference rsync.
- INFO: the repository has not accidentally made rsync the center of the overall
  backup architecture yet.

### 3. Request / plan / execution split

- INFO: `FileBackupRequest` in `immich_doctor/backup/files/models.py` separates
  request intent from execution.
- INFO: `FileBackupExecutionPlan` provides a clear planning artifact between
  request modeling and executor use.
- INFO: `VersionedDestinationBuilder` and `RsyncCommandBuilder` are separate from
  `LocalFileBackupExecutor`, which keeps planning and execution distinct.

### 4. Versioned destination design

- INFO: destination versioning is modeled in `VersionedDestinationBuilder`, not
  embedded into rsync command construction.
- INFO: the current timestamped path shape
  `<target_root>/<timestamp>/files/<source_label>` is aligned with the roadmap's
  versioning direction.
- WARNING: the builder currently derives version identity only from
  `FileBackupRequest.timestamp`, while `BackupContext.started_at` exists in core.
  Phase 3 should avoid introducing multiple competing timestamps for one backup set.

### 5. Command safety

- INFO: `RsyncCommandBuilder` constructs argument vectors as tuples and does not
  use shell concatenation.
- INFO: `LocalFileBackupExecutor` uses `subprocess.run(..., check=False, capture_output=True, text=True)`
  and does not use `shell=True`.
- INFO: destructive rsync flags are explicitly forbidden in
  `immich_doctor/backup/files/rsync.py`, including `--delete` and
  `--remove-source-files`.
- INFO: default rsync flags are explicit and reviewable:
  `--archive`, `--hard-links`, `--numeric-ids`.

### 6. Result model quality

- INFO: file backup execution returns `BackupResult` plus `BackupArtifact`, not a
  bare boolean or opaque subprocess result.
- WARNING: the produced `BackupArtifact.relative_path` is currently only the leaf
  directory name (`Path(plan.destination_path.name)`) instead of a path traceable
  from the eventual backup root. That is sufficient for Phase 2 tests, but it is
  too thin for manifest generation and later verification work.
- WARNING: `FileBackupExecutionError` currently drops stderr/stdout context from
  rsync failures. That is acceptable for a foundation phase, but Phase 3 should
  preserve failure evidence for reports and future manifests.

### 7. Manifest readiness

- INFO: `BackupManifest` already exists in core and `BackupResult` already has a
  `manifest` field, so the structural integration point is present.
- WARNING: current file backup outputs are only partially traceable because the
  result does not yet carry enough artifact path detail to describe the final
  backup tree cleanly in a manifest.
- INFO: there is no design choice yet that blocks manifest integration entirely,
  but Phase 3 should enrich artifact metadata instead of inventing a parallel
  file-backup result format.

### 8. Location / target model

- WARNING: `BackupLocationResolver` is defined in core but is not used by the
  file backup flow yet.
- WARNING: `FileBackupRequest` carries `source_path` and `target_root` as raw
  `Path` values, which means the current Phase 2 path flow partially bypasses the
  target abstraction already introduced in `BackupTarget`.
- INFO: this is still recoverable for Phase 3, but later local/docker/remote
  target growth should not continue by passing more raw paths deeper into the
  workflow.

### 9. Orchestration readiness

- INFO: `BackupOrchestrator` remains a placeholder and has not absorbed file
  backup implementation details.
- INFO: file backup code does not currently perform sequencing across multiple
  jobs, locking, or reporting orchestration.
- WARNING: `LocalFileBackupExecutor.execute()` already assembles a user-facing
  `BackupResult`. Phase 3 should preserve a boundary where orchestration owns
  multi-step report assembly and the executor stays focused on one file-copy unit.

### 10. Placeholder packages discipline

- INFO: `backup/db`, `backup/metadata`, `backup/scheduler`, and `backup/remote`
  remain placeholder-only.
- INFO: no early assumptions leaked into those packages beyond package purpose.

### 11. Roadmap compliance

- INFO: current code matches Phase 1 plus Phase 2 only.
- INFO: there is still no user-facing `backup files` command.
- INFO: there is no database backup logic, cron logic, remote logic, retention,
  restore, or verification expansion beyond the already existing `backup verify`
  readiness check.
- INFO: Phase 2 validation intent is covered by tests for deterministic
  destination structure, safe command generation, and a real local file tree in
  `tests/unit/test_backup_rsync_foundation.py`.

### 12. Phase 3 readiness

- INFO: the codebase is architecturally ready to begin Phase 3.
- WARNING: Phase 3 must preserve the current split:
  request -> plan -> rsync command -> executor -> structured result.
- WARNING: Phase 3 must not let the new `backup files` command talk directly to
  rsync or raw subprocess code from the CLI layer.

## Strengths

- Core backup contracts remain clean and technology-agnostic.
- Rsync is confined to the file backup area instead of leaking into the full
  backup domain.
- The request/plan/execution split is already visible and usable.
- Safety defaults are explicit and easy to review.
- Placeholder discipline is good; later phases still have room to grow without
  backtracking large assumptions.

## Risks

- `BackupLocationResolver` is currently unused, so Phase 3 could accidentally
  continue building around raw paths and weaken the target abstraction.
- File backup artifact metadata is still too shallow for the roadmap's mandatory
  manifest requirement.
- Executor-side result assembly may gradually absorb orchestration concerns if
  Phase 3 adds reporting details in the wrong layer.
- Multiple timestamp sources could drift if Phase 3 does not settle on one
  authoritative backup version identifier.

## Required constraints for Phase 3

- Keep `backup/core` free of rsync, subprocess, and filesystem execution details.
- Keep rsync-specific logic under `immich_doctor.backup.files`.
- Preserve the current request -> plan -> command -> executor split.
- Introduce `backup files` by adding a service/orchestration layer above the
  executor, not by exposing executor internals directly in CLI code.
- Make one timestamp source authoritative for one backup set; do not create a
  second versioning scheme.
- Enrich `BackupArtifact` usage so artifacts are traceable from the backup root
  and can feed the future manifest directly.
- Do not add destructive rsync flags or destination cleanup defaults.
- Do not bypass `BackupTarget` and `BackupLocationResolver` further; Phase 3
  should move closer to them, not farther away.
- Keep `db`, `metadata`, `scheduler`, and `remote` as non-implemented domains
  unless a placeholder-level type is strictly required for Phase 3 continuity.

## Recommended next step

Implement Phase 3 as a thin `backup files` application layer that:

1. accepts the future user-facing request
2. resolves the target through the backup domain abstractions
3. creates one file backup plan
4. executes it through the local rsync executor
5. returns a `BackupResult` with artifact metadata rich enough for manifest work

Do not add retention, remote transport, DB backup, metadata capture, or backup-all
orchestration in the same step.
