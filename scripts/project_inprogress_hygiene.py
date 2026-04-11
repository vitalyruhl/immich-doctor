#!/usr/bin/env python3
"""Conservative GitHub Project hygiene audit for In progress items."""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

from project_audit_common import (
    DEFAULT_PROJECT_NUMBER,
    DEFAULT_PROJECT_TITLE,
    AuditDecision,
    GitHubClient,
    ProjectItem,
    build_audit_comment,
    build_run_url,
    collect_linked_pull_requests,
    env_truthy,
    has_duplicate_audit_comment,
    is_recent,
    load_token,
    lower_texts,
    matches_any,
)

AUTOMATION_MARKER = "<!-- project-inprogress-hygiene:auto"
LINKED_REFERENCE_PATTERNS = (
    re.compile(
        r"(?:fixed|resolved|completed|implemented|merged) by "
        r"(?:pr|pull request) #(\d+)",
        re.I,
    ),
    re.compile(r"supersed(?:ed|es?) by (?:merged )?(?:pr|pull request) #(\d+)", re.I),
    re.compile(r"(?:via|in) (?:merged )?(?:pr|pull request) #(\d+)", re.I),
)
ONGOING_WORK_PATTERNS = (
    r"\bin progress\b",
    r"\bongoing\b",
    r"\bstill open\b",
    r"\bstill active\b",
    r"\bwork continues\b",
    r"\btesting continues\b",
    r"\bvalidation continues\b",
    r"\bpending\b",
    r"\bawaiting\b",
    r"\bnext step\b",
    r"\bfollow[- ]up\b",
    r"\bblocked\b",
)
COMPLETION_PATTERNS = (
    r"\bcompleted\b",
    r"\bdone\b",
    r"\bresolved\b",
    r"\bfully verified\b",
    r"\bvalidated successfully\b",
    r"\ball checks passed\b",
    r"\bstatus updated from in progress to done\b",
)
RECENT_ACTIVITY_DAYS = 5
OPEN_TASK_PATTERN = re.compile(r"^\s*[-*]\s*\[ \]", re.M)


@dataclass(slots=True)
class AuditReport:
    in_progress_items: list[ProjectItem] = field(default_factory=list)
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
        else DEFAULT_PROJECT_NUMBER,
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


def has_open_tasks(text: str) -> bool:
    return bool(OPEN_TASK_PATTERN.search(text))


def has_recent_ongoing_signal(comments: list[dict[str, object]]) -> bool:
    for comment in comments:
        body = (comment.get("body") or "").lower()
        if matches_any(body, ONGOING_WORK_PATTERNS) and is_recent(
            comment.get("updated_at"), days=RECENT_ACTIVITY_DAYS
        ):
            return True
    return False


def summarize_pull_request_states(pull_requests: list[dict[str, object]]) -> str:
    parts = []
    for pull_request in pull_requests:
        state = (
            "merged"
            if pull_request.get("merged_at")
            else str(pull_request.get("state", "")).lower()
        )
        parts.append(f"PR #{pull_request['number']} ({state})")
    return ", ".join(parts)


def evaluate_pull_request_item(
    item: ProjectItem,
    comments: list[dict[str, object]],
) -> AuditDecision:
    text = lower_texts(item.content.body, comments)
    if item.content.state == "OPEN":
        return AuditDecision(
            item=item,
            outcome="unchanged",
            old_status="In progress",
            new_status=None,
            reason="PR is still open.",
            evidence="open pull request should remain In progress",
        )
    if item.content.state == "MERGED" or item.content.merged_at:
        if has_open_tasks(text):
            return AuditDecision(
                item=item,
                outcome="manual_review",
                old_status="In progress",
                new_status=None,
                reason="Merged PR still contains open task markers.",
                evidence="completion is not fully clear from the tracked content",
            )
        if has_recent_ongoing_signal(comments):
            return AuditDecision(
                item=item,
                outcome="manual_review",
                old_status="In progress",
                new_status=None,
                reason="Merged PR has recent comments that still suggest ongoing work.",
                evidence="recent ongoing-work language conflicts with automatic completion",
            )
        return AuditDecision(
            item=item,
            outcome="change",
            old_status="In progress",
            new_status="Done",
            reason="PR is merged with no remaining tracked work signals.",
            evidence=f"merged at {item.content.merged_at or 'unknown time'}",
        )
    return AuditDecision(
        item=item,
        outcome="manual_review",
        old_status="In progress",
        new_status=None,
        reason="Closed PR is not merged.",
        evidence="cannot safely infer completion from a closed non-merged PR",
    )


