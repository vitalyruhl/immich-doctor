# Repair workflow

Status: active foundation

## Implemented now

- mutating repair flows may persist a `RepairRun` under
  `data/manifests/repair/<repair_run_id>/`
- every persisted repair run stores:
  - `run.json`
  - `plan-token.json`
  - `journal.jsonl`
  - `quarantine-items.jsonl`
- a global quarantine index foundation is stored at `data/quarantine/index.jsonl`
- runtime metadata permission repair now records:
  - repair run identity
  - live-state plan token
  - `pre_repair_snapshot_id` once the pre-snapshot succeeds
  - journal entries for planned/applied/failed actions
  - undo payload with old/new mode values for chmod-based permission repair
- runtime metadata permission repair now requests one real files-only `pre_repair`
  snapshot before apply and aborts before mutation if snapshot creation fails
- targeted undo now exists for the already integrated runtime permission repair:
  - reads persisted old/new mode values from journal data
  - plans undo eligibility per journal entry
  - blocks automatic undo when file state drift or missing files make it unsafe
  - executes permission restore only for journal-backed chmod repairs
  - records undo execution in its own persisted `RepairRun`
- GUI visibility now exposes:
  - repair history based on persisted `RepairRun` records
  - per-run journal entries
  - apply preconditions and blocking reasons for the integrated runtime permission repair
  - linked `pre_repair_snapshot_id`
  - undo visibility from persisted journal data
  - backup-side actions to create a manual files backup or a standalone `pre_repair` snapshot
  - explicit notice that full restore is still not implemented

## Missing asset references

This workflow is defined narrowly and must not be widened silently.

Detection rule:

- scan `public.asset.originalPath` only
- a record qualifies as missing when the current runtime cannot access the file at that path on the local filesystem
- the backend keeps these states distinct: `present`, `missing_on_disk`, `permission_error`, `unreadable_path`, `unsupported`, `already_removed`
- `missing_on_disk` is the only status that is repairable
- empty or unresolved paths are reported as `unsupported`

Supported scope:

- scanned table: `public.asset`
- path field: `public.asset.originalPath`
- repair / restore tables:
  - `public.asset`
  - `public.asset_file`
  - `public.album_asset`
  - `public.asset_job_status`
- unknown foreign-key tables that point at `public.asset.id` block apply until they are modeled explicitly
- derivatives, previews, and thumbnails are not part of this workflow

Repair model:

- preview and apply are separate operations
- preview creates a repair run plus a plan token for drift protection
- apply must reuse that repair run and must refuse to proceed if the preview scope or live-state fingerprint drifted
- apply creates restore-point manifests before database mutation
- repair results are journaled and attributable to a repair run
- restore points are first-class JSON manifests, not ad-hoc logs

Restore behavior:

- restore point records are stored under `data/manifests/missing-asset-references/restore-points/`
- restore can target a single restore point, selected restore points, or all restore points
- restore-point deletion is separate from restore and requires explicit confirmation
- deleting a restore point removes reversible state for future restores
- restore cannot recreate the missing physical files; it only rehydrates database reference state captured in the manifest

Recovery limits:

- apply can restore the database references that were removed
- apply cannot recreate deleted source files, missing originals, or unsupported FK-backed records that were never captured
- if a record is already absent from the current scan scope, it is reported as `already_removed`
- if the schema contains unsupported asset references, the run stays blocked until the mapping is modeled safely

## Catalog-backed remediation findings

The catalog-backed consistency page now exposes two additional review-first
flows based on the latest committed storage snapshot.

Broken DB originals:

- scope: DB asset rows whose mapped `originalPath` is absent from the cached uploads snapshot
- classifications stay explicit:
  - `missing_confirmed`
  - `found_elsewhere`
  - `unresolved_search_error`
- relocation search is read-only and uses the cached storage inventory
- `found_elsewhere` stays inspect-only by default:
  - no auto-delete
  - no auto-rebind
  - expected path and found path must stay visible to the operator
- only `missing_confirmed` is eligible for explicit DB cleanup preview/apply
- DB cleanup apply reuses the existing repair-run, journal, and restore-metadata foundation

`.fuse_hidden*` storage orphans:

- scope: storage-only uploads files whose name starts with `.fuse_hidden`
- `.immich` is ignored explicitly and must never appear as a repair candidate
- classifications stay explicit:
  - `blocked_in_use`
  - `deletable_orphan`
  - `check_failed`
- in-use checks depend on runtime tooling and must report the real reason when unavailable
- only `deletable_orphan` is eligible for explicit delete preview/apply
- blocked or failed-check rows stay informational and do not expose destructive apply

Shared remediation rules:

- preview and apply remain separate
- selection may target a single row, selected rows, or all eligible rows in one class
- DB cleanup and `.fuse_hidden*` deletion stay separate flows and must not be mixed in one ambiguous handler
- scan time remains non-destructive

CLI and UI:

- CLI keeps explicit dry-run/apply semantics and does not use the UI checkbox gate
- UI repair actions require two confirmations before apply:
  - `I have read the warning`
  - `I created a backup`
- the warning must tell the operator to ensure both database and asset/storage backups exist before apply
- help text and docs must keep the same safety message even though the interaction model differs

## Safety rules

- inspect live state first
- create a plan token from that state
- validate the token again before apply
- persist the repair run and journal even when the run fails
- keep destructive cleanup out of this phase
- treat quarantine as the future first stop for file-destructive actions

## Not implemented yet

- generic undo for DB-delete repair flows
- automated rollback across all repair domains
- quarantine move/restore execution
- migration of all existing DB-mutating repair flows onto `RepairRun` + pre-snapshot gating

## Current limitation

The presence of a persisted repair journal still does not mean the whole system can
be rolled back automatically. This phase adds one real targeted undo path for
runtime permission repair, but broader repair domains still require later migration
or full restore handling.

The GUI currently shows undo visibility and snapshot linkage, but it does not
offer automated undo execution, quarantine moves, or restore actions yet.
