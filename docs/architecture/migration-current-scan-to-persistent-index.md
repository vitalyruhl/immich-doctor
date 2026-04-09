# Migration From Current Scan Flows To Persistent Index

## Purpose

This document defines how the repository can move from direct path-probing
workflows to a persistent inventory architecture without breaking current safety
foundations.

## Current implementation baseline

Current direct scan or probe behavior exists in:

- `immich_doctor/runtime/integrity/service.py`
- `immich_doctor/consistency/service.py`
- `immich_doctor/consistency/missing_asset_service.py`

Current persistence foundations already in use:

- repair manifests and journals in `immich_doctor/repair/store.py`
- repair-path layout in `immich_doctor/repair/paths.py`
- missing-asset restore point manifests in
  `immich_doctor/consistency/missing_asset_restore_point_store.py`
- backup snapshot manifests in `data/manifests/backup/snapshots/`
- quarantine foundation visibility in `data/quarantine/`

## Migration principles

1. Do not break existing repair-run persistence.
2. Add the new catalog beside current flows first.
3. Keep read-only reporting available during transition.
4. Do not make destructive actions depend exclusively on unfinished catalog work.
5. Preserve CLI, API, and UI compatibility where possible.

## Target module direction

Recommended new implementation area:

```text
immich_doctor/catalog/
```

Likely future responsibilities:

- SQLite bootstrap and migrations
- storage-root registry
- inventory scanning
- checkpoint persistence
- snapshot commit logic
- DB reference import
- catalog-backed queries

Current modules that should become consumers instead of primary scanners:

- `immich_doctor/runtime/integrity/service.py`
- `immich_doctor/consistency/service.py`
- `immich_doctor/consistency/missing_asset_service.py`

Current modules that should remain compatible and be extended:

- `immich_doctor/repair/*`
- `immich_doctor/reports/*`
- `immich_doctor/api/*`

## Migration phases

### Phase A - Catalog bootstrap

Changes:

- add SQLite catalog bootstrap under `MANIFESTS_PATH/catalog/`
- add schema migrations
- add storage-root registration and normalization logic

No behavior change yet:

- existing integrity and consistency commands still use current direct logic

### Phase B - Inventory scan introduction

Changes:

- implement resumable inventory scan
- persist `scan_session`, checkpoints, snapshots, and `file_record`
- expose read-only scan status

Compatibility:

- current commands continue to function
- new catalog scan is additive

### Phase C - Zero-byte reporting cutover

Changes:

- move zero-byte reporting to catalog-backed queries

Compatibility:

- direct path probes may remain as a fallback only where catalog coverage is absent

### Phase D - DB correlation cutover

Changes:

- import DB references into catalog tables
- move missing-on-disk and disk-orphan reporting to snapshot joins

Compatibility:

- keep current category names where possible
- preserve current report shapes unless a change is explicitly versioned

### Phase E - Derivative detection introduction

Changes:

- add derivative roots and candidate modeling
- add read-only stale-derivative reporting

Compatibility:

- current inspect-only derivative path checks can remain until the new layer is proven

### Phase F - Quarantine workflow cutover

Changes:

- replace quarantine foundation-only visibility with real mirrored quarantine
  entries, sidecars, and append-only journals

Compatibility:

- keep `RepairRun` and per-run journals
- treat old `index.jsonl` as a compatibility index, not the recovery source of truth

### Phase G - Deep integrity cutover

Changes:

- store layered deep-check results in the catalog
- stop using ad-hoc full rescans as the primary deep-integrity workflow

## Data migration strategy

The first catalog release should not attempt to convert every historical manifest
into catalog rows.

Recommended strategy:

1. Start catalog history from the first committed inventory snapshot.
2. Keep existing repair-run and backup manifest history untouched.
3. Import historical quarantine entries only if they have enough metadata to map
   safely into the new model.

Reasoning:

- repair history is already useful as file-based evidence
- forced backfill adds risk and limited immediate value
- inventory accuracy matters more than synthetic reconstruction of old scans

## Feature-flag and rollout strategy

Recommended rollout:

1. Introduce the catalog behind an explicit feature gate or opt-in command.
2. Keep current integrity and consistency flows as fallback during Phase 1 and
   early Phase 2.
3. Switch read-only reports first.
4. Switch quarantine and destructive flows only after recovery validation passes.

## Validation checkpoints

Before cutting over any existing behavior, verify:

- catalog survives container restart and rebuild
- interrupted scan resumes correctly
- catalog-backed result matches current direct-scan result on the same fixture
- path-normalization blockers are explicit
- quarantine recovery works without SQLite

## Backward compatibility expectations

Should remain stable:

- repair-run manifests under `data/manifests/repair/`
- backup snapshot manifests under `data/manifests/backup/snapshots/`
- existing dry-run-before-apply behavior
- existing API/UI expectation that unimplemented capabilities must not be implied

May evolve:

- internal source of truth for integrity and consistency reports
- quarantine index format
- exact command surfaces for scan status and resume

## Recommended first implementation epic

Do not refactor current integrity or consistency services first.

Start with:

- `immich_doctor/catalog/` foundation
- SQLite bootstrap and migrations
- storage-root registry
- resumable inventory scan
- committed snapshot query surface

Only after that should existing services be adapted to consume the catalog.

