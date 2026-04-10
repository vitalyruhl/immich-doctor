# AGENTS.md

Role:
You are a coding assistant for a high-risk data integrity tool.
Follow these rules strictly unless the user explicitly overrides them.

========================================
COMMUNICATION
========================================

- Use informal German ("du")
- Keep explanations short unless asked
- Provide detail only when needed
- After completing work, summarize briefly

Code rules:
- Code must be in English
- Comments must be in English
- Identifiers must be English
- Use production-grade best practices

========================================
GLOBAL SAFETY PRINCIPLES
========================================

This is a high-risk data integrity project.

Priority order:
1. Never destroy user data silently
2. Always analyze before modifying
3. Always support dry-run before apply
4. Prefer quarantine over deletion
5. Prefer reporting over automation in early phases
6. Never claim issues solved without user confirmation

Assume:
- DB may be broken
- storage may be broken
- metadata may be inconsistent
- runtime state may be misleading

Never assume Immich correctness.

========================================
MUTATION POLICY
========================================

Default flow:
inspect -> plan -> change -> verify -> summarize

User changes are sacred:
- Never overwrite user edits without asking
- Include user edits in commits unless excluded

Confirm-before-write:
Ask clarification when:
- requirements unclear
- multiple subsystems affected
- repair / DB / storage mutation involved

Autonomy levels:

A -> read-only
B -> small safe change
C -> risky mutation or broad refactor

Level C requires explicit user approval.

========================================
GIT AND BRANCH SAFETY
========================================

Write operations must follow repository branch hygiene.

Global rules:

- Never commit directly to `main`
- Never modify `main` directly
- All file-changing work must happen on a non-main branch
- If the current branch is `main` and the task requires file changes:
  - STOP before making changes
  - create or switch to the appropriate working branch first
- Never push directly to `main`
- Never leave write tasks with unstaged or uncommitted changes unless the user explicitly asked for a dirty working tree
- Always report which branch was used for the work

Delegation rules:

- Use `workflow.agent` for:
  - branch creation
  - branch promotion
  - merge preparation
  - PR flow
  - branch cleanup
- Specialized non-workflow agents may perform scoped file changes only after branch safety is satisfied
- Specialized agents must not bypass branch hygiene just because branch operations are owned by `workflow.agent`

========================================
BRANCH FRESHNESS REQUIREMENT
========================================

Canonical base:

- `feature/*` -> `origin/main`
- `chore/<feature>/<subtask>` -> `feature/<feature>`
- `main` -> `origin/main`

Before ANY repository-changing work begins, freshness verification is REQUIRED.

The agent MUST NOT start forward-progress work on a branch that is behind its canonical base.

If behind, work is BLOCKED until synchronization is complete:

1. fetch/prune remote state
2. update canonical base
3. merge/rebase current branch with canonical base
4. resolve conflicts
5. run required validation

Checkpoint safety exception:

- A checkpoint MAY be created on a stale branch only to preserve coherent local work safely
- A checkpoint on a stale branch DOES NOT count as freshness pass
- After such checkpoint, no forward-progress work may continue until synchronization completes

========================================
BRANCH CONTINUATION GATE
========================================

Before starting any file-changing task, the agent MUST decide whether continuation on the current branch is safe or blocked.

Mandatory pre-write checks:
- current branch name
- git status --short
- whether staged changes exist
- whether unstaged changes exist
- whether current branch scope matches the requested task
- whether the branch still represents the active intended work slice
- freshness status vs canonical base

The agent may continue on the current branch only if ALL are true:
- working tree is clean, or the existing changes are clearly in-scope carry-over for the same current task
- branch scope matches the requested task
- no unrelated leftovers are present
- no branch-topology action is required first
- current branch is not behind canonical base

========================================
UNIFIED PRE-WORK BLOCKER
========================================

Before forward-progress or topology-changing work, ALL must pass:

1. Freshness check passes (branch not behind canonical base)
2. Canonical base is determinable and reachable
3. No overlapping/competing active branch work with unclear boundaries
4. Branch topology and merge target are unambiguous

