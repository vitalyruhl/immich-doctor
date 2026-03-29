#!/usr/bin/env python3
"""Conservative GitHub Project status audit for Blocked and Validation items."""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

from project_audit_common import (
    DEFAULT_PROJECT_TITLE,
    AuditDecision,
    GitHubClient,
    ProjectItem,
    build_audit_comment,
    build_run_url,
    collect_linked_pull_requests,
    env_truthy,
    has_duplicate_audit_comment,
    load_token,
    lower_texts,
    matches_any,
)

AUTOMATION_MARKER = "<!-- project-status-audit:auto"
ONGOING_VALIDATION_PATTERNS = (
    r"validation (?:is )?(?:still )?(?:ongoing|pending|in progress)",
    r"(?:testing|validation) continues",
    r"ongoing integration testing",
    r"pending user validation",
    r"real .*validation .*pending",
    r"remains in testing state",
    r"current test image for validation",
    r"please .*confirm",
    r"awaiting .*validation",
)
BLOCKER_PATTERNS = (
    r"\bblocked\b",
    r"waiting on",
    r"pending approval",
    r"dependency .* unresolved",
    r"requires .* decision",
    r"external input",
)
COMPLETION_PATTERNS = (
    r"all checks passed",
    r"validation passed",
    r"validated successfully",
    r"fully verified",
    r"status updated from validation to done",
    r"status updated from blocked to done",
)
LINKED_REFERENCE_PATTERNS = (
    re.compile(r"supersed(?:ed|es?) by (?:merged )?(?:pr|pull request) #(\d+)", re.I),
    re.compile(
        r"(?:fixed|resolved|completed|handled) by "
        r"(?:merged )?(?:pr|pull request|#)(?:\s*)#?(\d+)",
        re.I,
    ),
)


@dataclass(slots=True)
class AuditReport:
    blocked_items: list[ProjectItem] = field(default_factory=list)
    validation_items: list[ProjectItem] = field(default_factory=list)
    changed: list[AuditDecision] = field(default_factory=list)
    unchanged: list[AuditDecision] = field(default_factory=list)
    manual_review: list[AuditDecision] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY"))
    parser.add_argument("--project-owner", default=os.getenv("PROJECT_STATUS_AUDIT_OWNER"))
    parser.add_argument(
        "--project-title",
        default=os.getenv("PROJECT_STATUS_AUDIT_PROJECT_TITLE", DEFAULT_PROJECT_TITLE),
    )
    parser.add_argument(
        "--project-number",
        type=int,
        default=int(os.getenv("PROJECT_STATUS_AUDIT_PROJECT_NUMBER"))
        if os.getenv("PROJECT_STATUS_AUDIT_PROJECT_NUMBER")
        else None,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=env_truthy("PROJECT_STATUS_AUDIT_DRY_RUN"),
    )
    parser.add_argument("--summary-file", default=os.getenv("GITHUB_STEP_SUMMARY"))
    args = parser.parse_args()
    if not args.repo:
        parser.error("--repo is required")
    if not args.project_owner:
        args.project_owner = args.repo.split("/", 1)[0]
    return args


def resolve_merged_reference_pr(
    client: GitHubClient,
    repo: str,
    body: str,
    comments: list[dict[str, object]],
) -> dict[str, object] | None:
    for pull_request in collect_linked_pull_requests(
        client, repo, body, comments, LINKED_REFERENCE_PATTERNS
    ):
        if pull_request.get("merged_at"):
            return pull_request
    return None


def evaluate_validation_issue(
    client: GitHubClient,
    item: ProjectItem,
    comments: list[dict[str, object]],
) -> AuditDecision:
    text = lower_texts(item.content.body, comments)
    linked_pr = resolve_merged_reference_pr(
        client, item.content.repository, item.content.body, comments
    )
    if item.content.state == "CLOSED" and (matches_any(text, COMPLETION_PATTERNS) or linked_pr):
        evidence = "issue is closed"
        if linked_pr:
            evidence = f"issue references merged PR #{linked_pr['number']}"
        return AuditDecision(
            item=item,
            outcome="change",
            old_status="Validation",
            new_status="Done",
            reason="Validation track is resolved with clear completion evidence.",
            evidence=evidence,
        )
    if item.content.state == "OPEN" and matches_any(text, ONGOING_VALIDATION_PATTERNS):
        return AuditDecision(
            item=item,
            outcome="unchanged",
            old_status="Validation",
            new_status=None,
            reason="Validation is still explicitly ongoing.",
            evidence="comments/body still describe active or pending validation",
        )
    if item.content.state == "OPEN":
        return AuditDecision(
            item=item,
            outcome="manual_review",
            old_status="Validation",
            new_status=None,
            reason="Validation item is still open without strong completion evidence.",
            evidence="open issue and no safe Done signal detected",
        )
    return AuditDecision(
        item=item,
        outcome="manual_review",
        old_status="Validation",
        new_status=None,
        reason="Closed issue lacks explicit completion evidence.",
        evidence="state alone is not enough for an automatic Done transition",
    )


