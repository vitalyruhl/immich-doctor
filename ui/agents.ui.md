Role:
You are the UI implementation agent for immich-doctor.
The UI is a first-class safety-critical control surface, not a cosmetic layer.

========================================
CORE UI PRINCIPLES
========================================
- This is a high-risk data integrity tool.
- UI must never hide risk.
- UI must never simulate success.
- UI must always reflect real backend state.
- Analyze first, modify second.
- Dry-run before apply must be the default mental model.

"Feature done" means:
- Backend implemented
- API exposed
- UI visible
- End-to-end testable
- Risk-safe

========================================
MANDATORY UI PARITY
========================================
- Every new backend capability must become visible in UI immediately.
- No backend-only features unless explicitly marked internal.
- Commands, categories, validators, repairs, backups → must appear in UI.
- UI must regenerate in the same implementation step.

========================================
SETTINGS MANAGEMENT
========================================
All operational settings must be editable from UI:
- database
- storage
- immich connection
- backup
- scheduler / cron
- runtime safe environment settings

Security rules:
- secrets masked
- no secret leakage in logs
- validation before save
- high-risk settings show impact warnings

========================================
DASHBOARD REQUIREMENTS
========================================
Dashboard must immediately show:

- Immich configured
- Immich reachable
- DB reachable
- Storage reachable
- Paths match expectations
- Backup targets reachable
- Scheduler valid
- Runtime environment valid

Health states:
- OK
- WARNING
- ERROR
- UNKNOWN

Never hide partial failure.

========================================
OPERATION READINESS VISIBILITY
========================================
UI must show whether:

- analyze possible
- repair possible
- backup possible
- restore possible

Blocking reasons must be explicit.

========================================
NAVIGATION STRUCTURE
========================================
Sidebar must be domain-based:

- Dashboard
- Runtime / Health
- Consistency
- Database
- Storage
- Backup
- Reports / Logs
- Settings

Never mix domains.

========================================
TAB STRUCTURE
========================================
Inside each domain:

- Overview
- Analyze / Validate
- Repair
- History / Reports
- Settings

Never mix read-only and destructive actions in same tab.

========================================
BULK OPERATIONS SAFETY
========================================
Bulk actions must require confirmation.

Confirmation must show:
- scope
- category
- affected items count
- operation type
- dry-run vs apply
- risk level

High-risk actions require stronger confirmation pattern.

========================================
DISCLAIMER
========================================
UI must clearly state:

This tool can affect user data integrity.
Results must be reviewed before apply.
Some operations may be irreversible.

Warnings must be inline, not only in docs.

========================================
LOGGING & REPORTING
========================================
- All logs downloadable
- Structured reports downloadable
- Operation history preserved
- Context must be reconstructable later

========================================
DRY-RUN UX
========================================
- Repair/mutation actions must default to dry-run.
- UI must encourage preview.
- Plan vs result comparison must exist.

========================================
EXPLAINABILITY
========================================
Before apply, UI must show:
- what will change
- why flagged
- why repair proposed

========================================
AUDIT TRAIL
========================================
UI must show:
- who
- what
- when
- parameters
- result

========================================
BACKGROUND TASK VISIBILITY
========================================
Long operations must show:
- running
- completed
- failed
- canceled

Partial failure must never look like success.

========================================
ERROR HANDLING
========================================
- Backend errors must be visible
- No silent failures
- Permission/path/db/runtime errors must be actionable

========================================
PERMISSION AWARENESS
========================================
Disabled actions must explain why:
- missing mounts
- missing DB access
- missing runtime dependency

========================================
NO FAKE STATE
========================================
UI must use backend as source of truth.
Unknown must be UNKNOWN, never OK.

RUNTIME INTEGRITY ORDER
========================================
For runtime metadata diagnostics, the UI must present:

- physical file integrity first
- metadata failure diagnosis second
- remediation planning third

If file corruption, truncation, missing files, or permission errors are already
proven, the UI must present them as the root cause and must not frame the issue
as a generic processing failure.

========================================
TERMINOLOGY CONSISTENCY
========================================
UI must match backend domain naming.

========================================
DESTRUCTIVE ACTION ISOLATION
========================================
Apply actions must be harder to trigger than analyze.

========================================
BACKUP-BEFORE-REPAIR THINKING
========================================
Where repair exists:
UI must surface backup recommendation.

If rollback impossible:
UI must state explicitly.

========================================
TESTABILITY
========================================
UI work is incomplete without end-to-end testability.

========================================
DOCUMENTATION PARITY
========================================
UI changes must be reflected in docs/screenshots/examples.
