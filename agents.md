Role:
You are my coding assistant. Follow the instructions in this file carefully when generating code, plans, refactors, tests, and reviews.

========================================
1. COMMUNICATION STYLE
========================================
- Use informal tone with "du"
- Answer in German
- Keep explanations brief by default
- Provide detailed explanations only when explicitly asked
- After completing work, provide only a short overview unless more detail is requested

If code is shown:
- Code must be in English
- Comments must be in English
- Names for variables, functions, classes, files, and identifiers must be in English
- Use production-grade best practices

========================================
2. PROJECT RISK PROFILE
========================================
This project is a high-risk data integrity tool.

Global priorities (strict order):
1. Never destroy user data silently
2. Always analyze before modifying
3. Always support dry-run before apply
4. Prefer quarantine over deletion
5. Prefer reporting over automation in early phases
6. Never claim a problem is solved until the user confirms it

Assume at all times:
- broken DB possible
- broken storage possible
- inconsistent metadata possible
- partial or misleading application state possible

Never assume Immich correctness.

========================================
3. WORKFLOW RULES
========================================
Default workflow:
inspect -> plan -> change -> verify -> summarize

User changes are sacred:
- Never revert or overwrite user edits without asking first
- If the user edits files during the agent run, treat those edits as intentional and preserve them
- If the user later requests a commit, include user edits by default unless the user explicitly excludes files or changes

Confirm-before-write:
Ask 1–3 precise clarifying questions before editing if:
- requirements are ambiguous
- multiple subsystems/files are affected
- repair logic, DB mutations, or storage mutations are introduced

Autonomy levels:
- Level A: read-only inspection and analysis
- Level B: small isolated changes with low risk
- Level C: risky work involving DB mutation, storage mutation, repair logic, or broad refactors

Level C always requires explicit user confirmation before writing.

Stage, commit, and push only on explicit user request.

Keep docs updated:
- Update docs/ready-to-use-commands.md whenever a finished user-facing command is added, renamed, deprecated, or removed

Runtime integrity rule:
- physical file integrity inspection must happen before metadata failure classification or repair planning
- proven file defects are root causes and must not be downgraded to vague job failures
- unknown runtime states remain unsafe and visible until resolved

========================================
4. GIT WORKFLOW
========================================
Rules:
- main is protected
- main must remain runnable and represent the latest tested stable state
- Never commit directly to main

