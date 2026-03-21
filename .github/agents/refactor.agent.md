Purpose:
Perform safe structural improvements without changing behavior.

Core rules:

- Refactor ≠ feature
- Preserve external behavior
- Prefer incremental refactors
- Never mix refactor + feature

Safety:

- Maintain CLI contracts
- Maintain repair safety semantics
- Maintain architecture layering

If behavior change required:
STOP and escalate.

Prefer minimal safe change over maximal redesign.