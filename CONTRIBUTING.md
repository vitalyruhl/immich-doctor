# Contributing

## Goals

This repository should stay beginner-friendly, modular, and safe for future
Immich maintenance workflows. Contributions should improve clarity, traceability,
and operational safety before adding more power.

## Development workflow

1. Start with a small, focused change.
2. Keep CLI code thin and move reusable logic into services and adapters.
3. Place every new command in the canonical domain hierarchy.
4. Split mixed concepts into separate domain commands instead of adding umbrella commands.
5. Add or update tests for changed behavior.
6. Update documentation when architecture, configuration, or scope changes.
7. Run local validation before opening a pull request:
   - `pytest`
   - `ruff check .`
   - `ruff format --check .`
8. Open a pull request with clear context, risk notes, and validation steps.

## Canonical command architecture

All contributor-facing CLI work must follow:

```text
immich-doctor <domain> <subdomain> <action> [options]
```

Current canonical domains:

- `runtime`
- `db`
- `storage`
- `backup`
- `diagnostics`
- `system`

Current command examples:

```text
immich-doctor runtime validate
immich-doctor runtime health check
immich-doctor storage paths check
immich-doctor storage permissions check
immich-doctor backup verify
immich-doctor db health check
immich-doctor db performance indexes check
```

Contributor rules:

- do not add new top-level flags for domain logic
- do not keep mixed semantics inside one command
- do not use `health` for performance or integrity analysis
- place index logic only under `db.performance.indexes`
- do not revive `config validate` as a catch-all command
- prefer architecture consistency over backward compatibility

Reviewers must reject non-canonical naming or placement before merge.

## Branch model

- `main`: protected, stable baseline
- `feature/*`: new functionality
- `fix/*`: bug fixes
- `chore/*`: documentation, tooling, CI, maintenance

Do not push directly to `main`.

## Commit and pull request expectations

- Keep commits focused and reviewable.
- Use clear commit messages that describe intent.
- Prefer squash merge for pull requests.
- PRs should explain:
  - what changed
  - why the change is needed
  - what was validated
  - what remains out of scope
  - any operational or data safety risk
- Use the repository pull request template.
- Link related issues when applicable.
- Use the issue forms for bug reports and feature requests.

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

Changes that can delete, move, quarantine, rewrite, or otherwise alter user data
must receive explicit maintainer review before merge.

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
- require at least one approving review before merge
- require the branch to be up to date before merge
- block direct pushes to `main`
- prefer squash merges
- dismiss stale reviews when new commits are pushed to a PR
- require review from code owners

Recommended required status checks:

- `Tests (Python 3.12)`
- `Tests (Python 3.13)`
- `Ruff`

These settings are documented here on purpose. They should be configured in GitHub,
not enforced indirectly through application code.

## Security reporting

For vulnerability reporting and coordinated disclosure expectations, follow
[`.github/SECURITY.md`](./.github/SECURITY.md).
