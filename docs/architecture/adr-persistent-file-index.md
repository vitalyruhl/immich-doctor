# ADR: Persistent File Index Architecture

## Status

Accepted for the redesign roadmap.

## Context

`immich-doctor` already persists backup snapshots, repair runs, and repair
journals under mounted runtime paths. Relevant current paths and modules:

- `immich_doctor/repair/store.py`
- `immich_doctor/repair/paths.py`
- `immich_doctor/consistency/missing_asset_restore_point_store.py`
- `data/manifests/`
- `data/quarantine/`

File-oriented validation still operates as direct database-led path probing in:

- `immich_doctor/runtime/integrity/service.py`
- `immich_doctor/consistency/service.py`
- `immich_doctor/consistency/missing_asset_service.py`

The project needs a durable, resumable catalog for large libraries and later
multi-stage analysis.

## Decision

Use a hybrid persistence model:

- SQLite is the primary doctor-owned metadata catalog.
- SQLite lives on mounted storage under `MANIFESTS_PATH/catalog/`.
- SQLite runs in WAL mode with `synchronous=FULL`.
- Filesystem sidecars remain mandatory for quarantined items.
- Append-only JSONL journals remain mandatory for critical destructive actions.

Primary catalog location:

```text
MANIFESTS_PATH/catalog/file-catalog.sqlite3
```

Related runtime artifacts:

- `MANIFESTS_PATH/catalog/file-catalog.sqlite3-wal`
- `MANIFESTS_PATH/catalog/file-catalog.sqlite3-shm`
- `MANIFESTS_PATH/repair/operation-journal.jsonl`
- `QUARANTINE_PATH/by-operation/...`

## Options considered

### Option 1: JSON/YAML files only

Advantages:

- simple to inspect manually
- fits current manifest style
- no embedded database dependency

Rejected as primary store because:

- indexed reverse lookups across millions of files are poor
- resumable scan checkpoints become fragile and slow
- orphan detection and correlation need relational joins, not repeated full-file
  deserialization
- concurrent read/write safety is weak compared with a transactional catalog
- YAML adds parsing overhead without solving queryability

JSON or YAML remains appropriate for:

- human-readable exports
- sidecars
- append-only action journals
- interoperability artifacts

### Option 2: SQLite as primary local metadata store

Advantages:

- embedded, no additional service to run
- transactional and queryable
- strong fit for mounted local state
- appropriate for a mostly single-writer tool
- easy backup story because the DB is a local file set

Tradeoffs:

- needs writer discipline
- large catalogs require careful schema and index choices
- WAL files must live on the same durable mounted volume

Accepted as the primary store.

### Option 3: Separate PostgreSQL doctor metadata database

Advantages:

- familiar relational model
- strong concurrency story
- larger multi-user ceiling

Rejected because:

- introduces a second service to provision, secure, back up, and monitor
- contradicts the current repo's local artifact model
- couples recovery of doctor metadata to an additional database dependency
- over-scopes the first redesign for a tool that primarily runs as a local
  maintenance container

The redesign still reads Immich PostgreSQL as a source of truth for application
references, but does not use PostgreSQL as the doctor-owned catalog.

### Option 4: Hybrid model

Advantages:

- combines SQLite queryability with filesystem-native recovery artifacts
- protects quarantine recovery from catalog loss
- preserves auditability outside the embedded DB

Accepted.

## Why the hybrid model is final

The tool has two different durability needs:

- fast indexed metadata queries for scan, correlation, and integrity workflows
- disaster-recovery-friendly artifacts for destructive actions

SQLite solves the first problem well. Sidecars and append-only journals solve
the second.

## Durability and crash safety mode

SQLite must be configured with at least:

- `PRAGMA journal_mode=WAL;`
- `PRAGMA synchronous=FULL;`
- `PRAGMA foreign_keys=ON;`
- `PRAGMA busy_timeout` set to a conservative non-zero value

Operational rules:

- keep one active catalog writer at a time
- checkpoint intentionally, not on every write
- treat a committed scan snapshot as the boundary for downstream reads
- treat quarantine completion as requiring both catalog and filesystem artifacts

## Storage location decision

The primary catalog belongs under mounted manifests storage:

```text
MANIFESTS_PATH/catalog/
```

Reasoning:

- the repo already treats `data/manifests/` as durable runtime state
- this avoids adding another top-level operational path before implementation
- container rebuilds should not remove catalog state if the manifests mount persists

Quarantine remains on its own mounted root:

```text
QUARANTINE_PATH/
```

## Indexing and querying expectations

The catalog must support:

- lookup by `(storage_root_id, relative_path)`
- snapshot membership and recency queries
- joins from DB references to catalog rows
- joins from catalog rows to quarantine entries
- incremental deep-check targeting by prior result or age

This requires relational indexes. JSON/YAML-only storage is not adequate as the
primary substrate for these operations.

## Sidecar decision

Sidecars still exist, but not as the primary inventory store.

Sidecars are required for:

- quarantine restore recovery if SQLite is lost
- manual inspection of a quarantined file in isolation
- portable evidence of why a file was moved

Sidecars are not required for:

- normal inventory and correlation queries
- resume checkpoints
- snapshot joins

## Backup and export considerations

Backup/export expectations:

- the SQLite catalog files can be backed up as part of mounted manifest storage
- future export commands may emit JSON snapshot summaries for human review
- quarantine recovery must not depend on SQLite backup success
- append-only journals should remain readable without the catalog

## Consequences

Positive:

- staged analysis becomes practical
- repeated scans can be reduced
- catalog survives container rebuilds
- destructive actions remain auditable and recoverable

Negative:

- the tool must manage schema migrations for a real local database
- write ordering between SQLite, journals, and sidecars must be explicit
- implementation complexity rises compared with flat manifests

## Follow-up decisions required during implementation

- exact storage-root configuration model
- snapshot retention policy
- lock strategy for single-writer enforcement
- export and compaction policy for large catalogs