def evaluate_issue_item(
    client: GitHubClient,
    item: ProjectItem,
    comments: list[dict[str, object]],
) -> AuditDecision:
    text = lower_texts(item.content.body, comments)
    linked_pull_requests = collect_linked_pull_requests(
        client,
        item.content.repository,
        item.content.body,
        comments,
        LINKED_REFERENCE_PATTERNS,
    )
    open_pull_requests = [
        pull_request
        for pull_request in linked_pull_requests
        if str(pull_request.get("state")) == "open" and not pull_request.get("merged_at")
    ]

    if item.content.state == "OPEN":
        return AuditDecision(
            item=item,
            outcome="unchanged",
            old_status="In progress",
            new_status=None,
            reason="Issue is still open.",
            evidence="open tracked work should remain In progress",
        )

    if open_pull_requests:
        return AuditDecision(
            item=item,
            outcome="unchanged",
            old_status="In progress",
            new_status=None,
            reason="Linked pull request work is still open.",
            evidence=summarize_pull_request_states(open_pull_requests),
        )

    if has_recent_ongoing_signal(comments) or matches_any(text, ONGOING_WORK_PATTERNS):
        return AuditDecision(
            item=item,
            outcome="manual_review",
            old_status="In progress",
            new_status=None,
            reason="Closed issue still contains ongoing-work signals.",
            evidence="recent comments or tracked text conflict with automatic completion",
        )

    if has_open_tasks(text):
        return AuditDecision(
            item=item,
            outcome="manual_review",
            old_status="In progress",
            new_status=None,
            reason="Closed issue still contains open tasks.",
            evidence="unchecked task list items remain in the tracked content",
        )

    merged_pull_requests = [
        pull_request for pull_request in linked_pull_requests if pull_request.get("merged_at")
    ]
    has_completion_evidence = bool(merged_pull_requests) or matches_any(text, COMPLETION_PATTERNS)

    if not has_completion_evidence:
        return AuditDecision(
            item=item,
            outcome="manual_review",
            old_status="In progress",
            new_status=None,
            reason="Closed issue lacks strong completion evidence.",
            evidence="no merged linked PR and no explicit completion signal found",
        )

    if len(linked_pull_requests) > 1 and len(merged_pull_requests) != len(linked_pull_requests):
        return AuditDecision(
            item=item,
            outcome="manual_review",
            old_status="In progress",
            new_status=None,
            reason="Multiple linked pull requests have mixed end states.",
            evidence=summarize_pull_request_states(linked_pull_requests),
        )

    evidence = "closed issue with explicit completion evidence"
    if merged_pull_requests:
        evidence = summarize_pull_request_states(merged_pull_requests)
    return AuditDecision(
        item=item,
        outcome="change",
        old_status="In progress",
        new_status="Done",
        reason="Closed issue is backed by clear completion evidence.",
        evidence=evidence,
    )


def evaluate_item(
    client: GitHubClient,
    item: ProjectItem,
) -> tuple[AuditDecision, list[dict[str, object]]]:
    comments = client.get_issue_comments(item.content.repository, item.content.number)
    if item.content.kind == "PullRequest":
        return evaluate_pull_request_item(item, comments), comments
    return evaluate_issue_item(client, item, comments), comments


def format_items(items: list[ProjectItem]) -> list[str]:
    if not items:
        return ["- none"]
    return [f"- [{item.content.title}]({item.content.url})" for item in items]


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
        "# Project In-Progress Hygiene",
        "",
        f"- Dry-run: `{'true' if dry_run else 'false'}`",
        f"- Generated: `{datetime.now(UTC).isoformat()}`",
        "",
        "## Audited `In progress` Items",
        "",
        *format_items(report.in_progress_items),
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
        if item.status != "In progress":
            continue
        report.in_progress_items.append(item)
        decision, comments = evaluate_item(client, item)
        if decision.outcome == "change" and decision.new_status:
            decision.comment_body = build_audit_comment(
                AUTOMATION_MARKER,
                "Project in-progress hygiene audit",
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
        print(f"project_inprogress_hygiene failed: {exc}", file=sys.stderr)
        raise
