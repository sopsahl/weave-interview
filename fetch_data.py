#!/usr/bin/env python3
"""Fetch PR and issue data from PostHog/posthog using gh api graphql."""

import json
import os
import subprocess
import sys

BOT_LOGINS = {"dependabot", "github-actions"}

def is_bot(login: str) -> bool:
    if not login:
        return True
    return login.lower() in BOT_LOGINS or "[bot]" in login.lower()

PR_QUERY = """
query($cursor: String) {
  search(query: "repo:PostHog/posthog is:pr is:merged merged:>2025-12-11", type: ISSUE, first: 100, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number
        title
        author { login }
        createdAt
        mergedAt
        additions
        deletions
        changedFiles
        labels(first: 10) { nodes { name } }
        reviews(first: 50) {
          nodes {
            author { login }
            state
            submittedAt
            body
          }
        }
      }
    }
  }
}
"""

ISSUE_QUERY = """
query($cursor: String) {
  search(query: "repo:PostHog/posthog is:issue is:closed closed:>2025-12-11", type: ISSUE, first: 100, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on Issue {
        number
        title
        author { login }
        closedAt
        labels(first: 10) { nodes { name } }
        assignees(first: 10) { nodes { login } }
      }
    }
  }
}
"""


def run_graphql(query: str, cursor: str = None, retries: int = 3) -> dict:
    """Run a GraphQL query via gh api graphql with retry on transient errors."""
    import time
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    if cursor:
        cmd += ["-F", f"cursor={cursor}"]
    else:
        cmd += ["-F", "cursor=null"]

    for attempt in range(retries):
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return json.loads(result.stdout)
        err = result.stderr.strip()
        transient = any(s in err.lower() for s in ["502", "503", "504", "500", "timeout", "cancel", "stream error", "connection", "http 5"])
        if transient and attempt < retries - 1:
            wait = 2 ** (attempt + 1)
            print(f"  Retrying in {wait}s after error: {err}")
            time.sleep(wait)
            continue
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


def parse_pr_nodes(nodes: list) -> list:
    """Parse PR nodes from GraphQL response, filtering bots."""
    prs = []
    for node in nodes:
        if not node:
            continue
        author_login = (node.get("author") or {}).get("login", "")
        if is_bot(author_login):
            continue

        reviews = []
        for r in (node.get("reviews") or {}).get("nodes", []):
            if not r:
                continue
            r_login = (r.get("author") or {}).get("login", "")
            if is_bot(r_login):
                continue
            reviews.append({
                "author": r_login,
                "state": r.get("state", ""),
                "submittedAt": r.get("submittedAt", ""),
                "bodyLength": len(r.get("body", "") or ""),
            })

        prs.append({
            "number": node["number"],
            "title": node.get("title", ""),
            "author": author_login,
            "createdAt": node.get("createdAt", ""),
            "mergedAt": node.get("mergedAt", ""),
            "additions": node.get("additions", 0),
            "deletions": node.get("deletions", 0),
            "changedFiles": node.get("changedFiles", 0),
            "labels": [l["name"] for l in (node.get("labels") or {}).get("nodes", [])],
            "reviews": reviews,
        })
    return prs


# GitHub search caps at 1000 results, so we split into 2-week windows
DATE_WINDOWS = [
    ("2025-12-11", "2025-12-25"),
    ("2025-12-25", "2026-01-08"),
    ("2026-01-08", "2026-01-22"),
    ("2026-01-22", "2026-02-05"),
    ("2026-02-05", "2026-02-19"),
    ("2026-02-19", "2026-03-05"),
    ("2026-03-05", "2026-03-12"),
]

