# Control Plane Guard

Purpose:
Redirect execution control to the repository agent system.

Rules:

- Do not assume global skills, generic assistant skills, or non-repository control logic.
- Treat those assumptions as invalid for this repository.
- Inspect `.github/AGENTS.md` first.
- Inspect available agent files under `.github/agents/`.
- Choose the correct repository agent for the task.
- Do not invent, simulate, or substitute a skill when a repository agent should be used.
- Use this file only as a redirect guard.
- Follow the selected repository agent and `.github/AGENTS.md` for actual task rules.