def evaluate_blocked_issue(
    client: GitHubClient,
    item: ProjectItem,
    comments: list[dict[str, object]],
) -> AuditDecision:
    text = lower_texts(item.content.body, comments)
    linked_pr = resolve_merged_reference_pr(
        client, item.content.repository, item.content.body, comments
    )
    if item.content.state == "CLOSED" and linked_pr:
        return AuditDecision(
            item=item,
            outcome="change",
            old_status="Blocked",
            new_status="Done",
            reason="Blocked item is resolved by a merged replacement PR.",
            evidence=f"references merged PR #{linked_pr['number']}",
        )
    if item.content.state == "CLOSED" and matches_any(text, COMPLETION_PATTERNS):
        return AuditDecision(
            item=item,
            outcome="change",
            old_status="Blocked",
            new_status="Done",
            reason="Blocked item is closed with explicit completion evidence.",
            evidence="closed issue plus completion markers in body/comments",
        )
    if item.content.state == "OPEN" and matches_any(text, BLOCKER_PATTERNS):
        return AuditDecision(
            item=item,
            outcome="unchanged",
            old_status="Blocked",
            new_status=None,
            reason="Blocker is still explicitly documented.",
            evidence="body/comments still describe an active blocker",
        )
    return AuditDecision(
        item=item,
        outcome="manual_review",
        old_status="Blocked",
        new_status=None,
        reason="Blocked state could not be safely reclassified.",
        evidence="no active blocker proof and no safe completion proof",
    )


def evaluate_validation_pr(
    client: GitHubClient,
    item: ProjectItem,
    comments: list[dict[str, object]],
) -> AuditDecision:
    if item.content.state == "MERGED" or item.content.merged_at:
        return AuditDecision(
            item=item,
            outcome="change",
            old_status="Validation",
            new_status="Done",
            reason="PR is merged.",
            evidence=f"merged at {item.content.merged_at or 'unknown time'}",
        )
    linked_pr = resolve_merged_reference_pr(
        client, item.content.repository, item.content.body, comments
    )
    if item.content.state == "CLOSED" and linked_pr:
        return AuditDecision(
            item=item,
            outcome="change",
            old_status="Validation",
            new_status="Done",
            reason="PR is superseded by a merged replacement PR.",
            evidence=f"references merged PR #{linked_pr['number']}",
        )
    if item.content.state == "OPEN":
        return AuditDecision(
            item=item,
            outcome="unchanged",
            old_status="Validation",
            new_status=None,
            reason="PR is still open.",
            evidence="validation remains active until merge or explicit completion",
        )
    return AuditDecision(
        item=item,
        outcome="manual_review",
        old_status="Validation",
        new_status=None,
        reason="Closed PR is not merged and lacks a clear superseding resolution.",
        evidence="cannot safely infer Done",
    )


def evaluate_blocked_pr(
    client: GitHubClient,
    item: ProjectItem,
    comments: list[dict[str, object]],
) -> AuditDecision:
    if item.content.state == "MERGED" or item.content.merged_at:
        return AuditDecision(
            item=item,
            outcome="change",
            old_status="Blocked",
            new_status="Done",
            reason="Blocked PR is already merged.",
            evidence=f"merged at {item.content.merged_at or 'unknown time'}",
        )
    text = lower_texts(item.content.body, comments)
    linked_pr = resolve_merged_reference_pr(
        client, item.content.repository, item.content.body, comments
    )
    if item.content.state == "CLOSED" and linked_pr:
        return AuditDecision(
            item=item,
            outcome="change",
            old_status="Blocked",
            new_status="Done",
            reason="Blocked PR was superseded by a merged replacement PR.",
            evidence=f"references merged PR #{linked_pr['number']}",
        )
    if item.content.state == "OPEN" and matches_any(text, BLOCKER_PATTERNS):
        return AuditDecision(
            item=item,
            outcome="unchanged",
            old_status="Blocked",
            new_status=None,
            reason="PR still has an explicit blocker signal.",
            evidence="body/comments still describe blocking conditions",
        )
    return AuditDecision(
        item=item,
        outcome="manual_review",
        old_status="Blocked",
        new_status=None,
        reason="Blocked PR could not be safely reclassified.",
        evidence="no clear blocker and no clear completion evidence",
    )


