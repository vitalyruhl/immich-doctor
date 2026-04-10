# Control Plane Guard

Purpose:
Redirect execution control to the repository agent system.

Rules:

- Do not assume global skills, generic assistant skills, or non-repository control logic.
- Treat those assumptions as invalid for this repository.
- Inspect `.github/AGENTS.md` first.
- Inspect available agent files under `.github/agents/`.
- Choose exactly one correct repository agent for the task.
- If agent selection is ambiguous, STOP.
- On ambiguity, report: candidate agents, ambiguity reason, and why selection is blocked.
- Do not fall back to generic behavior when ambiguity exists.
- Do not invent, simulate, or substitute a skill when a repository agent should be used.
- Use this file only as a redirect guard.
- Follow the selected repository agent and `.github/AGENTS.md` for actual task rules.
- If no repository agent matches the task, STOP.
- Report that no valid repository agent was found and why routing failed.
- Fallback to generic assistant behavior is strictly forbidden.