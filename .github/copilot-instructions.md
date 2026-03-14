Role:
you are my coding assistant. Follow the instructions in this file carefully when generating code.

========================================
COMMUNICATION STYLE
========================================
- Use informal tone with "du"
- Answer in German
- Give only a brief overview after completing tasks
- Provide detailed explanations only when explicitly asked

========================================
CORE PROJECT PRINCIPLES
========================================
This project is a high-risk data integrity tool.

Global priorities:
1. Never destroy user data silently
2. Always analyze before modifying
3. Always allow dry-run modes
4. Prefer quarantine over deletion
5. Prefer reporting over automation in early phases

========================================
SEMI-AUTOMATIC WORKFLOW GUIDELINES
========================================
- User changes are sacred:
  - Never revert or overwrite user edits without asking first.
  - If the user edits files during the agent run, treat those edits as intentional and preserve them.
  - If the user later requests a commit, include those user edits in the commit by default unless the user explicitly excludes specific files or changes.

- Confirm-before-write:
  - If requirements are ambiguous or the change impacts multiple subsystems/files,
    ask 1–3 precise clarifying questions before editing.

- Step-by-step workflow:
  - inspect -> plan -> change -> verify -> summarize

- Autonomy levels:
  - Level A (safe): read-only analysis
  - Level B (normal): small isolated changes
  - Level C (risky): anything involving data mutation, DB, storage, repair logic → REQUIRE confirmation

========================================
GIT WORKFLOW GUIDELINES
========================================
- main is protected
- main must always stay runnable and represent the latest tested stable state
- never commit directly to main
- use:
  - feature/*
  - fix/*
  - chore/*

- Branch model:
  - long-running work for a larger topic belongs on a dedicated feature branch
  - example: `feature/db`
  - short-lived implementation branches for that topic branch off from the feature branch
  - example: `chore/db-real-runtime-validation`
  - short-lived chore branches must be merged back into the matching feature branch first
  - only when the whole feature is complete and runnable, open a PR from the feature branch to `main`

- Branch freshness rules:
  - always branch from the latest relevant base
  - for a new feature branch, branch from current `main`
  - for a chore branch inside a feature, branch from the current feature branch
  - do not start a new work branch while the intended base branch is behind the tested latest state
  - after a feature is merged, delete obsolete work branches for that feature

- Merge rules:
  - prefer keeping feature branches up to date by fast-forwarding or rebasing short-lived chore branches into them
  - do not keep multiple parallel branches alive for the same completed topic when one canonical branch is enough

- Stage/commit/push only on explicit user request

========================================
ARCHITECTURE RULES (CRITICAL)
========================================
The architecture MUST remain layered:

- CLI layer
- Service layer
- Domain/Core layer
- Adapter/Infrastructure layer

Canonical command hierarchy:

- All CLI commands MUST follow:
  - `immich-doctor <domain> <subdomain> <action> [options]`
- Domain-specific one-off flags and flat shortcut commands are forbidden
- `health` is only for minimal reachability and readiness checks
- index analysis belongs under:
  - `db performance indexes check`
- `config validate` is not a canonical command concept and must not be reintroduced
- New command work must map cleanly to future GUI/API grouping:
  - Domain -> Subdomain -> Action

Rules:
- CLI MUST NOT access database or filesystem directly
- Services coordinate use-cases
- Core contains pure logic
- Adapters talk to:
  - PostgreSQL
  - filesystem
  - Immich API
  - external tools

========================================
REPAIR SYSTEM DESIGN RULES
========================================
Repair logic must follow:

1. Scan phase
2. Report phase
3. Decision phase
4. Execution phase

Never mix scan + mutate in same function.

Repair steps must be:
- idempotent
- resumable
- reversible where possible
- loggable
- dry-run capable

========================================
STORAGE SAFETY RULES
========================================
- Never delete original files automatically in early versions
- Prefer:
  quarantine/
  orphaned/
  corrupted/

- Large storage scans must be:
  - chunked
  - resumable
  - memory safe

========================================
DATABASE SAFETY RULES
========================================
- Never modify DB schema
- Never assume Immich internal invariants
- Prefer:
  detect -> report -> suggest fix

Hard DB mutations require:
explicit user confirmation.

========================================
PYTHON STYLE RULES
========================================
- Use type hints everywhere
- Prefer pathlib
- Prefer pydantic models for structured config/data
- Prefer small modules
- No business logic in CLI
- No global state mutation

========================================
PYTHON TOOLCHAIN POLICY
========================================
Use uv as single tool.

Allowed:
- uv sync
- uv add
- uv run

Forbidden:
- pip install
- poetry
- pipenv

========================================
TESTING & VALIDATION
========================================
- pytest for tests
- Add tests for repair logic
- Mocked data must be marked [MOCKED!]

========================================
IMMICH-SPECIFIC SAFETY
========================================
All operations must assume:

- broken DB possible
- broken storage possible
- inconsistent metadata possible

Never assume Immich correctness.

========================================
FINAL RULE
========================================
Never mark an issue as solved until user confirms.
