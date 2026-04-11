# Workflow Agent

Purpose:
Provide repository workflow operations for branch lifecycle, promotion, merge preparation, cleanup, and shipping.

This agent MUST apply global rules from `.github/AGENTS.md`.

## Canonical dependencies

- branch freshness and canonical base -> `BRANCH FRESHNESS REQUIREMENT`
- unpublished/open-PR awareness -> `PUBLICATION STATE REQUIREMENT`
- authoritative rule source -> `GOVERNANCE AUTHORITY RULE`
- continuation decision -> `BRANCH CONTINUATION GATE`
- hard preconditions before forward progress or topology changes -> `UNIFIED PRE-WORK BLOCKER`
- collision handling -> `CONSISTENCY AND COLLISION GUARD`
- reporting fields -> `MANDATORY REPORTING CONTRACT`
- main protection and branch safety -> `GIT AND BRANCH SAFETY`

## Branch model

- `main` is protected and must never receive direct work commits
- there is exactly one active `feature/*` workstream at a time until it is integrated into `main`
- `feature/*` is the canonical current work carrier for all unpublished work
- `chore/<feature>/<subtask>` is an optional short-lived, scoped isolation branch under that active feature
- at most one active `chore/*` may exist under the active feature at a time
- exception: a temporary cross-topic detour branch may use
  - `chore/<active-feature>/to-<target-feature>-<subtask>`
  - it starts from `main`, lands on `main`, and must be deleted before the suspended feature resumes
- non-canonical `fix/*` branches are retained and reported unless verified safe for cleanup

## Shortcut invocation syntax

- canonical form: `workflow.<shortcut>`
- optional alias form: `.<shortcut>`
- do not mix undocumented invocation styles

## Shortcut catalog

`workflow.begin` `workflow.checkpoint` `workflow.docs` `workflow.audit` `workflow.ship` `workflow.ready` `workflow.promoteMain` `workflow.toMain` `workflow.cleanBranches` `workflow.end`

Alias equivalents: `.begin` `.checkpoint` `.docs` `.audit` `.ship` `.ready` `.promoteMain` `.toMain` `.cleanBranches` `.end`

## Execution model

Workflow shortcuts are target-state requests, not narrow branch-shape assertions.

The workflow agent MUST satisfy missing prerequisite stages automatically when:

- the next step is deterministic
- branch topology is clear
- required validation can still be performed honestly
- no freshness/publication/collision blocker is active
- no governance-authority blocker is active

The workflow agent MUST NOT stop merely because the user invoked a later-stage shortcut from an earlier branch level if the required chain is clear and safe.

Examples:

- invoking `workflow.begin` on `main` for a file-changing task means: create the canonical working branch stack automatically
- invoking `workflow.promoteMain` on `chore/<feature>/<subtask>` means: checkpoint if needed -> optional docs sync if narrow and factual -> checkpoint docs if changed -> `workflow.ready` -> synchronize feature state -> promote stable subset to `main`
- invoking `workflow.toMain` on `chore/<feature>/<subtask>` means: checkpoint if needed -> optional docs sync if narrow and factual -> checkpoint docs if changed -> `workflow.ready` -> synchronize feature state -> choose `workflow.toMain` if the feature is honestly complete, otherwise choose `workflow.promoteMain` -> `workflow.cleanBranches`

The workflow agent must prefer the least-destructive chain that satisfies the user goal of getting the current validated state onto `main`.

The workflow agent must not use unpublished governance changes as binding workflow law unless the user explicitly requested a simulation or rehearsal.

## Publication gate

Before any workflow shortcut that changes topology, merges branches, or starts new work, inspect:

- local unpublished commits
- remote unpublished feature/chore branches
- open PRs not yet merged
- upstream branches that disappeared but still have local history
- unpublished governance changes that would alter the decision logic itself
- matching GitHub Project tracked item for the requested task scope
- canonical task-tracking Issue existence for that scope

If relevant unpublished state exists for the same scope, do not continue from an older effective base.

Task tracking is mandatory before forward-progress workflow actions:

- there must be a corresponding Issue tracked in GitHub Project before task start
- tracked item may be Issue or PR card, but the work item must resolve to an Issue
- if no matching Issue exists, create the Issue and add/link it in GitHub Project before continuing

Required action:

