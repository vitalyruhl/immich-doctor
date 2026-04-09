# Persistent File Index Redesign

## Status

Proposed implementation roadmap for the next analysis and repair foundation.

## Problem statement

`immich-doctor` already has safe report, journal, backup-manifest, and repair-run
foundations, but its file-oriented checks still work as direct scan-and-compare
flows. The current implementation probes live filesystem paths while iterating
database batches in:

- `immich_doctor/runtime/integrity/service.py`
- `immich_doctor/consistency/service.py`
- `immich_doctor/consistency/missing_asset_service.py`

That approach is acceptable for small batches, but it is not a durable
foundation for very large Immich libraries. The repository also already treats
repair journals and manifests as first-class artifacts in:

- `immich_doctor/repair/store.py`
- `immich_doctor/repair/paths.py`
- `immich_doctor/services/repair_visibility_service.py`

The redesign must extend that persistence model to filesystem inventory work.

## Current pain points

1. Repeated filesystem work is too expensive.
   Current integrity and missing-asset flows rescan or reprobe paths from live
   storage instead of reusing a persisted inventory.

2. Reverse lookup is weak.
   The repository can detect database references whose paths are missing on
   disk, but it does not yet maintain a durable catalog of files present on disk
   and not referenced in PostgreSQL.

3. Later stages cannot build on earlier results.
   Zero-byte detection, orphan detection, stale derivative detection, and future
   deep integrity checks need reusable intermediate state.

4. Quarantine is only a foundation today.
   The current `QuarantineItem` model and `data/quarantine/index.jsonl`
   visibility are useful, but move/restore orchestration is not implemented and
   recovery should not depend on the doctor-internal database alone.

5. Container rebuild safety is not solved for inventory state.
   The repository already assumes mounted `reports`, `manifests`, `quarantine`,
   `logs`, and `tmp` paths, but scan state is not yet persisted in a durable,
   queryable catalog that survives rebuilds.

## Chosen architecture summary

Recommended target architecture:

- primary persistent store: SQLite on mounted storage
- durability mode: WAL plus `synchronous=FULL`
- catalog location: `MANIFESTS_PATH/catalog/`
- primary catalog file: `MANIFESTS_PATH/catalog/file-catalog.sqlite3`
- critical destructive action trail: append-only JSONL journal under
  `MANIFESTS_PATH/repair/`
- quarantine recovery: mirrored source-relative paths under `QUARANTINE_PATH`
  plus per-item sidecar manifests and optional batch manifests
- scan model: staged scan sessions, committed scan snapshots, resumable
  checkpoints, incremental revalidation, and later deep-check layers

Why this direction:

- SQLite gives indexed joins and resumable state without adding another service.
- Existing repo conventions already prefer mounted runtime artifacts over
  ephemeral container state.
- WAL mode provides crash resilience for the catalog.
- Sidecars and append-only journals keep quarantine recoverable even if the
  catalog is lost.

## Scope and non-goals

This roadmap plans a redesign. It does not implement the scanner yet.

Out of scope for this planning task:

- runtime code changes
- partial scanning implementation
- automatic destructive cleanup
- frontend lock-in to one API shape

## Target architecture

### Core layers

1. Storage root registry
   Maintain explicit scanned roots such as source library roots and derivative
   roots. All indexed files are stored relative to a known root.

2. Persistent file catalog
   Store current known file state, scan sessions, checkpoints, snapshots, and
   later integrity-layer results in SQLite.

3. DB correlation layer
   Import normalized Immich asset references into catalog tables, then perform
   indexed joins between DB references and file inventory without rewalking the
   filesystem.

4. Derivative intelligence layer
   Evaluate thumbnails, previews, encoded outputs, and other derivative files
   against known owning assets and explicit confidence rules.

5. Quarantine and operation journal
   Keep repair decisions auditable and reversible through repair runs, append-only
   journals, per-item sidecars, and mirrored path preservation.

### Storage layout

Recommended mounted layout:

