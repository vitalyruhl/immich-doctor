# Project Status Audit

## Purpose

The `Project Status Audit` workflow keeps the GitHub Project status field cleaner for items that drift in `Blocked` or `Validation`.

It is intentionally conservative:

- it prefers no change over a wrong change
- it only auto-moves items when evidence is strong
- it always leaves a short audit comment when it changes a status

## What It Audits

The automation scans the `Backup Execution Roadmap` GitHub Project and evaluates only items currently in:

- `Blocked`
- `Validation`

It ignores every other project status.

## What It Can Change

### `Validation` -> `Done`

This happens only when there is strong evidence such as:

- the tracked PR is merged
- the tracked issue is closed and has explicit completion evidence
- the tracked item is explicitly superseded by a merged PR

The automation will not mark an item `Done` just because time passed or because the issue is still open.

### `Blocked`

The automation only auto-clears `Blocked` when completion is certain, for example:

- the blocked PR itself is merged
- the blocked item is explicitly superseded by a merged PR
- the blocked issue is closed with explicit completion evidence

If a blocker looks stale but there is no safe target status, the automation does not guess. It leaves the item unchanged and reports it for manual review in the workflow summary.

## What It Will Not Do

- It does not modify code or repository files.
- It does not create or delete project items.
- It does not merge or close PRs.
- It does not infer success from branch existence alone.
- It does not override open validation tracks that still say testing is ongoing.

## Workflow Triggers

Workflow file:

- [`.github/workflows/project-status-audit.yml`](../.github/workflows/project-status-audit.yml)

Triggers:

- daily scheduled run
- manual `workflow_dispatch`

## Manual Run

Use `workflow_dispatch` and set:

- `dry_run=true` to see what would change without updating the project
- optional `project_owner`, `project_title`, or `project_number` overrides if the project location changes later

## Dry Run

In dry-run mode the workflow:

- evaluates the same items and rules
- writes the same summary
- does not update project statuses
- does not post audit comments

## Audit Comment Format

Automatic status changes write a concise comment to the linked issue or PR with:

- the old and new status
- the reason
- the evidence used
- the workflow run link when available

The comment includes a machine marker so repeated identical transitions do not keep spamming the same item.

## Configuration

Script:

- [`scripts/project_status_audit.py`](../scripts/project_status_audit.py)

Recommended configuration:

- repository secret `PROJECT_STATUS_AUDIT_TOKEN`
  - should have permission to read repository metadata, comment on issues/PRs, and update the target GitHub Project
- optional repository variables:
  - `PROJECT_STATUS_AUDIT_OWNER`
  - `PROJECT_STATUS_AUDIT_TITLE`
  - `PROJECT_STATUS_AUDIT_NUMBER`

If the project stays on the same owner/title, the defaults are enough and only the token is usually needed.

## Safe Rule Changes

If the project workflow evolves later, adjust the heuristics only in:

- [`scripts/project_status_audit.py`](../scripts/project_status_audit.py)

Keep the rules narrow and evidence-based. When in doubt, leave the item unchanged and make the workflow summary ask for manual review.
