# Core Project Memory

- Project: `immich-doctor`, Python 3.12+ CLI/API/UI toolkit for safe Immich maintenance, validation, backup, consistency, and repair workflows.
- Start with repository governance before changing files: `.github/AGENTS.md`, then the relevant `.github/agents/*.agent.md`.
- Key context memories: project overview in `mem:project_overview`, architecture boundaries in `mem:architecture`, development commands in `mem:development_commands`, workflow rules in `mem:workflow_governance`, Serena handling in `mem:serena_project_state`.
- Preserve operator safety: validation-first behavior, dry-run/default-safe repair behavior, explicit reports, traceability, and no silent broadening of destructive workflows.
- Serena project files are repository-relevant configuration. Do not delete `.serena/` as cleanup. Only remove known generated/runtime paths when they are ignored and clearly disposable.