```text
data/
  manifests/
    backup/
    repair/
      <repair-run-id>/
      operation-journal.jsonl
    catalog/
      file-catalog.sqlite3
      file-catalog.sqlite3-wal
      file-catalog.sqlite3-shm
      exports/
  quarantine/
    by-operation/
      YYYY/
        MM/
          DD/
            <operation-id>/
              <storage-root-slug>/
                <mirrored-relative-path>
                <file>.immich-doctor.json
              batch-manifest.json
```

### Data flow

1. Register storage roots.
2. Run or resume a scan session.
3. Persist checkpoints during traversal.
4. Commit a scan snapshot when the session completes.
5. Surface zero-byte files immediately from catalog rows.
6. Import DB references into correlation tables.
7. Join DB references against the committed catalog snapshot.
8. Produce reviewable candidates for missing-on-disk, on-disk-orphan, and
   derivative-leftover findings.
9. Move approved files into quarantine with sidecars and journal records.
10. Run optional deep integrity checks against catalog-selected targets only.

## Required design answers

### 1. Primary persistent store

Use SQLite as the primary local metadata store and keep it on mounted storage.
It matches the repo's local-artifact model, supports indexed queries, and avoids
running a second network database for doctor-owned metadata.

### 2. Crash safety

Crash safety comes from:

- SQLite WAL mode
- `synchronous=FULL`
- transactional session, snapshot, and checkpoint updates
- append-only journal records for destructive actions
- sidecar writes and batch manifests committed before a destructive action is
  considered complete

### 3. Metadata location

Persist metadata under `MANIFESTS_PATH/catalog/`, not inside the container image
filesystem. This aligns with the current mounted manifest model already used by
backup and repair persistence.

### 4. Scan resume model

Each scan session stores:

- root scope
- mode: full, incremental, deep-check
- status
- last completed directory token
- last emitted relative path
- counters and heartbeat

Interrupted sessions resume from the last durable checkpoint instead of
restarting from the filesystem root.

### 5. File identity

Authoritative logical identity:

- `storage_root_id`
- normalized `relative_path`

Supporting, non-authoritative hints:

- device/inode if available
- size
- modified timestamp
- optional future content hash

The unique key should be `(storage_root_id, relative_path)`. A surrogate `id`
still exists for internal joins and external references.

### 6. Phase 1 file metadata

Minimum Phase 1 metadata:

- `id`
- `storage_root_id`
- `relative_path`
- `file_name`
- `extension`
- `size_bytes`
- `created_at_fs` when available
- `modified_at_fs`
- `first_seen_at`
- `last_seen_at`
- `first_seen_snapshot_id`
- `last_seen_snapshot_id`
- `file_type_guess`
- `media_class_guess`
- `zero_byte_flag`
- optional `stat_device` and `stat_inode`
- hash state marker only, not required content hashing

### 7. Layering later checks

Later checks must attach their results to catalog rows and snapshots instead of
rewalking storage:

- DB correlation reads `file_record`
- derivative detection reads `file_record` plus `db_asset_reference`
- deep integrity reads `file_record` subsets chosen by scope, age, or previous
  status

### 8. Efficient orphan detection

Orphan detection must use indexed joins between:

- `db_asset_reference(storage_root_id, normalized_relative_path)`
- `file_record(storage_root_id, relative_path, last_seen_snapshot_id)`

Disk orphans are file rows with no matching DB reference.
DB-missing cases are DB references with no matching catalog row in the target
snapshot.

### 9. Separate DB-missing and disk-missing cases

Keep them as different result classes:

- DB missing on disk: DB row exists, catalog row absent in snapshot
- Disk orphan: catalog row exists, DB reference absent

This distinction matters for review, quarantine policy, and future restore logic.

### 10. Derivative leftovers

Model derivatives separately from primary asset files. A derivative candidate
needs:

- derivative type
- owning asset if known
- detection rule
- confidence
- safe-action class

Previews and thumbnails should not automatically inherit the same repair policy
as source files.

### 11. Quarantine representation

Quarantine stores the moved file under:

- operation bucket
- storage-root slug
- mirrored original relative path

Each quarantined item also gets a sidecar manifest adjacent to the file. An
optional batch manifest summarizes the operation bucket.

