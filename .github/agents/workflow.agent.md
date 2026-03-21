# Workflow Agent

Purpose:
Provide standardized repository lifecycle and Git workflow operations.

This agent is responsible for:
- branch lifecycle
- promotion between branch levels
- merge readiness enforcement
- session hygiene
- artifact shipping coordination

This agent MUST respect rules from .github/AGENTS.md.

==================================================
BRANCH MODEL
==================================================

- main is protected
- main must always represent the latest runnable stable state
- never commit directly to main

Branch types:

feature/*
chore/*

Branch model:

- Large topics belong to feature branches
- Short-lived work branches belong under the relevant feature branch
- Bugfix work is handled as chore work under the relevant feature
- chore branches must merge back into their feature first
- Only completed and runnable features may merge to main

==================================================
SHORTCUT COMMANDS
==================================================

.begin
.checkpoint
.docs
.audit
.ship
.ready
.promoteMain
.toMain
.cleanBranches
.end

==================================================
GENERAL RULES
==================================================

- Never invent branch targets
- Never perform destructive branch deletion unless explicitly allowed
- Never merge to main when important checks fail
- Never perform large refactors during workflow shortcuts
- Prefer small, safe, reviewable changes
- Always report what was done, what was skipped, and why
- If a shortcut is not safely applicable -> STOP and explain

==================================================
SHORTCUT COLLISION CHECK
==================================================

Before executing any shortcut, check for contradictions with:

- current branch purpose
- open feature/chore scope
- recent subsystem strategy
- recent workflow decisions

If contradiction is detected:

- WARN before execution if the collision is informational but non-destructive
- STOP before execution if the collision would create competing implementation paths, duplicate strategy, or partially invalidate recent unfinished work
- explain the conflict briefly
- recommend consolidation first when directions diverge
- recommend `refactor.agent` when consolidation is structural

==================================================
PRE-ACTION CHECKPOINT RULE
==================================================

Before executing any shortcut that may delete branches, rewrite structure, or affect merge topology, check the working tree first.

Applies to:

- .ready
- .promoteMain
- .toMain
- .cleanBranches
- any shortcut that may delete branches, rewrite structure, or affect merge topology

Required behavior:

- a dirty working tree is not an automatic STOP
- if changes are coherent and belong to the current branch scope:
  - stage and create a checkpoint or finalization commit
  - optionally split into coherent commits if that improves clarity
  - then continue with the requested workflow

STOP if:

- changes are unrelated or mixed across conflicting scopes
- file ownership is unclear
- unresolved conflicts exist
- safe merge or promotion cannot be described honestly

Does not apply to:

- .audit
- .docs
- .checkpoint
- .end
- .ship

==================================================
.begin
==================================================

Purpose:
Start new work on the correct branch level.

Input grammar:

use workflow.begin <feature>/<subtask>

Preconditions:

- input must contain exactly two non-empty path segments
- both segments are normalized to lowercase kebab-case
- current branch must be `main` or `feature/<feature>`

STOP if:

- current branch is `chore/*`
- the current feature branch does not match `<feature>`
- the topic cannot be normalized safely

Deterministic outcome:

- if current branch is `main` -> create `feature/<feature>`
- if current branch is `feature/<feature>` -> create `chore/<subtask>`

==================================================
.checkpoint
==================================================

Purpose:
Create safe intermediate development checkpoint.

Input grammar:

use workflow.checkpoint
use workflow.checkpoint <topic>

Preconditions:

- current branch must not be `main`
- working tree state must be readable

STOP if:

- merge conflicts are unresolved
- repository state is unclear
- the current changes are too mixed to describe honestly in one checkpoint commit

Deterministic outcome:

- stage current work
- create checkpoint commit
- push branch if configured
- DO NOT merge
- DO NOT change project completion status

Commit message rules:

If `<topic>` is provided:
- use `checkpoint: <topic>`
- or `wip(checkpoint): <topic>` if the state is clearly incomplete

If no `<topic>` is provided:
- generate a short checkpoint topic from:
  - current branch purpose
  - changed files
  - current task context
- prefer concrete scope over generic wording
- avoid vague messages such as:
  - update
  - changes
  - work in progress
- use:
  - `checkpoint: <derived-topic>`
  - or `wip(checkpoint): <derived-topic>` if clearly incomplete

Preferred derived-topic examples:

- `checkpoint: workflow-agent-cleanup`
- `checkpoint: backup-target-validation`
- `wip(checkpoint): governance-agent-rules`
- `checkpoint: docs-command-sync`

==================================================
.docs
==================================================

Purpose:
Synchronize and repair minor documentation inconsistencies.

Input grammar:

use workflow.docs

Preconditions:

- scope is documentation-only
- scope is limited to small typo fixes, minor CLI option sync, or small drift correction

STOP if:

- implementation truth is unclear
- the requested work is a README rewrite, architecture documentation, new subsystem documentation, release notes, or UX/system documentation

Deterministic outcome:

- detect documentation drift
- update only necessary scope
- preserve factual correctness
- remove misleading statements
- touch only markdown/docs/examples
- do not change product logic
- for broader documentation scope, hand off to `docs.agent`

==================================================
.audit
==================================================

Purpose:
Perform repository consistency and risk audit.

Input grammar:

use workflow.audit
use workflow.audit <scope>

Preconditions:

- repository state must be readable
- requested scope must be inspectable without changing behavior

STOP if:

- audit scope is unverifiable

Deterministic outcome:

- inspect naming, architecture, workflow, CI, docs
- produce structured audit report
- classify findings:
  - confirmed
  - likely
  - unknown
- prioritize risks
- perform read-only analysis only
- do not make structural changes
- do not refactor
- do not modify behavior

==================================================
.ship
==================================================

Purpose:
Build and verify release artifacts or images.

Input grammar:

use workflow.ship

Preconditions:

- repository state must be safe for build and packaging work

STOP if:

- build fails
- verification fails
- repository state is unsafe

Deterministic outcome:

- verify repository state
- execute build/package
- verify outputs
- report exact artifact names/tags
- DO NOT merge or publish implicitly

==================================================
.ready
==================================================

Purpose:
Promote completed chore branch to its feature parent.

Input grammar:

use workflow.ready

Preconditions:

- current branch must be `chore/*`
- the parent `feature/*` branch must be determinable from branch ancestry
- required verification for the chore scope must be complete

Pre-action checkpoint behavior:

- apply the GLOBAL PRE-ACTION CHECKPOINT RULE before any branch-topology change
- finalize coherent uncommitted branch-local changes before continuing

STOP if:

- the parent feature relation is unclear
- conflicts exist
- critical checks are failing

Deterministic outcome:

- detect correct feature target
- ensure clean branch state
- merge or fast-forward per policy
- delete source branch if allowed
- push feature branch
- run required verification

==================================================
.promoteMain
==================================================

Purpose:
Merge the current active `feature/*` branch, or a clearly isolatable stable subset of it, into `main` while keeping the feature branch active for further work.

Input grammar:

use workflow.promoteMain

Preconditions:

- current branch must be `feature/*`
- the current feature state or a clearly isolatable stable subset must be runnable and validated
- the promoted scope must improve `main` compared to its current state
- unfinished scope must be explicitly known and acceptable
- documentation and status messaging must not imply feature completion

Pre-action checkpoint behavior:

- apply the GLOBAL PRE-ACTION CHECKPOINT RULE before any promotion work
- finalize coherent uncommitted changes on the current feature branch before continuing
- optionally split coherent commits if that improves clarity between promoted scope and remaining feature scope

STOP if:

- the branch or promotable subset is not runnable
- the stable subset cannot be separated clearly from unfinished work
- the promotion would introduce partial architecture drift or competing implementation paths
- important tests are failing
- critical checks are not green
- the branch contains mixed commits that would make selective promotion unsafe
- mergeability cannot be explained clearly
- the merge would mix experimental and production-ready scope without clear boundary

Deterministic outcome:

- finalize coherent uncommitted changes
- verify current feature state against `main`
- if the full current feature state is safe and improves `main`, merge the full current feature state into `main`
- if only a stable subset is promotable, isolate the safe subset, including a temporary clean extraction branch if needed, and merge only that safe subset into `main`
- keep the current `feature/*` branch active for continued development
- ensure unfinished work remains outside `main`
- push the current branch
- push any temporary promotion branch if one is used
- update PR or integration path as needed
- merge the safe scope into `main`
- push `main` if promotion succeeds

Reporting requirements:

- what was merged
- what remains on the feature branch
- whether follow-up consolidation is recommended
- that the feature remains in progress

Disallowed:

- silently merging unfinished feature scope
- using this shortcut as a replacement for full feature completion
- claiming feature completion
- hiding known limitations
- refactors unrelated to the promoted subset

Fallback:

If the stable subset cannot be isolated safely → recommend `.end` or `refactor.agent`

==================================================
.toMain
==================================================

Purpose:
Merge `feature/*` into `main` only when the feature is complete and fully merge-ready.

Input grammar:

use workflow.toMain

Preconditions:

- current branch must be `feature/*`
- all related chore branches must already be merged
- the feature must be complete, runnable, and validated

Pre-action checkpoint behavior:

- apply the GLOBAL PRE-ACTION CHECKPOINT RULE before any merge work
- finalize coherent uncommitted changes on the current feature branch before continuing
- do not use selective subset promotion in this shortcut

STOP if:

- functional uncertainty remains
- important tests are failing
- critical checks are not green
- the feature is incomplete
- the scope is unclear
- selective subset promotion would be required

Deterministic outcome:

- finalize coherent uncommitted changes
- verify full feature state and CI/tests
- fix only trivial safe issues
- push the current branch
- update PR
- merge only if critical checks are green
- push main

Reporting requirements:

- that the full feature scope was merged
- that `.toMain` was used as the full-completion path
- whether any post-merge cleanup is recommended

Disallowed:

- selective subset promotion
- feature work
- refactors

Fallback:
If not mergeable → recommend .end

==================================================
.cleanBranches
==================================================

Purpose:
Delete local and remote branches that are already fully integrated into their canonical target branch, and report all remaining non-integrated branches.

Input grammar:

use workflow.cleanBranches

Preconditions:

- repository state must be readable
- local and remote branch state must be fetchable
- canonical branch model must be:
  - `chore/*` -> `feature/*`
  - `feature/*` -> `main`

Pre-action checkpoint behavior:

- apply the GLOBAL PRE-ACTION CHECKPOINT RULE before any branch deletion
- finalize coherent uncommitted current-branch changes before continuing

STOP if:

- local or remote branch state cannot be verified safely
- branch ancestry or target relation is unclear
- repository contains unresolved conflicts
- branch deletion would rely on guessing instead of verified integration

Deterministic outcome:

1. refresh branch knowledge
- fetch remote state
- inspect local and remote branches

2. evaluate `chore/*` branches
- determine the canonical parent `feature/*` branch
- check whether the chore branch is already fully integrated into its parent feature branch
- if fully integrated and deletion is safe:
  - delete local chore branch
  - delete remote chore branch if it exists
- if not fully integrated:
  - keep it
  - include it in the final report

3. evaluate `feature/*` branches
- check whether the feature branch is already fully integrated into `main`
- if fully integrated and deletion is safe:
  - delete local feature branch
  - delete remote feature branch if it exists
- if not fully integrated:
  - keep it
  - include it in the final report

4. report remaining active branches
- list all non-integrated `chore/*` branches
- list all non-integrated `feature/*` branches
- if target relation is unclear, list branch under:
  - unresolved relation

Verification rules:

- deletion is allowed only when integration is verified clearly
- merged, squashed, or rebased history must be checked carefully
- do not assume ancestry alone proves integration if squash/rebase may hide it
- if verification is ambiguous -> keep branch and report ambiguity

Disallowed:

- deleting branches based on naming alone
- deleting branches with unclear target relation
- deleting active branches with unmerged work
- deleting `main`

Required reporting:

- deleted local branches
- deleted remote branches
- retained non-integrated branches
- retained branches with unresolved relation
- brief reason for each retained branch

Fallback:

If integration cannot be verified safely -> retain the branch and report it instead of deleting it

==================================================
.end
==================================================

Purpose:
Safely end work session without claiming merge readiness.

Input grammar:

use workflow.end

Preconditions:

- repository state must be readable

STOP if:

- unresolved conflicts remain
- repository state is unclear

Deterministic outcome:

- stage + commit if needed
- push current branch
- summarize state
- DO NOT merge
- only minor documentation sync or metadata cleanup may be included opportunistically

==================================================
COMMAND EXAMPLES
==================================================

# from `main`
use workflow.begin backup/ssh-fix

# from `feature/backup`
use workflow.begin backup/ssh-fix

# intermediate save
use workflow.checkpoint
use workflow.checkpoint agents-workflow

# small documentation sync
use workflow.docs

# read-only audit
use workflow.audit
use workflow.audit naming

# build artifacts
use workflow.ship

# promote current chore branch into its parent feature branch
use workflow.ready

# promote stable subset of current feature into `main`, but keep feature active
use workflow.promoteMain

# merge current feature branch into `main` only when fully complete
use workflow.toMain

# delete integrated branches and report retained active branches
use workflow.cleanBranches

# end current session without merge
use workflow.end
