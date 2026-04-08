# Quarantine Recovery Model

## Purpose

This document defines how quarantined files remain recoverable even if the
doctor-internal SQLite catalog is lost.

## Current repository baseline

Today the repository has a quarantine foundation but not a full quarantine
workflow:

- `QuarantineItem` exists in `immich_doctor/repair/models.py`
- `RepairJournalStore` persists quarantine index lines in
  `immich_doctor/repair/store.py`
- quarantine visibility is exposed by
  `immich_doctor/services/repair_visibility_service.py`
- the current global file is `data/quarantine/index.jsonl`

That is a useful starting point, but it is not enough for production-grade
recovery on its own.

## Recovery requirements

1. Non-destructive by default.
2. Review before apply.
3. Restore should remain possible if the catalog database is lost.
4. Restoring a quarantined file should preserve the original source-relative
   structure.
5. Audit trails must show why a move happened and what was restored later.

## Required recovery guarantees

Supported recovery tiers:

- required: `structure + sidecars`
- best effort: `structure alone`
- highest fidelity: `structure + sidecars + journal`

Interpretation:

- directory structure alone should let an operator infer the likely original
  relative path
- sidecars are required for supported recovery because they carry operation and
  classification metadata
- the append-only journal gives the strongest audit trail and replay ordering

## Quarantine layout decision

Recommended on-disk layout:

```text
QUARANTINE_PATH/
  by-operation/
    YYYY/
      MM/
        DD/
          <operation-id>/
            <storage-root-slug>/
              <original-relative-path>
              <filename>.immich-doctor.json
            batch-manifest.json
```

Example:

```text
data/quarantine/by-operation/2026/04/08/op-01ABCDEF/upload/library/admin/2024/01/img.jpg
data/quarantine/by-operation/2026/04/08/op-01ABCDEF/upload/library/admin/2024/01/img.jpg.immich-doctor.json
```

Design implications:

- the subtree under `<storage-root-slug>/` mirrors the original relative path
- recovery does not need SQLite to reconstruct the original destination path
- the operation bucket groups files that moved together

## Why mirrored structure matters

If the catalog is lost, the operator can still infer:

- which configured storage root the file came from
- the original relative path under that root

This is the minimum acceptable manual-recovery story. The sidecar adds the rest
of the safety-critical metadata.

## Sidecar design

Per-item sidecars are mandatory.

Recommended file naming:

```text
<quarantined-file-name>.immich-doctor.json
```

Required fields:

- `sidecar_version`
- `operation_id`
- `repair_run_id`
- `storage_root_id`
- `storage_root_slug`
- `original_relative_path`
- `original_absolute_path_at_move`
- `quarantine_relative_path`
- `quarantine_absolute_path`
- `moved_at`
- `reason_code`
- `correlation_class`
- `source_snapshot_id`
- optional `db_asset_id`
- optional `asset_file_id`
- `size_bytes`
- optional `modified_at_fs`
- optional `checksum`
- optional `checksum_algorithm`

Useful optional fields:

- `detected_file_type`
- `confidence`
- `source_scan_session_id`
- `notes`

## Batch manifest design

`batch-manifest.json` is optional but recommended. It summarizes the operation
bucket for fast review and disaster triage.

Candidate fields:

- `operation_id`
- `repair_run_id`
- `created_at`
- `item_count`
- `reason_summary`
- `source_snapshot_id`
- `entries`
  Store only compact references, not full duplicated sidecar payloads

## Append-only journal

The quarantine design also requires an append-only journal outside SQLite.

Recommended location:

```text
MANIFESTS_PATH/repair/operation-journal.jsonl
```

Each event should record:

- `event_id`
- `operation_id`
- `repair_run_id`
- `event_type`
- `subject_path`
- `source_relative_path`
- `quarantine_relative_path`
- `timestamp`
- `result`
- `details`

Recommended event progression:

1. `planned`
2. `sidecar_prepared`
3. `move_started` or `copy_started`
4. `copy_verified` when cross-filesystem
5. `source_removed`
6. `completed`
7. `restore_started`
8. `restore_completed`
9. `failed`

## Same-filesystem versus cross-filesystem handling

### Same filesystem

Preferred path:

- create sidecar payload
- stage journal `planned`
- move via atomic rename when safe
- fsync sidecar and manifest
- append `completed`

### Cross-filesystem

Required path:

- create sidecar payload
- append `copy_started`
- copy file to quarantine
- fsync destination
- verify size and optional checksum
- write sidecar
- remove source only after verification
- append `source_removed` and `completed`

Cross-filesystem moves must never behave like blind `move` operations.

## Restore model

Restore planning should rely on:

- sidecar metadata for original destination
- journal state for ordering and prior restore attempts
- current source-path safety checks

Restore execution should:

1. verify target path and parent safety
2. refuse overwrite by default
3. support dry-run planning
4. record restore journal events
5. mark sidecar or catalog state as restored

## Failure handling

If an interruption happens:

- the journal should show the last completed stage
- the sidecar should still identify intended source and quarantine paths
- restore tooling should classify the item as partial, not silently complete

Examples:

- copied but not verified
- copied and verified but source not removed
- restored file present but journal not finalized

## Compatibility with current models

Current compatibility guidance:

- keep `RepairRun` and per-run `journal.jsonl`
- evolve `QuarantineItem` to point at mirrored paths and sidecars
- keep `data/quarantine/index.jsonl` only as a convenience index, not as the
  required recovery artifact

The source of truth for recoverability becomes:

- quarantined file path
- adjacent sidecar
- append-only journal

## Minimum implementation checklist

1. Mirrored path preservation under `QUARANTINE_PATH`
2. Mandatory per-item sidecar
3. Append-only external journal
4. Dry-run restore planning
5. Same-filesystem and cross-filesystem execution paths
6. Recovery tooling that can reconstruct restore candidates without SQLite

