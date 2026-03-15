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
  - explicit notice that full restore is still not implemented

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