Use branches:
- feature/*
- fix/*
- chore/*

Branch model:
- Large topics belong on a dedicated feature branch
- Short-lived implementation branches branch from the related feature branch
- Short-lived branches must merge back into the matching feature branch first
- Only when the feature is complete and runnable, open a PR from the feature branch to main

Branch freshness:
- Always branch from the latest relevant base
- Do not start work from an outdated base branch
- Before starting any implementation, verify that the current branch matches the task scope
- If the current branch does not match the task scope, stop and state:
  - which branch is active
  - why it does not fit the task
  - which branch should be used instead
- Before starting work, verify the relevant base branch is current against local and remote state
- If the relevant base is outdated, stop and state exactly what is behind:
  - current branch vs expected base
  - local branch vs remote branch
  - missing merges or PR state if visible
- Never start a new task on top of unrelated feature work without explicitly calling out the dependency
- When a task depends on another open feature branch, provide a short decision aid before changing code:
  - merge the other feature first
  - branch intentionally from that feature
  - split the work to avoid the dependency
- Never do implementation work directly on main
- Before commit, push, or PR, verify:
  - current branch name
  - clean or intentionally changed working tree
  - correct target/base branch
  - no unrelated local changes are being dragged along
- After finishing work on a short-lived branch, return the topic to its canonical branch state:
  - all related chore/fix branches merged back cleanly
  - temporary integration branches deleted
  - no stale work branch left behind
- When switching from one feature to another, verify:
  - whether the destination branch is current
  - whether other feature work needed by the task is already in main
  - whether changes should be merged, rebased, or kept isolated
  - then state the recommended path with brief tradeoff guidance
- Before claiming that work is already in main, verify:
  - local branches
  - remote branches
  - merged vs non-merged branch state
  - open PRs
  - squash/rebase merge cases where ancestry alone may be misleading

========================================
5. ARCHITECTURE RULES (CRITICAL)
========================================
The architecture MUST remain layered:

- CLI layer
- Service layer
- Domain/Core layer
- Adapter/Infrastructure layer

Rules:
- CLI MUST NOT access database or filesystem directly
- Services coordinate use-cases
- Core contains pure logic
- Adapters talk to:
  - PostgreSQL
  - filesystem
  - Immich API
  - external tools

Canonical command hierarchy (STRICT LAW):
immich-doctor <domain> <subdomain> <action> [options]

Forbidden:
- flat shortcut commands
- domain-specific one-off flags
- non-hierarchical CLI extensions
- reintroduction of "config validate" concept

Special rules:
- health is only for minimal reachability and readiness checks
- index analysis belongs under:
  db performance indexes check

New command work MUST map cleanly to future GUI/API grouping:
Domain -> Subdomain -> Action

========================================
6. REPAIR SYSTEM DESIGN RULES
========================================
Repair logic must follow strict phases:
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

Mutating repair foundation rules:
- future mutating repair flows must execute inside a persisted `RepairRun`
- future mutating repair flows must write persisted journal entries
- inspect -> plan -> apply must be protected by a live-state guard or plan token
- integrated mutating repair flows must create and reference a real `pre_repair` snapshot
- file-destructive behavior must remain quarantine-first
- targeted undo may only be claimed when the journal contains enough reversible data
- currently supported real targeted undo is limited to journal-backed runtime permission repair
- broader repair domains must report restore/undo blockers explicitly instead of pretending reversibility

Runtime metadata repair rule:
- never blindly retry metadata extraction when file integrity already proves missing, empty, truncated, corrupted, or permission-denied input
- prefer reporting, quarantine planning, or permission repair over automation

========================================
7. STORAGE SAFETY RULES
========================================
- Never delete original files automatically in early versions
- Prefer quarantine locations:
  quarantine/
  orphaned/
  corrupted/

Large storage scans must be:
- chunked
- resumable
- memory safe

========================================
8. DATABASE SAFETY RULES
========================================
- Never modify DB schema
- Never assume Immich internal invariants
- Prefer:
  detect -> report -> suggest fix

Hard DB mutations require explicit user confirmation.

========================================
9. CONSISTENCY FRAMEWORK UX RULES
========================================
Primary UX unit:
- category, not the individual finding

Validation output must:
- group findings by category
- include summary with:
  - category name
  - severity
  - repair mode
  - count
  - representative sample findings

Individual findings:
- must exist as structured first-class records
- must have deterministic stable finding_id

Repair selection must support exactly:
- --category <category>
- --id <finding-id>
- --all-safe

Forbidden:
- broad unsafe --all flag
- ambiguous selectors such as --albums, --assets, --fix-all

Repair defaults:
- always dry-run
- mutation only with explicit --apply

--all-safe:
- must include only categories explicitly marked safe

Category names must be:
- stable
- machine-friendly
- suitable for future UI grouping

Repair output must clearly distinguish:
- selected scope
- planned actions
- applied actions
- skipped actions
- post-repair validation result

Framework must support future UI with:
- category overview cards
- expandable finding details
- per-category repair actions
- optional per-finding repair actions

========================================
10. PYTHON STYLE RULES
========================================
- Use type hints everywhere
- Prefer pathlib
- Prefer pydantic models for structured config/data
- Prefer small modules
- No business logic in CLI
- No global state mutation

========================================
11. PYTHON TOOLCHAIN POLICY
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
12. TESTING & VALIDATION
========================================
- pytest required
- Add tests for repair logic
- Mocked data must be marked [MOCKED!]

========================================
FINAL RULE
========================================
Never mark an issue as solved until user confirms.

UI rules are defined in ui/agents.ui.md and are mandatory.
