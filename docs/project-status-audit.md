# Project Status Audit

## Purpose

The project hygiene automation keeps the GitHub Project status field cleaner for items that drift in status columns that should be evidence-backed.

It is intentionally conservative:

- it prefers no change over a wrong change
- it only auto-moves items when evidence is strong
- it always leaves a short audit comment when it changes a status

## What It Audits

Current workflows:

- [`.github/workflows/project-status-audit.yml`](../.github/workflows/project-status-audit.yml)
- [`.github/workflows/project-inprogress-hygiene.yml`](../.github/workflows/project-inprogress-hygiene.yml)

The automation scans the `Backup-Doctor Projekt` GitHub Project and evaluates only items currently in:

- `Blocked`
- `Validation`
- `In progress`

Each workflow only acts on its own target statuses and ignores every other project status.

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

### `In progress`

The in-progress hygiene workflow only auto-moves tracked work from `In progress` to `Done` when completion is clear and safe:

- the tracked PR is merged and there are no remaining tracked work signals
- or the tracked issue is closed, any linked PR work is merged, and there is explicit completion evidence

It will not mark `In progress` work as `Done` when:

- the issue is still open
- a linked PR is still open
- comments still suggest ongoing work or follow-up
- completion evidence is weak or conflicting

Closed-but-unclear items are reported for manual review instead of being auto-closed in the project.

## What It Will Not Do

- It does not modify code or repository files.
- It does not create or delete project items.
- It does not merge or close PRs.
- It does not infer success from branch existence alone.
- It does not override open validation tracks that still say testing is ongoing.
- It does not move open `In progress` work to `Done`.
- It does not infer completion from staleness alone.

## Workflow Triggers

Triggers:

- weekend scheduled run
- manual `workflow_dispatch`

## Manual Run

Use `workflow_dispatch` and set:

- `dry_run=true` to see what would change without updating the project
- optional `project_owner`, `project_title`, or `project_number` overrides if the project location changes later

The automation is intended to resolve the project primarily by `project_number`. Title is retained only as a human-readable fallback or override.

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

Scripts:

- [`scripts/project_status_audit.py`](../scripts/project_status_audit.py)
- [`scripts/project_inprogress_hygiene.py`](../scripts/project_inprogress_hygiene.py)
- [`scripts/project_audit_common.py`](../scripts/project_audit_common.py)

Recommended configuration:

- repository secret `PROJECT_STATUS_AUDIT_TOKEN`
  - should have permission to read repository metadata, comment on issues/PRs, and update the target GitHub Project
- optional repository variables:
  - `PROJECT_STATUS_AUDIT_OWNER`
  - `PROJECT_STATUS_AUDIT_TITLE`
  - `PROJECT_STATUS_AUDIT_NUMBER`

Current default target:

- owner: `vitalyruhl`
- project number: `3`
- display title: `Backup-Doctor Projekt`

If the project stays on the same owner/number, the defaults are enough and only the token is usually needed.

## Safe Rule Changes

If the project workflow evolves later, adjust the heuristics only in:

- [`scripts/project_status_audit.py`](../scripts/project_status_audit.py)
- [`scripts/project_inprogress_hygiene.py`](../scripts/project_inprogress_hygiene.py)

Keep the rules narrow and evidence-based. When in doubt, leave the item unchanged and make the workflow summary ask for manual review.
