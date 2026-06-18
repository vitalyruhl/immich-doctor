# Workflow Governance

- `main` is protected; do not make direct work commits on `main`.
- Use `.github/AGENTS.md` as canonical global governance and `.github/agents/workflow.agent.md` for branch lifecycle, promotion, merge, cleanup, and shipping operations.
- Prefer `rg` / `rg --files` for repository discovery, including `rg --hidden` for governance and hidden config.
- Do not revert or delete unrelated user changes. Treat untracked hidden project config as potentially important until inspected.
- Publication and topology changes require branch freshness, collision checks, and open PR awareness.
- Validation must match the changed surface: Python changes need Python checks; frontend dependency/UI changes need frontend install/test/build/audit as relevant; docs-only work should not claim full product validation unless run.
- Remote CI failures must be inspected from logs before changing code; distinguish code fixes from token/permission or external workflow failures.