1. integrate it
2. synchronize onto it
3. or explicitly supersede it with a clear warning and isolation plan

If unpublished governance changes would be required to justify the next workflow step, integrate those governance changes into `main` first unless the user explicitly asked for simulation only.

If another unpublished active `feature/*` exists, do not start a second feature.

Required action:

1. integrate the current active feature into `main`
2. clean fully integrated branches
3. only then create the next feature

If an active `chore/*` already exists under the active feature, do not start a second one.

Required action:

1. continue the existing chore if the task is the same work slice
2. integrate the existing chore into the parent feature first if the new task is a distinct larger slice
3. only then create the new chore

Detour exception:

- a temporary cross-topic detour branch may be created only when ALL are true:
  - the active feature is clean, checkpointed, and intentionally suspended
  - the detour work is urgent
  - the detour starts from current `main`
  - overlap with the suspended feature is demonstrably absent or safely extractable
  - the branch name contains `to-<target-feature>`
- if overlap is unclear, likely, or strategic rather than surgical, STOP instead of creating the detour

## Shortcut reference

### `workflow.begin`

Purpose:
Start work on the correct branch level.

Input:
`workflow.begin <feature>/<subtask>`

Preconditions:

- current branch is `main` or `feature/<feature>`
- input has exactly two kebab-case segments
- corresponding task Issue exists and is tracked in GitHub Project (create + link first if missing)
- apply `UNIFIED PRE-WORK BLOCKER`

STOP if:

- current branch is already `chore/<feature>/<subtask>` and the request would duplicate active scope
- feature segment mismatches current `feature/*`
- input normalization fails
- blockers fail

Deterministic outcome:

- from `main` -> create/switch `feature/<feature>`, then create/switch `chore/<feature>/<subtask>`
- from `feature/<feature>` -> create/switch `chore/<feature>/<subtask>`
- if a sibling chore already exists under that feature:
  - continue it when the task is the same slice
  - otherwise integrate it first, then create the new chore
- for an approved detour request:
  - checkpoint and suspend the active feature if needed
  - create `chore/<active-feature>/to-<target-feature>-<subtask>` from current `main`
- active branch after success is the created or selected working branch, either standard `chore/<feature>/<subtask>` or approved detour `chore/<active-feature>/to-<target-feature>-<subtask>`

### `workflow.checkpoint`

Purpose:
Create an intermediate checkpoint.

Input:
`workflow.checkpoint [topic]`

Preconditions:

- current branch is not `main`
- working tree state is readable

Behavior:

- if branch is fresh: normal checkpoint
- if branch is stale: allow checkpoint only as safety-preserving action per global checkpoint exception

STOP if:

- unresolved conflicts
- repository state unclear
- changes are too mixed for one honest checkpoint commit

Deterministic outcome:

- stage + commit + push
- no merge
- if stale-branch checkpoint: explicitly report `sync required before continued forward-progress`

### `workflow.docs`

Purpose:
Small documentation synchronization only.

Input:
`workflow.docs`

Preconditions:

- documentation-only, narrow scope
- apply `BRANCH CONTINUATION GATE`
- for repository-changing docs work, apply `BRANCH FRESHNESS REQUIREMENT`

STOP if:

- implementation truth is unclear
- scope is rewrite/architecture/new subsystem docs/release notes/UX system docs

Deterministic outcome:

- minimal factual doc correction only
- no product logic changes
- hand off broad docs work to `docs.agent`

### `workflow.audit`

Purpose:
Read-only consistency and risk audit.

Input:
`workflow.audit [scope]`

Preconditions:

- repository state readable
- scope is inspectable read-only

STOP if:

- scope unverifiable

Deterministic outcome:

- read-only findings with priorities
- include freshness/publication/collision observations where relevant

### `workflow.ship`

Purpose:
Build and verify artifacts or images.

Input:
`workflow.ship`

Preconditions:

- repository state safe for build and packaging

STOP if:

- build fails
- verification fails
- repository state is unsafe

Deterministic outcome:

- run build or package
- verify outputs
- report exact artifact names or tags
- no implicit merge or publish

### `workflow.ready`

Purpose:
Promote `chore/<feature>/<subtask>` into its parent `feature/*`.

Input:
`workflow.ready`

Preconditions:

- current branch is `chore/<feature>/<subtask>`
- parent `feature/*` is determinable
- required checks complete
- apply `UNIFIED PRE-WORK BLOCKER`

Automatic prerequisite chain:

- if the worktree is dirty -> `workflow.checkpoint`
- if small factual docs drift is detected -> `workflow.docs`, then `workflow.checkpoint`

STOP if:

- parent relation is unclear
- the branch is a `to-<target-feature>` detour branch
- blockers fail
- conflicts or required checks fail after sync or merge

Deterministic outcome:

- merge or fast-forward chore into parent feature
- push feature
- delete source chore branch if safe

### `workflow.promoteMain`

Purpose:
Merge a stable subset of current work into `main` via PR while keeping the broader feature active when needed.

Input:
`workflow.promoteMain`

Accepted current branches:

- `feature/*`
- `chore/<feature>/<subtask>` through automatic prerequisite chaining
- `chore/<active-feature>/to-<target-feature>-<subtask>` as a detour branch that promotes directly to `main`

Preconditions:

- promoted scope is runnable, validated, and improves `main`
- apply `UNIFIED PRE-WORK BLOCKER`

Automatic prerequisite chain:

- from `chore/<feature>/<subtask>` -> `workflow.checkpoint` if needed -> optional `workflow.docs` -> checkpoint docs if changed -> `workflow.ready`
- from resulting `feature/*` -> inspect publication state and synchronize onto the latest effective base before PR creation
- from `chore/<active-feature>/to-<target-feature>-<subtask>` -> checkpoint if needed -> verify overlap gate passed -> promote directly to `main` without `workflow.ready`

STOP if:

- stable subset is not safely isolatable
- blockers fail
- required checks fail
- mergeability is unclear

Deterministic outcome:

- prepare promotable full scope or safe subset
- push branch or extraction branch if needed
- open or update PR to `main`
- merge only through PR when checks are green
- keep the feature branch active unless cleanup proves it is fully integrated
- if the source is a detour branch:
  - delete the detour after merge
  - synchronize the suspended active feature to the new `main` before resuming work

### `workflow.toMain`

Purpose:
Get the current validated work onto `main`.

Input:
`workflow.toMain`

Accepted current branches:

- `feature/*`
- `chore/<feature>/<subtask>` through automatic prerequisite chaining

Preconditions:

- apply `UNIFIED PRE-WORK BLOCKER`
- current state is runnable and validated
- corresponding task Issue is tracked in GitHub Project and ready for transition update on merge

Automatic prerequisite chain:

- from `chore/<feature>/<subtask>` -> `workflow.checkpoint` if needed -> optional `workflow.docs` -> checkpoint docs if changed -> `workflow.ready`
- synchronize resulting `feature/*` with the latest effective base, including relevant unpublished/open-PR state
- if the feature is honestly complete -> continue with full `toMain`
- otherwise -> downgrade safely to `workflow.promoteMain`
- after successful merge to `main` -> `workflow.cleanBranches`

STOP if:

- required blockers fail
- mergeability or publication state is unclear
- validation fails

Deterministic outcome:

- push required branch state
- open or update PR to `main`
- merge via PR when checks are green
- update/move the tracked project item to review/done semantics according to repository status taxonomy (for example `Review` then `Done`, including equivalent wording such as `prüfen`/`fertig`)
- clean fully integrated branches afterward

### `workflow.cleanBranches`

Purpose:
Delete branches already fully integrated into canonical targets.

Input:
`workflow.cleanBranches`

Preconditions:

- repository state is readable
- remote state is fetchable
- apply relevant `UNIFIED PRE-WORK BLOCKER` elements for topology and deletion

Mandatory pre-step:

- `fetch --all --prune`

STOP if:

- integration status cannot be verified clearly
- relation or target is ambiguous
- unresolved conflicts or state ambiguity exists

Deterministic outcome:

- evaluate `chore/<feature>/<subtask>` against parent feature
- evaluate `feature/*` against `origin/main`
- delete local and remote branches only when verified integrated
- report retained branches with reasons

### `workflow.end`

Purpose:
End session safely without merge claim.

Input:
`workflow.end`

Preconditions:

- repository state is readable

STOP if:

- unresolved conflicts
- repository state is unclear

Deterministic outcome:

- stage + commit if needed
- push current branch
- report branch, freshness status, publication state, and next recommended action
- no merge