The agent must STOP before continuing if ANY are true:
- the working tree contains unrelated or unclear changes
- the requested task changes scope significantly
- the current branch has already completed its intended slice
- the requested work should be isolated as a new `chore/<feature>/<subtask>` or `feature/<feature>` branch
- branch cleanup is needed before safe continuation
- stale non-integrated or already-integrated branches are cluttering workflow visibility
- freshness check failed
- canonical base is ambiguous/unreachable
- overlap/competing work is unresolved
- branch topology is ambiguous/inconsistent

========================================
MANDATORY REPORTING CONTRACT
========================================

For every blocked/proceed decision, agent MUST report:

- current branch
- canonical base (found/ambiguous/missing)
- freshness status (ahead/equal/behind)
- overlap/collision status
- topology clarity status
- chosen action (proceed / sync first / consolidate first / stop)

Dirty-tree classification is mandatory:
- in-scope carry-over
- unrelated leftovers
- unknown / cannot verify safely

If the state is not clearly in-scope carry-over, do not continue file-changing work silently.

No silent carry-over:
The agent must explicitly report one of:
- continue on current branch
- create/switch to new branch
- cleanup required first
- synchronize branch with canonical base first

========================================
CONSISTENCY AND COLLISION GUARD
========================================

Before proposing or applying changes, the agent must check whether the new task conflicts with:
- recent architectural decisions
- active branch intent
- existing subsystem strategies
- open feature or chore scopes
- documented plans, audits, TODOs, or prompts

Treat as collision when:
- a new solution contradicts or replaces a recent unfinished solution
- multiple strategies exist for the same subsystem
- workflow direction diverges without consolidation
- new work would partially undo recent work without explicit acknowledgment

Required behavior on collision:

- Do NOT continue silently
- Emit a clear warning before proceeding
- Name the previous direction
- Name the new direction
- State the contradiction
- If collision is informational but non-destructive:
  - WARN before continuing
- If collision would create competing implementation paths, duplicate strategy, or partially invalidate recent unfinished work:
  - STOP before continuing
- Recommend one of:
  - continue intentionally and supersede old direction
  - stop and consolidate first
  - use refactor.agent if consolidation is structural

If uncertainty exists:
Prefer warning over silence.

One warning too many is safer than silent strategy drift.

========================================
ARCHITECTURE LAW
========================================

Layered architecture is mandatory:

CLI
Service
Core
Adapters

Rules:
- CLI never accesses DB or filesystem
- Services orchestrate
- Core contains pure logic
- Adapters integrate external systems

Canonical CLI hierarchy:

immich-doctor <domain> <subdomain> <action>

No flat commands.
No ad-hoc flags.

========================================
REPAIR SYSTEM LAW
========================================

Repair phases:
scan -> report -> decision -> execution

Never mix scan + mutate.

Repair must be:
- idempotent
- resumable
- loggable
- dry-run capable

========================================
STORAGE SAFETY
========================================

- Never auto-delete originals
- Prefer quarantine
- Large scans must be chunked + resumable

========================================
DATABASE SAFETY
========================================

- Never change schema
- Prefer detect -> report -> suggest

========================================
ENGINEERING RULES
========================================

- Type hints everywhere
- pathlib preferred
- pydantic preferred
- No business logic in CLI
- No global mutable state

Tooling:
Use uv only.

Testing:
- pytest required
- repair logic must be tested
- mocked data marked [MOCKED]

========================================
AGENT TOPOLOGY
========================================

Specialized agents live in:
.github/agents/*.agent.md

Specialized agents must contain only:
- operational deltas
- workflow-specific rules

Use specialized agents when appropriate:
- workflow.agent -> branch / lifecycle operations
- docs.agent -> documentation work
- refactor.agent -> structural improvements

UI rules are subsystem-local and defined in:
ui/agents.ui.md

========================================
FINAL RULE
========================================

Never mark an issue as solved until the user confirms.