PR_QUERY_TEMPLATE = """
query($cursor: String) {{
  search(query: "repo:PostHog/posthog is:pr is:merged merged:{start}..{end}", type: ISSUE, first: 100, after: $cursor) {{
    pageInfo {{ hasNextPage endCursor }}
    nodes {{
      ... on PullRequest {{
        number
        title
        author {{ login }}
        createdAt
        mergedAt
        additions
        deletions
        changedFiles
        labels(first: 10) {{ nodes {{ name }} }}
        reviews(first: 50) {{
          nodes {{
            author {{ login }}
            state
            submittedAt
            body
          }}
        }}
      }}
    }}
  }}
}}
"""


def fetch_prs() -> list:
    """Fetch all merged PRs using date windows to avoid the 1000-result cap."""
    # Resume from cached data if available
    cache_path = "data/raw_prs_partial.json"
    all_prs = []
    seen_numbers = set()
    completed_windows = set()

    if os.path.exists(cache_path):
        with open(cache_path) as f:
            cache = json.load(f)
        all_prs = cache.get("prs", [])
        seen_numbers = {pr["number"] for pr in all_prs}
        completed_windows = set(cache.get("completed_windows", []))
        print(f"Resuming from cache: {len(all_prs)} PRs, {len(completed_windows)} windows done")

    for start, end in DATE_WINDOWS:
        window_key = f"{start}..{end}"
        if window_key in completed_windows:
            print(f"Skipping {window_key} (already cached)")
            continue
        query = PR_QUERY_TEMPLATE.format(start=start, end=end)
        cursor = None
        page = 0

        while True:
            page += 1
            print(f"Fetching PRs {start}..{end} page {page}... (total so far: {len(all_prs)})")
            data = run_graphql(query, cursor)
            search = data["data"]["search"]

            for pr in parse_pr_nodes(search["nodes"]):
                if pr["number"] not in seen_numbers:
                    seen_numbers.add(pr["number"])
                    all_prs.append(pr)

            if not search["pageInfo"]["hasNextPage"]:
                break
            cursor = search["pageInfo"]["endCursor"]

        completed_windows.add(window_key)
        # Save progress after each window
        with open(cache_path, "w") as f:
            json.dump({"prs": all_prs, "completed_windows": list(completed_windows)}, f)

    # Clean up cache
    if os.path.exists(cache_path):
        os.remove(cache_path)

    print(f"Done fetching PRs: {len(all_prs)} total (after bot filtering)")
    return all_prs


def fetch_issues() -> list:
    """Fetch all closed issues with pagination."""
    all_issues = []
    cursor = None
    page = 0

    while True:
        page += 1
        print(f"Fetching issues page {page}... (total so far: {len(all_issues)})")
        data = run_graphql(ISSUE_QUERY, cursor)
        search = data["data"]["search"]

        for node in search["nodes"]:
            if not node:
                continue
            author_login = (node.get("author") or {}).get("login", "")
            if is_bot(author_login):
                continue

            all_issues.append({
                "number": node["number"],
                "title": node.get("title", ""),
                "author": author_login,
                "closedAt": node.get("closedAt", ""),
                "labels": [l["name"] for l in (node.get("labels") or {}).get("nodes", [])],
                "assignees": [a["login"] for a in (node.get("assignees") or {}).get("nodes", [])],
            })

        if not search["pageInfo"]["hasNextPage"]:
            break
        cursor = search["pageInfo"]["endCursor"]

    print(f"Done fetching issues: {len(all_issues)} total (after bot filtering)")
    return all_issues


def main():
    os.makedirs("data", exist_ok=True)

    print("=== Fetching PRs ===")
    prs = fetch_prs()
    with open("data/raw_prs.json", "w") as f:
        json.dump(prs, f, indent=2)
    print(f"Saved {len(prs)} PRs to data/raw_prs.json\n")

    print("=== Fetching Issues ===")
    issues = fetch_issues()
    with open("data/raw_issues.json", "w") as f:
        json.dump(issues, f, indent=2)
    print(f"Saved {len(issues)} issues to data/raw_issues.json")


if __name__ == "__main__":
    main()
