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

use workflow.checkpoint <topic>

Preconditions:

- current branch must not be `main`
- working tree state must be readable

STOP if:

- merge conflicts are unresolved
- repository state is unclear

Deterministic outcome:

- stage current work
- create checkpoint commit
- push branch if configured
- DO NOT merge
- DO NOT change project completion status
- commit message is `checkpoint: <topic>` or `wip(checkpoint): <topic>`

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
Promote the current stable subset of an active feature branch into `main` without closing or deleting the feature branch.

Input grammar:

use workflow.promoteMain

Preconditions:

- current branch must be `feature/*`
- the current branch contains a stable, runnable, and clearly mergeable subset
- the promoted subset must improve `main` compared to its current state
- the remaining unfinished feature work must stay isolated and must not be dragged into `main`

STOP if:

- the stable subset cannot be separated clearly from unfinished work
- the promotion would introduce partial architecture drift or competing implementation paths
- important tests are failing
- critical checks are not green
- the branch contains mixed commits that would make selective promotion unsafe

Deterministic outcome:

- identify the mergeable subset of the current feature work
- promote only the stable subset into `main`
- keep the current `feature/*` branch active for continued development
- ensure unfinished work remains outside `main`
- update PR or integration path as needed
- push `main` if promotion succeeds
- report clearly:
  - what was promoted
  - what remains on the feature branch
  - whether follow-up consolidation is recommended

Disallowed:

- silently merging unfinished feature scope
- using this shortcut as a replacement for full feature completion
- refactors unrelated to the promoted subset

Fallback:

If the stable subset cannot be isolated safely → recommend `.end` or `refactor.agent`

==================================================
.toMain
==================================================

Purpose:
Merge feature into main only if fully merge-ready.

Input grammar:

use workflow.toMain

Preconditions:

- current branch must be `feature/*`
- all related chore branches must already be merged
- the feature must be runnable and validated

STOP if:

- functional uncertainty remains
- important tests are failing
- critical checks are not green

Deterministic outcome:

- verify CI/tests
- fix only trivial safe issues
- update PR
- merge only if critical checks are green
- push main

Disallowed:

- feature work
- refactors

Fallback:
If not mergeable → recommend .end

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

# merge current feature branch into `main`
use workflow.toMain

# end current session without merge
use workflow.end
