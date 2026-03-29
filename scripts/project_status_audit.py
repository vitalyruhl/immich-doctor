#!/usr/bin/env python3
"""Conservative GitHub Project status audit for Blocked and Validation items."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

DEFAULT_PROJECT_TITLE = "Backup Execution Roadmap"
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
class ContentRef:
    kind: str
    number: int
    title: str
    url: str
    state: str
    body: str
    closed_at: str | None = None
    merged_at: str | None = None
    repository: str = ""


@dataclass(slots=True)
class ProjectItem:
    id: str
    status: str
    content: ContentRef
    updated_at: str | None = None


@dataclass(slots=True)
class AuditDecision:
    item: ProjectItem
    outcome: str
    old_status: str
    new_status: str | None
    reason: str
    evidence: str
    comment_body: str | None = None


@dataclass(slots=True)
class AuditReport:
    blocked_items: list[ProjectItem] = field(default_factory=list)
    validation_items: list[ProjectItem] = field(default_factory=list)
    changed: list[AuditDecision] = field(default_factory=list)
    unchanged: list[AuditDecision] = field(default_factory=list)
    manual_review: list[AuditDecision] = field(default_factory=list)


class GitHubClient:
    def __init__(self, token: str) -> None:
        self.token = token
        self.api_base = "https://api.github.com"
        self.graphql_url = "https://api.github.com/graphql"
        self._reference_cache: dict[tuple[str, int], dict[str, Any]] = {}

    def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        data: dict[str, Any] | None = None,
    ) -> Any:
        payload = None
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "immich-doctor-project-status-audit",
        }
        if data is not None:
            payload = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, method=method, headers=headers, data=payload)
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        response = self._request(
            self.graphql_url,
            method="POST",
            data={"query": query, "variables": variables},
        )
        if "errors" in response:
            raise RuntimeError(f"GraphQL request failed: {response['errors']}")
        return response["data"]

    def rest(self, path: str, *, method: str = "GET", data: dict[str, Any] | None = None) -> Any:
        return self._request(f"{self.api_base}{path}", method=method, data=data)

    def get_project(
        self,
        owner: str,
        repo_name: str,
        title: str,
        project_number: int | None,
    ) -> dict[str, Any]:
        query = """
        query($owner: String!, $repo: String!, $query: String!) {
          repository(owner: $owner, name: $repo) {
            owner {
              __typename
              login
              ... on User {
                projectsV2(first: 20, query: $query) {
                  nodes { id number title url }
                }
              }
              ... on Organization {
                projectsV2(first: 20, query: $query) {
                  nodes { id number title url }
                }
              }
            }
          }
        }
        """
        data = self.graphql(query, {"owner": owner, "repo": repo_name, "query": title})
        repository = data.get("repository")
        if not repository:
            raise RuntimeError(f"Repository {owner}/{repo_name} could not be resolved")
        project_owner = repository["owner"]
        projects = project_owner["projectsV2"]["nodes"]
        if project_number is not None:
            for project in projects:
                if project["number"] == project_number:
                    return project
            raise RuntimeError(f"Project number {project_number} not found for owner {owner}")
        matches = [project for project in projects if project["title"] == title]
        if len(matches) != 1:
            raise RuntimeError(
                f"Expected exactly one project titled '{title}' for owner {owner}, "
                f"found {len(matches)}"
            )
        return matches[0]

    def get_project_fields(self, project_id: str) -> dict[str, dict[str, str]]:
        query = """
        query($projectId: ID!) {
          node(id: $projectId) {
            ... on ProjectV2 {
              fields(first: 50) {
                nodes {
                  ... on ProjectV2SingleSelectField {
                    id
                    name
                    options { id name }
                  }
                }
              }
            }
          }
        }
        """
        data = self.graphql(query, {"projectId": project_id})
        fields = data["node"]["fields"]["nodes"]
        field_map: dict[str, dict[str, str]] = {}
        for single_select_field in fields:
            if not single_select_field:
                continue
            field_map[single_select_field["name"]] = {"id": single_select_field["id"]}
            for option in single_select_field["options"]:
                field_map[single_select_field["name"]][option["name"]] = option["id"]
        return field_map

    def iter_project_items(self, project_id: str) -> Iterable[ProjectItem]:
        query = """
        query($projectId: ID!, $cursor: String) {
          node(id: $projectId) {
            ... on ProjectV2 {
              items(first: 50, after: $cursor) {
                pageInfo { hasNextPage endCursor }
                nodes {
                  id
                  updatedAt
                  fieldValueByName(name: "Status") {
                    ... on ProjectV2ItemFieldSingleSelectValue {
                      name
                    }
                  }
                  content {
                    __typename
                    ... on Issue {
                      number
                      title
                      url
                      state
                      body
                      closedAt
                      repository { nameWithOwner }
                    }
                    ... on PullRequest {
                      number
                      title
                      url
                      state
                      body
                      closedAt
                      mergedAt
                      repository { nameWithOwner }
                    }
                  }
                }
              }
            }
          }
        }
        """
        cursor = None
        while True:
            data = self.graphql(query, {"projectId": project_id, "cursor": cursor})
            items = data["node"]["items"]
            for node in items["nodes"]:
                content = node.get("content")
                status_value = node.get("fieldValueByName")
                if not content or not status_value:
                    continue
                yield ProjectItem(
                    id=node["id"],
                    status=status_value["name"],
                    updated_at=node.get("updatedAt"),
                    content=ContentRef(
                        kind=content["__typename"],
                        number=content["number"],
                        title=content["title"],
                        url=content["url"],
                        state=content["state"],
                        body=content.get("body") or "",
                        closed_at=content.get("closedAt"),
                        merged_at=content.get("mergedAt"),
                        repository=content["repository"]["nameWithOwner"],
                    ),
                )
            if not items["pageInfo"]["hasNextPage"]:
                break
            cursor = items["pageInfo"]["endCursor"]

    def get_issue_comments(self, repo: str, number: int) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"per_page": 100, "sort": "updated", "direction": "desc"})
        return self.rest(f"/repos/{repo}/issues/{number}/comments?{query}")

    def get_pull_request(self, repo: str, number: int) -> dict[str, Any]:
        cache_key = (repo, number)
        cached = self._reference_cache.get(cache_key)
        if cached is not None:
            return cached
        reference = self.rest(f"/repos/{repo}/pulls/{number}")
        self._reference_cache[cache_key] = reference
        return reference

    def post_issue_comment(self, repo: str, number: int, body: str) -> None:
        self.rest(f"/repos/{repo}/issues/{number}/comments", method="POST", data={"body": body})

    def update_project_status(
        self,
        project_id: str,
        item_id: str,
        field_id: str,
        option_id: str,
    ) -> None:
        mutation = """
        mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
          updateProjectV2ItemFieldValue(
            input: {
              projectId: $projectId,
              itemId: $itemId,
              fieldId: $fieldId,
              value: { singleSelectOptionId: $optionId }
            }
          ) {
            projectV2Item { id }
          }
        }
        """
        self.graphql(
            mutation,
            {
                "projectId": project_id,
                "itemId": item_id,
                "fieldId": field_id,
                "optionId": option_id,
            },
        )


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
        default=_env_truthy("PROJECT_STATUS_AUDIT_DRY_RUN"),
    )
    parser.add_argument("--summary-file", default=os.getenv("GITHUB_STEP_SUMMARY"))
    args = parser.parse_args()
    if not args.repo:
        parser.error("--repo is required")
    if not args.project_owner:
        args.project_owner = args.repo.split("/", 1)[0]
    return args


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def build_run_url() -> str | None:
    server = os.getenv("GITHUB_SERVER_URL")
    repo = os.getenv("GITHUB_REPOSITORY")
    run_id = os.getenv("GITHUB_RUN_ID")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return None


def lower_texts(body: str, comments: list[dict[str, Any]]) -> str:
    parts = [body]
    parts.extend(comment.get("body") or "" for comment in comments)
    return "\n".join(parts).lower()


def matches_any(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text, flags=re.I | re.S) for pattern in patterns)


def extract_linked_pr_numbers(text: str) -> list[int]:
    numbers: list[int] = []
    for pattern in LINKED_REFERENCE_PATTERNS:
        for match in pattern.finditer(text):
            numbers.append(int(match.group(1)))
    return numbers


def infer_reference_pr(
    client: GitHubClient,
    repo: str,
    body: str,
    comments: list[dict[str, Any]],
) -> dict[str, Any] | None:
    combined = "\n".join([body, *(comment.get("body") or "" for comment in comments)])
    for number in extract_linked_pr_numbers(combined):
        try:
            pull_request = client.get_pull_request(repo, number)
        except urllib.error.HTTPError:
            continue
        if pull_request.get("merged_at"):
            return pull_request
    return None


def has_duplicate_audit_comment(
    comments: list[dict[str, Any]],
    old_status: str,
    new_status: str,
) -> bool:
    marker = f"{AUTOMATION_MARKER} from={old_status} to={new_status} -->"
    return any(marker in (comment.get("body") or "") for comment in comments)


def build_audit_comment(decision: AuditDecision, run_url: str | None) -> str:
    lines = [
        f"{AUTOMATION_MARKER} from={decision.old_status} to={decision.new_status} -->",
        "Project status audit",
        "",
        f"- Transition: `{decision.old_status}` -> `{decision.new_status}`",
        f"- Reason: {decision.reason}",
        f"- Evidence: {decision.evidence}",
    ]
    if run_url:
        lines.append(f"- Workflow run: {run_url}")
    return "\n".join(lines)


def evaluate_validation_issue(
    client: GitHubClient,
    item: ProjectItem,
    comments: list[dict[str, Any]],
) -> AuditDecision:
    text = lower_texts(item.content.body, comments)
    linked_pr = infer_reference_pr(client, item.content.repository, item.content.body, comments)
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
    comments: list[dict[str, Any]],
) -> AuditDecision:
    text = lower_texts(item.content.body, comments)
    linked_pr = infer_reference_pr(client, item.content.repository, item.content.body, comments)
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
    comments: list[dict[str, Any]],
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
    linked_pr = infer_reference_pr(client, item.content.repository, item.content.body, comments)
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
    comments: list[dict[str, Any]],
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
    linked_pr = infer_reference_pr(client, item.content.repository, item.content.body, comments)
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
) -> tuple[AuditDecision, list[dict[str, Any]]]:
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


def write_summary(report: AuditReport, summary_file: str | None, dry_run: bool) -> None:
    lines = [
        "# Project Status Audit",
        "",
        f"- Dry-run: `{'true' if dry_run else 'false'}`",
        f"- Generated: `{datetime.now(UTC).isoformat()}`",
        "",
        "## Audited `Blocked` Items",
        "",
    ]
    lines.extend(format_items(report.blocked_items))
    lines.extend(["", "## Audited `Validation` Items", ""])
    lines.extend(format_items(report.validation_items))
    lines.extend(["", "## Changed Items", ""])
    lines.extend(format_decisions(report.changed, include_transition=True))
    lines.extend(["", "## Unchanged Items", ""])
    lines.extend(format_decisions(report.unchanged))
    lines.extend(["", "## Manual Review Required", ""])
    lines.extend(format_decisions(report.manual_review))
    summary = "\n".join(lines) + "\n"
    print(summary)
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as handle:
            handle.write(summary)


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
    lines = []
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


def load_token() -> str:
    for name in ("PROJECT_STATUS_AUDIT_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        token = os.getenv(name)
        if token:
            return token
    raise RuntimeError(
        "A GitHub token is required via PROJECT_STATUS_AUDIT_TOKEN, GITHUB_TOKEN, or GH_TOKEN"
    )


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
            decision.comment_body = build_audit_comment(decision, run_url)
            if not args.dry_run:
                client.update_project_status(
                    project["id"],
                    item.id,
                    status_field["id"],
                    status_field[decision.new_status],
                )
                if not has_duplicate_audit_comment(
                    comments, decision.old_status, decision.new_status
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
