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

- full restore orchestration
- automated rollback
- quarantine move/restore execution
- migration of all existing DB-mutating repair flows onto `RepairRun` + pre-snapshot gating

## Current limitation

The presence of a persisted repair journal does not yet mean the whole system can
be rolled back automatically. This phase provides the mandatory persistence and
drift-protection primitives so later repair migrations can become reversible.

The GUI currently shows undo visibility and snapshot linkage, but it does not
offer automated undo execution, quarantine moves, or restore actions yet.
