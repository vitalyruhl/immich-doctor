#!/usr/bin/env python3
"""Assign default Project Status for items that still have no status."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

from project_audit_common import (
    DEFAULT_PROJECT_NUMBER,
    DEFAULT_PROJECT_TITLE,
    GitHubClient,
    ProjectItem,
    env_truthy,
    load_token,
)


@dataclass(slots=True)
class HygieneDecision:
    item: ProjectItem
    outcome: str
    old_status: str
    new_status: str | None
    reason: str


@dataclass(slots=True)
class HygieneReport:
    scoped_items: list[ProjectItem] = field(default_factory=list)
    changed: list[HygieneDecision] = field(default_factory=list)
    unchanged: list[HygieneDecision] = field(default_factory=list)


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
    parser.add_argument(
        "--content-url",
        default=(os.getenv("PROJECT_STATUS_AUDIT_CONTENT_URL") or "").strip() or None,
        help="Optional Issue/PR URL to scope processing to one tracked content item.",
    )
    args = parser.parse_args()
    if not args.repo:
        parser.error("--repo is required")
    if not args.project_owner:
        args.project_owner = args.repo.split("/", 1)[0]
    return args


def evaluate_item(item: ProjectItem) -> HygieneDecision:
    if item.status:
        return HygieneDecision(
            item=item,
            outcome="unchanged",
            old_status=item.status,
            new_status=None,
            reason="Item already has a Status value.",
        )
    if item.content.state != "OPEN":
        return HygieneDecision(
            item=item,
            outcome="unchanged",
            old_status="",
            new_status=None,
            reason="Item has no Status but content is not OPEN.",
        )
    return HygieneDecision(
        item=item,
        outcome="change",
        old_status="",
        new_status="Planned",
        reason="OPEN item has empty Status and should receive default Planned.",
    )


def format_items(items: list[ProjectItem]) -> list[str]:
    if not items:
        return ["- none"]
    return [
        f"- [{item.content.title}]({item.content.url}) - "
        f"kind=`{item.content.kind}` status=`{item.status or '(empty)'}`"
        for item in items
    ]


def format_decisions(decisions: list[HygieneDecision], include_transition: bool) -> list[str]:
    if not decisions:
        return ["- none"]
    lines: list[str] = []
    for decision in decisions:
        title = f"[{decision.item.content.title}]({decision.item.content.url})"
        if include_transition and decision.new_status:
            lines.append(
                f"- {title}: `{decision.old_status or '(empty)'}` -> `{decision.new_status}`. "
                f"{decision.reason}"
            )
        else:
            lines.append(
                f"- {title}: status=`{decision.item.status or '(empty)'}`. {decision.reason}"
            )
    return lines


def write_summary(
    report: HygieneReport,
    summary_file: str | None,
    dry_run: bool,
    content_url: str | None,
) -> None:
    lines = [
        "# Project Default Status Hygiene",
        "",
        f"- Dry-run: `{'true' if dry_run else 'false'}`",
        f"- Scoped content URL: `{content_url or '(none)'}`",
        f"- Generated: `{datetime.now(UTC).isoformat()}`",
        "",
        "## Scoped Items",
        "",
        *format_items(report.scoped_items),
        "",
        "## Changed Items",
        "",
        *format_decisions(report.changed, include_transition=True),
        "",
        "## Unchanged Items",
        "",
        *format_decisions(report.unchanged, include_transition=False),
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
    if not status_field:
        raise RuntimeError("Project Status field could not be resolved")
    if "Planned" not in status_field:
        raise RuntimeError("Project Status option 'Planned' could not be resolved")

    report = HygieneReport()

    for item in client.iter_project_items(project["id"]):
        if args.content_url and item.content.url != args.content_url:
            continue
        report.scoped_items.append(item)
        decision = evaluate_item(item)
        if decision.outcome == "change" and decision.new_status:
            if not args.dry_run:
                client.update_project_status(
                    project["id"],
                    item.id,
                    status_field["id"],
                    status_field[decision.new_status],
                )
            report.changed.append(decision)
        else:
            report.unchanged.append(decision)

    write_summary(report, args.summary_file, args.dry_run, args.content_url)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - top-level workflow failure path
        print(f"project_default_status_hygiene failed: {exc}", file=sys.stderr)
        raise