def evaluate_item(
    client: GitHubClient,
    item: ProjectItem,
) -> tuple[AuditDecision, list[dict[str, object]]]:
    comments = client.get_issue_comments(item.content.repository, item.content.number)
    if item.status == "Validation":
        if item.content.kind == "PullRequest":
            return evaluate_validation_pr(client, item, comments), comments
        return evaluate_validation_issue(client, item, comments), comments
    if item.status == "Blocked":
        if item.content.kind == "PullRequest":
            return evaluate_blocked_pr(client, item, comments), comments
        return evaluate_blocked_issue(client, item, comments), comments
    raise ValueError(f"Unsupported status: {item.status}")


def format_items(items: list[ProjectItem]) -> list[str]:
    if not items:
        return ["- none"]
    return [f"- `{item.status}` [{item.content.title}]({item.content.url})" for item in items]


def format_decisions(
    decisions: list[AuditDecision],
    *,
    include_transition: bool = False,
) -> list[str]:
    if not decisions:
        return ["- none"]
    lines: list[str] = []
    for decision in decisions:
        title = f"[{decision.item.content.title}]({decision.item.content.url})"
        if include_transition and decision.new_status:
            lines.append(
                f"- {title}: `{decision.old_status}` -> `{decision.new_status}`. "
                f"{decision.reason} Evidence: {decision.evidence}"
            )
        else:
            lines.append(f"- {title}: {decision.reason} Evidence: {decision.evidence}")
    return lines


def write_summary(report: AuditReport, summary_file: str | None, dry_run: bool) -> None:
    lines = [
        "# Project Status Audit",
        "",
        f"- Dry-run: `{'true' if dry_run else 'false'}`",
        f"- Generated: `{datetime.now(UTC).isoformat()}`",
        "",
        "## Audited `Blocked` Items",
        "",
        *format_items(report.blocked_items),
        "",
        "## Audited `Validation` Items",
        "",
        *format_items(report.validation_items),
        "",
        "## Changed Items",
        "",
        *format_decisions(report.changed, include_transition=True),
        "",
        "## Unchanged Items",
        "",
        *format_decisions(report.unchanged),
        "",
        "## Manual Review Required",
        "",
        *format_decisions(report.manual_review),
    ]
    summary = "\n".join(lines) + "\n"
    print(summary)
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as handle:
            handle.write(summary)


def main() -> int:
    args = parse_args()
    client = GitHubClient(load_token())
    repo_name = args.repo.split("/", 1)[1]
    project = client.get_project(
        args.project_owner,
        repo_name,
        args.project_title,
        args.project_number,
    )
    fields = client.get_project_fields(project["id"])
    status_field = fields.get("Status")
    if not status_field or "Done" not in status_field:
        raise RuntimeError("Project Status field or Done option could not be resolved")

    report = AuditReport()
    run_url = build_run_url()

    for item in client.iter_project_items(project["id"]):
        if item.status not in {"Blocked", "Validation"}:
            continue
        if item.status == "Blocked":
            report.blocked_items.append(item)
        else:
            report.validation_items.append(item)

        decision, comments = evaluate_item(client, item)
        if decision.outcome == "change" and decision.new_status:
            decision.comment_body = build_audit_comment(
                AUTOMATION_MARKER,
                "Project status audit",
                decision,
                run_url,
            )
            if not args.dry_run:
                client.update_project_status(
                    project["id"],
                    item.id,
                    status_field["id"],
                    status_field[decision.new_status],
                )
                if not has_duplicate_audit_comment(
                    comments,
                    AUTOMATION_MARKER,
                    decision.old_status,
                    decision.new_status,
                ):
                    client.post_issue_comment(
                        item.content.repository,
                        item.content.number,
                        decision.comment_body,
                    )
            report.changed.append(decision)
        elif decision.outcome == "manual_review":
            report.manual_review.append(decision)
        else:
            report.unchanged.append(decision)

    write_summary(report, args.summary_file, args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - top-level workflow failure path
        print(f"project_status_audit failed: {exc}", file=sys.stderr)
        raise
