# Backup Roadmap V1 — immich-doctor

Status: DRAFT  
Scope: Backup only (NO restore in V1)  
Branch root: `feature/backup`

---

# Vision

Backup V1 shall provide a reproducible, transportable backup set that allows building a separate test/repair Immich instance later.

Backup must include:
- Database backup
- Asset files
- Metadata & runtime context
- Manifest describing backup state

Backup V1 is not responsible for restore.

---

# Architectural Principles

- Doctor orchestrates backups
- Immich native DB backup preferred over custom dump
- rsync is the base for file backups
- All backups must be versioned
- Every backup must produce a manifest
- Backup must be deterministic and reproducible
- Backup must be safe (no destructive default behaviour)
- Backup must be automatable
- Backup must be inspectable
- Backup must support later validation

---

# Branch Strategy

Main feature branch:
feature/backup

Work branches (sequential):
- chore/backup-foundation
- chore/backup-rsync-foundation
- chore/backup-files
- chore/backup-db
- chore/backup-metadata
- chore/backup-all
- chore/backup-path
- chore/backup-versioning
- chore/backup-cron
- chore/backup-remote
- chore/backup-verify
- chore/backup-docs

Rule:
- One logical step per branch
- Must be validated before next step
- Merge → delete branch → next

---

# Phase 1 — Backup Foundation

Goal:
Introduce backup domain architecture without full functionality.

Create structure:
immich_doctor/backup/
  core/
  db/
  files/
  metadata/
  orchestration/
  scheduler/
  remote/

Introduce core concepts:
- BackupContext
- BackupJob
- BackupTarget
- BackupArtifact
- BackupManifest
- BackupResult
- BackupLocationResolver

Validation gate:
- CLI still works
- Tests still pass
- No behaviour regression

---

# Phase 2 — Rsync Foundation

Goal:
Introduce rsync-based file backup engine.

Scope:
- Local source → local target
- Versioned destination folder
- No destructive default flags

Validation gate:
- Real file tree test
- Correct destination structure
- rsync invocation stable

---

# Phase 3 — backup files

CLI:
backup files

Features:
- rsync based
- versioned output
- manifest generation

Validation gate:
- Reproducible backup
- Manifest exists
- Output understandable

---

# Phase 4 — backup db (via Immich native backup)

Doctor must:
- trigger or detect Immich DB backup artifact
- include artifact in backup set
- version artifact

Validation gate:
- DB backup exists
- Included in manifest
- Deterministic naming

---

# Phase 5 — backup metadata

Metadata includes:
- Immich version
- Doctor version
- runtime hints
- configuration snapshot
- asset statistics

Validation gate:
- Metadata useful
- No secrets leaked

---

# Phase 6 — backup all

CLI:
backup all

Execution order:
1. db
2. metadata
3. files

Output:
/backups/immich/<timestamp>/
  manifest.json
  db/
  files/
  metadata/

Validation gate:
- Full backup created
- Manifest complete

---

# Phase 7 — Path Override

CLI option:
--path <target>

Validation gate:
- Works across environments
- Deterministic behaviour

---

# Phase 8 — Versioning & Retention

Default:
Timestamp-based versioning

Future:
--keep N

Validation gate:
- Multiple runs produce separate backups

---

# Phase 9 — Cron Integration

CLI:
backup cron add
backup cron enable
backup cron disable

Validation gate:
- Cron file correct
- Enable/disable works

---

# Phase 10 — Remote Targets

Priority:
1. rsync over SSH
2. mounted network paths

Validation gate:
- Remote transfer reproducible

---

# Phase 11 — Backup Verification

CLI:
backup verify

Checks:
- manifest presence
- artifact presence
- gzip/tar integrity

Validation gate:
- Corrupt backup detected
- Valid backup confirmed

---

# Critical Requirements

- Manifest mandatory
- Locking required
- No secret leakage
- Deterministic exit codes

---

# Out of Scope (V1)

- Restore
- Encryption
- Incremental DB backup
- Advanced retention
