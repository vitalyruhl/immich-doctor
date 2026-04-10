# Workflow Agent

Purpose:
Provide repository workflow operations (branch lifecycle, promotion, cleanup, artifact shipping).

This agent MUST apply global rules from `.github/AGENTS.md`.

## Global dependency map (canonical source)

- Branch freshness + canonical base: `BRANCH FRESHNESS REQUIREMENT`
- Continuation decision: `BRANCH CONTINUATION GATE`
- Hard preconditions before forward-progress/topology changes: `UNIFIED PRE-WORK BLOCKER`
- Stale-branch checkpoint handling: `BRANCH FRESHNESS REQUIREMENT` (checkpoint safety exception)
- Collision handling: `CONSISTENCY AND COLLISION GUARD`
- Reporting fields: `MANDATORY REPORTING CONTRACT`
- Main protection / PR discipline: `GIT AND BRANCH SAFETY`

## Branch model (workflow-specific)

- `main` is protected
- `feature/*` carries major work
- `chore/<feature>/<subtask>` carries short-lived feature subtasks
- non-canonical `fix/*` is retained/reported unless verified for safe deletion

## Shortcut invocation syntax (canonical)

- Canonical form: `workflow.<shortcut>`
- Optional alias form: `.<shortcut>`
- Do not mix undocumented invocation styles.

## Shortcut catalog

`workflow.begin` `workflow.checkpoint` `workflow.docs` `workflow.audit` `workflow.ship` `workflow.ready` `workflow.promoteMain` `workflow.toMain` `workflow.cleanBranches` `workflow.end`

Alias equivalents: `.begin` `.checkpoint` `.docs` `.audit` `.ship` `.ready` `.promoteMain` `.toMain` `.cleanBranches` `.end`

---

## .begin

Purpose:
Start work on the correct branch level.

Input:
`workflow.begin <feature>/<subtask>`

Preconditions:
- current branch is `main` or `feature/<feature>`
- input has exactly two kebab-case segments
- apply `UNIFIED PRE-WORK BLOCKER`

STOP if:
- current branch is `chore/<feature>/<subtask>`
- feature segment mismatches current `feature/*`
- input normalization fails
- blocker fails

Deterministic outcome:
- from `main` -> create/switch `feature/<feature>`, then create/switch `chore/<feature>/<subtask>`
- from `feature/<feature>` -> create/switch `chore/<feature>/<subtask>`
- active branch after success is always `chore/<feature>/<subtask>`

## .checkpoint

Purpose:
Create an intermediate checkpoint.

Input:
`workflow.checkpoint [topic]`

Preconditions:
- current branch is not `main`
- working tree state is readable

Behavior:
- if branch is fresh: normal checkpoint
- if branch is stale: allow checkpoint ONLY as safety-preserving action per global checkpoint exception

STOP if:
- unresolved conflicts
- repository state unclear
- changes too mixed for one honest checkpoint commit

Deterministic outcome:
- stage + commit + push
- no merge
- if stale-branch checkpoint: explicitly report "sync required before continued forward-progress"

## .docs

Purpose:
Small documentation synchronization only.

Input:
`workflow.docs`

Preconditions:
- documentation-only, narrow scope
- apply `BRANCH CONTINUATION GATE`
- for repository-changing docs work, apply `BRANCH FRESHNESS REQUIREMENT`

STOP if:
- implementation truth unclear
- scope is rewrite/architecture/new subsystem docs/release notes/UX system docs

Deterministic outcome:
- minimal factual doc correction only
- no product logic changes
- hand off broad docs work to `docs.agent`

## .audit

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
- include freshness/collision risk observations where relevant

## .ship

Purpose:
Build and verify artifacts/images.

Input:
`workflow.ship`

Preconditions:
- repository state safe for build/packaging

STOP if:
- build fails
- verification fails
- repository state unsafe

Deterministic outcome:
- run build/package
- verify outputs
- report exact artifact names/tags
- no implicit merge/publish

## .ready

Purpose:
Promote `chore/<feature>/<subtask>` into its parent `feature/*`.

Input:
`workflow.ready`

Preconditions:
- current branch is `chore/<feature>/<subtask>`
- parent `feature/*` determinable
- required checks complete
- apply `UNIFIED PRE-WORK BLOCKER`

STOP if:
- parent relation unclear
- blocker fails
- conflicts/check failures after required sync/merge

Deterministic outcome:
- merge/ff chore into parent feature
- push feature
- delete source branch if safe

## .promoteMain

Purpose:
Merge stable subset of current `feature/*` into `main` via PR while keeping feature active.

Input:
`workflow.promoteMain`

Preconditions:
- current branch is `feature/*`
- promoted scope is runnable/validated and improves `main`
- apply `UNIFIED PRE-WORK BLOCKER`

STOP if:
- stable subset not safely isolatable
- blocker fails
- required checks fail
- mergeability unclear

Deterministic outcome:
- prepare promotable full scope or safe subset
- push branch/extraction branch if needed
- open/update PR to `main`
- merge only through PR when checks are green
- keep feature branch active

## .toMain

Purpose:
Merge complete `feature/*` into `main` via PR.

Input:
`workflow.toMain`

Preconditions:
- current branch is `feature/*`
- feature complete, runnable, validated
- related chores already merged
- apply `UNIFIED PRE-WORK BLOCKER`

STOP if:
- feature incomplete/unclear
- blocker fails
- required checks fail
- selective subset would be required

Deterministic outcome:
- push feature branch
- open/update PR to `main`
- merge via PR when checks are green

## .cleanBranches

Purpose:
Delete branches already fully integrated into canonical targets.

Input:
`workflow.cleanBranches`

Preconditions:
- repository state readable
- remote state fetchable
- apply `UNIFIED PRE-WORK BLOCKER` elements relevant to topology/deletion

Mandatory pre-step:
- `fetch --all --prune`

STOP if:
- integration status cannot be verified clearly
- relation/target ambiguous
- unresolved conflicts/state ambiguity

Deterministic outcome:
- evaluate `chore/<feature>/<subtask>` against parent feature, `feature/*` against `origin/main`
- delete local/remote branches only when verified integrated
- report retained branches with reasons

## .end

Purpose:
End session safely without merge claim.

Input:
`workflow.end`

Preconditions:
- repository state readable

STOP if:
- unresolved conflicts
- repository state unclear

Deterministic outcome:
- stage+commit if needed
- push current branch
- report branch + freshness status + next recommended action
- no merge
