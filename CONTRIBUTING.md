# Contributing

## Goals

This repository should stay beginner-friendly, modular, and safe for future
Immich maintenance workflows. Contributions should improve clarity, traceability,
and operational safety before adding more power.

## Development workflow

1. Start with a small, focused change.
2. Keep CLI code thin and move reusable logic into services and adapters.
3. Add or update tests for changed behavior.
4. Update documentation when architecture, configuration, or scope changes.
5. Open a pull request with clear context, risk notes, and validation steps.

## Branch model

- `main`: protected, stable baseline
- `feature/*`: new functionality
- `fix/*`: bug fixes
- `chore/*`: documentation, tooling, CI, maintenance

Do not push directly to `main`.

## Commit and pull request expectations

- Keep commits focused and reviewable.
- Use clear commit messages that describe intent.
- PRs should explain:
  - what changed
  - why the change is needed
  - what was validated
  - what remains out of scope
  - any operational or data safety risk

## Code style basics

- Use modern Python with type hints.
- Keep modules small and focused.
- Prefer explicit imports.
- Keep code comments in English.
- Keep logs and error messages in English.
- Avoid business logic inside CLI entrypoints.

## Review expectations

Review should focus on:

- correctness
- safety
- architectural fit
- traceability
- test coverage for changed core logic
- clarity for future maintainers with basic Python knowledge

## Testing expectations

- Use `pytest` for automated tests.
- Prefer targeted unit tests first.
- Add integration tests for CLI or service flows when the behavior spans modules.
- Document manual validation steps in the PR when automated coverage is not enough.

## Safety rules for repair-oriented changes

Risky repair behavior must land in stages:

1. report-only
2. dry-run
3. quarantine-capable flow
4. explicitly approved destructive behavior, if ever justified

Destructive delete behavior must not be the first implementation.

Every future repair action must be:

- traceable in reports or journals
- explicit about scope and limits
- documented with operational risk notes

## Recommended GitHub repository settings

Recommended repository settings for GitHub:

- protect `main`
- require pull requests before merge
- require required status checks before merge
- require the branch to be up to date before merge
- block direct pushes to `main`
- prefer squash merges

These settings are documented here on purpose. They should be configured in GitHub,
not enforced indirectly through application code.

