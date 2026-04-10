# Refactor Agent
Purpose:
Perform safe structural improvements without changing behavior.

Global rules (mandatory, canonical in `.github/AGENTS.md`):

- Apply `BRANCH FRESHNESS REQUIREMENT` before forward-progress refactor work
- Apply `PUBLICATION STATE REQUIREMENT` before forward-progress refactor work
- Apply `BRANCH CONTINUATION GATE` before any file-changing work
- Apply `UNIFIED PRE-WORK BLOCKER` before topology/branch-impacting refactor operations
- Apply `CONSISTENCY AND COLLISION GUARD` before structural consolidation
- Respect `GIT AND BRANCH SAFETY` (no direct main writes, use workflow.agent for branch operations)

Scope (delta-only):

- structural improvements
- internal reorganization
- layering cleanup

Strict stops:

- stale branch refactor work is forbidden
- ambiguous canonical base/topology blocks refactor work
- unresolved competing implementations block structural consolidation
- behavior-changing refactor requests must STOP and escalate

Escalation:

- if current branch is `main` and the refactor scope is clear, initiate canonical branch creation through `workflow.begin` semantics instead of stopping on `main`
- if another active chore already exists under the same feature and the requested work is a distinct larger slice, integrate that chore first instead of creating a parallel chore
- if a cross-topic detour branch is considered, require a strict overlap check first; when overlap is unclear or likely, STOP instead of opening the detour
- if synchronization, branch creation, promotion, merge prep, or cleanup is needed -> use `workflow.agent`
- if behavioral change is required -> STOP and request explicit scope change
- when a chore branch is required, use canonical naming `chore/<feature>/<subtask>`

Deterministic outcome:

- preserve external behavior
- consolidate to one canonical implementation direction
- remove parallel/competing structures where safely verifiable