### 12. Quarantine recovery without internal DB

Recovery must remain possible without the catalog database. Required recovery
level:

- structure plus sidecars

Best-effort recovery level:

- directory structure alone

Highest-fidelity recovery level:

- structure plus sidecars plus append-only operation journal

### 13. Minimum sidecar metadata

Required per-item sidecar fields:

- `sidecar_version`
- `operation_id`
- `repair_run_id` when present
- `storage_root_id`
- `storage_root_slug`
- `original_relative_path`
- `original_absolute_path_at_move`
- `quarantine_relative_path`
- `moved_at`
- `reason_code`
- `correlation_class`
- `source_snapshot_id`
- optional `db_asset_id`
- optional `asset_file_id`
- `size_bytes`
- optional `modified_at_fs`
- optional checksum or deferred checksum marker

### 14. Auditability and reversibility

Critical actions must create:

- a repair-run record
- a global append-only journal entry
- a per-run journal entry
- a `quarantine_entry` row
- a sidecar manifest

Journal entries need status transitions such as `planned`, `copied`,
`verified`, `source_removed`, `restored`, and `failed`. Restore tooling should
replay journal state instead of inferring intent from file moves alone.

### 15. Migration story

The redesign should layer on top of current repair persistence, not replace it
in one step. Existing report and repair foundations stay valid while the
file-catalog subsystem is added beside them.

## Phase roadmap

### Phase 1 - Persistent file inventory foundation

Objective:

- create a durable, resumable file inventory

Core epics:

- storage-root registry and path normalization rules
- SQLite catalog bootstrap under `MANIFESTS_PATH/catalog/`
- scan session and checkpoint persistence
- committed scan snapshot generation
- Phase 1 file metadata capture
- zero-byte detection from inventory rows
- initial read-only CLI/API status surface

Exit criteria:

- interrupted scans resume safely
- a completed snapshot can be queried without touching the filesystem
- zero-byte reports come from catalog data
- catalog survives container rebuild when mounted storage persists

Validation milestones:

- kill-and-resume test during scan
- large-directory checkpoint test
- rebuild-container and reopen-catalog test
- zero-byte fixture test against committed snapshot

### Phase 2 - DB correlation layer

Objective:

- compare Immich DB references against catalog snapshots without repeating the
  full filesystem walk

Core epics:

- DB reference importer
- root-aware DB path normalization
- snapshot-based join queries
- explicit `db_missing_on_disk` and `disk_orphan` result classes
- conservative report outputs and review filters

Exit criteria:

- source-file missing-on-disk and disk-orphan detection work from persisted data
- repeated correlation runs do not require a new full inventory scan

Validation milestones:

- fixture with DB reference missing on disk
- fixture with disk orphan not referenced in DB
- normalization blocker test for paths outside registered roots

### Phase 3 - Derivative / leftover detection

Objective:

- detect stale previews, thumbnails, and encoded outputs

Core epics:

- derivative root classification
- derivative ownership rules
- candidate confidence scoring
- separation of safe candidates from uncertain candidates

Exit criteria:

- derivative candidates are reported with rule and confidence metadata
- unsafe candidates remain inspect-only

Validation milestones:

- stale thumbnail fixture
- encoded-output ownership test
- mixed-confidence reporting test

### Phase 4 - Quarantine safety model

Objective:

- move from quarantine visibility to quarantine recovery guarantees

Core epics:

- mirrored path layout under `QUARANTINE_PATH`
- per-item sidecars
- optional batch manifests
- append-only action journal
- restore planning and execution primitives
- cross-filesystem copy-verify-delete workflow

Exit criteria:

- quarantined items can be restored from structure plus sidecars without the
  catalog database
- journal and sidecar state is consistent after interrupted moves

Validation milestones:

- same-filesystem quarantine move test
- cross-filesystem copy-verify-delete test
- simulated DB-loss restore-candidate reconstruction test

### Phase 5 - Deep integrity scan

Objective:

- add optional expensive validation without collapsing back to raw repeated
  scans

Core epics:

