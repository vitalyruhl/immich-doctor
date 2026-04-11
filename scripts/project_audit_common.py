#!/usr/bin/env python3
"""Shared helpers for GitHub Project status hygiene scripts."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

DEFAULT_PROJECT_TITLE = "Backup-Doctor Projekt"
DEFAULT_PROJECT_NUMBER = 3


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
    updated_at: str | None = None
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


class GitHubClient:
    def __init__(self, token: str) -> None:
        self.token = token
        self.api_base = "https://api.github.com"
        self.graphql_url = "https://api.github.com/graphql"
        self._pull_request_cache: dict[tuple[str, int], dict[str, Any]] = {}

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
            "User-Agent": "immich-doctor-project-audit",
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
        query($owner: String!, $repo: String!) {
          repository(owner: $owner, name: $repo) {
            owner {
              __typename
              login
              ... on User {
                projectsV2(first: 100) {
                  nodes { id number title url }
                }
              }
              ... on Organization {
                projectsV2(first: 100) {
                  nodes { id number title url }
                }
              }
            }
          }
        }
        """
        data = self.graphql(query, {"owner": owner, "repo": repo_name})
        repository = data.get("repository")
        if not repository:
            raise RuntimeError(f"Repository {owner}/{repo_name} could not be resolved")
        project_owner = repository["owner"]
        projects = project_owner["projectsV2"]["nodes"]
        if project_number is not None:
            for project in projects:
                if project["number"] == project_number:
                    return project
            available = ", ".join(
                f"#{project['number']} {project['title']}" for project in projects
            ) or "none"
            raise RuntimeError(
                f"Project number {project_number} not found for owner {owner}. "
                f"Available projects: {available}"
            )
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
        field_map: dict[str, dict[str, str]] = {}
        for single_select_field in data["node"]["fields"]["nodes"]:
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
                      updatedAt
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
                      updatedAt
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
            page = data["node"]["items"]
            for node in page["nodes"]:
                content = node.get("content")
                status_value = node.get("fieldValueByName")
                if not content:
                    continue
                yield ProjectItem(
                    id=node["id"],
                    status=(status_value or {}).get("name") or "",
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
                        updated_at=content.get("updatedAt"),
                        repository=content["repository"]["nameWithOwner"],
                    ),
                )
            if not page["pageInfo"]["hasNextPage"]:
                break
            cursor = page["pageInfo"]["endCursor"]

    def get_issue_comments(self, repo: str, number: int) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"per_page": 100, "sort": "updated", "direction": "desc"})
        return self.rest(f"/repos/{repo}/issues/{number}/comments?{query}")

    def get_pull_request(self, repo: str, number: int) -> dict[str, Any]:
        cache_key = (repo, number)
        if cache_key not in self._pull_request_cache:
            self._pull_request_cache[cache_key] = self.rest(f"/repos/{repo}/pulls/{number}")
        return self._pull_request_cache[cache_key]

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


def env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def load_token() -> str:
    for name in ("PROJECT_STATUS_AUDIT_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        token = os.getenv(name)
        if token:
            return token
    raise RuntimeError(
        "A GitHub token is required via PROJECT_STATUS_AUDIT_TOKEN, GITHUB_TOKEN, or GH_TOKEN"
    )


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


def extract_linked_pr_numbers(text: str, patterns: Iterable[re.Pattern[str]]) -> list[int]:
    numbers: list[int] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            numbers.append(int(match.group(1)))
    return numbers


def collect_linked_pull_requests(
    client: GitHubClient,
    repo: str,
    body: str,
    comments: list[dict[str, Any]],
    patterns: Iterable[re.Pattern[str]],
) -> list[dict[str, Any]]:
    combined = "\n".join([body, *(comment.get("body") or "" for comment in comments)])
    pull_requests: list[dict[str, Any]] = []
    seen: set[int] = set()
    for number in extract_linked_pr_numbers(combined, patterns):
        if number in seen:
            continue
        seen.add(number)
        try:
            pull_requests.append(client.get_pull_request(repo, number))
        except urllib.error.HTTPError:
            continue
    return pull_requests


def has_duplicate_audit_comment(
    comments: list[dict[str, Any]],
    marker: str,
    old_status: str,
    new_status: str,
) -> bool:
    expected = f"{marker} from={old_status} to={new_status} -->"
    return any(expected in (comment.get("body") or "") for comment in comments)


def build_audit_comment(
    marker: str,
    title: str,
    decision: AuditDecision,
    run_url: str | None,
) -> str:
    lines = [
        f"{marker} from={decision.old_status} to={decision.new_status} -->",
        title,
        "",
        f"- Transition: `{decision.old_status}` -> `{decision.new_status}`",
        f"- Reason: {decision.reason}",
        f"- Evidence: {decision.evidence}",
    ]
    if run_url:
        lines.append(f"- Workflow run: {run_url}")
    return "\n".join(lines)


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).astimezone(UTC)


def is_recent(value: str | None, *, days: int) -> bool:
    timestamp = parse_timestamp(value)
    if not timestamp:
        return False
    return timestamp >= datetime.now(UTC) - timedelta(days=days)