- integrity check queue based on catalog snapshot
- resumable per-file deep check progress
- result layering in `integrity_check_result`
- incremental targeting rules by age, type, or previous failure status

Exit criteria:

- deep checks can resume after interruption
- previous scan snapshots remain reusable

Validation milestones:

- interrupt-and-resume media probe run
- incremental recheck of only stale or failed rows

### Phase 6 - UX / API / CLI exposure

Objective:

- expose status, resume, review, and apply flows without binding core logic to a
  single frontend

Core epics:

- scan status and resume endpoints
- snapshot listing and selection
- review surfaces for zero-byte, missing-on-disk, disk-orphan, and derivative
  candidates
- quarantine review and restore flows
- progress reporting suitable for CLI, API, and future UI

Exit criteria:

- users can inspect snapshot freshness, resume interrupted work, review
  candidates, and apply approved actions safely

## Dependency graph

```text
Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5 -> Phase 6
          Phase 2 ------^
Phase 1 ----------------^
Phase 4 -------------------------------> Phase 6
```

Interpretation:

- Phase 1 is the hard foundation.
- Phase 2 depends directly on Phase 1.
- Phase 3 depends on both Phase 1 inventory and Phase 2 correlation data.
- Phase 4 depends on at least Phase 1 and Phase 2, and should consume Phase 3
  confidence classes for derivative handling.
- Phase 5 depends on Phase 1 and should reuse later correlation outputs when
  filtering scope.
- Phase 6 can expose only what the earlier phases truly implement.

## Early shipments

Can ship early:

- Phase 1 inventory scan and resume support
- zero-byte reporting from catalog snapshots
- snapshot status visibility
- Phase 2 read-only correlation reports

Must wait for foundation completion:

- quarantine execution
- derivative cleanup actions
- deep integrity scheduling
- any destructive orphan handling

## Risks

### Path normalization risk

Immich paths may not cleanly map into one registered storage root. The
implementation must surface unresolved mappings as blockers instead of guessing.

### Cross-filesystem quarantine risk

If quarantine lives on another filesystem, `rename` is no longer atomic. The
workflow must switch to copy, fsync, verify, and only then remove the source.

### Catalog growth risk

A large library can produce millions of rows. The schema must avoid full
snapshot duplication where a current-state table plus snapshot references are
sufficient.

### Concurrent writer risk

SQLite is appropriate here, but scan and mutation orchestration must enforce one
writer or a strict writer queue.

### False-positive derivative risk

Derivative ownership rules are likely to be incomplete initially. Unsafe
confidence classes must remain inspect-only.

### Recovery gap risk

If sidecars are optional in implementation, recovery quality collapses. Sidecars
must be treated as mandatory for quarantine completion.

## Validation strategy

Per phase, validation must cover:

- crash interruption
- container rebuild persistence
- read-only rerun behavior
- safety downgrade behavior when path normalization is incomplete
- review-before-apply boundaries
- recovery from catalog loss for quarantined files

Recommended milestone boundaries:

1. Catalog bootstrap and single-root resumable scan
2. Multi-root inventory plus zero-byte reporting
3. DB correlation reports from snapshots
4. Derivative candidate classification
5. Quarantine move and restore safety
6. Deep integrity resumption and UX exposure

## Open questions

1. Which exact Immich storage roots should be first-class in configuration:
   originals only, or originals plus thumbs and encoded-video from the start?
2. Should the first implementation persist device/inode hints, or keep Phase 1
   strictly path-based for portability?
3. Is a dedicated catalog export command required in the first delivery, or is
   SQLite file backup plus snapshot export sufficient?
4. Should snapshot retention keep only current plus N committed generations, or
   retain all committed generations until manual pruning exists?
5. Which CLI domain should own the new scan surface: a future `analyze` domain
   or an extension of `consistency` and `runtime` commands?

## Recommended next implementation epic

Implement Phase 1 only:

- bootstrap `MANIFESTS_PATH/catalog/file-catalog.sqlite3`
- add storage-root registration and path normalization primitives
- add resumable inventory scan sessions with committed snapshots
- expose zero-byte reporting and scan status from persisted catalog data

