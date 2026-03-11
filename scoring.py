#!/usr/bin/env python3
"""Score engineers based on PR and issue data from PostHog/posthog."""

import json
import re
import sys
from collections import defaultdict


# Minimum merged PRs to qualify
MIN_PR_THRESHOLD = 5

# Metric weights within categories
METRIC_WEIGHTS = {
    "collaboration": {
        "reviews_given": 0.25,
        "review_comments": 0.20,
        "approvals_given": 0.20,
        "unique_prs_reviewed": 0.35,
    },
    "ownership": {
        "bug_fix_prs": 0.30,
        "issues_involved": 0.25,
        "unique_areas_touched": 0.25,
        "chore_prs": 0.20,
    },
    "output": {
        "prs_merged": 0.40,
        "total_additions": 0.15,
        "total_deletions": 0.10,
        "avg_pr_size": 0.35,
    },
}

# Category weights
DEFAULT_CATEGORY_WEIGHTS = {
    "collaboration": 0.35,
    "ownership": 0.30,
    "output": 0.35,
}

SCOPE_RE = re.compile(r"^(?:feat|fix|chore|refactor|perf|test|ci|docs|style|build)\(([^)]+)\)")


def extract_scope(title: str) -> str | None:
    """Extract scope from conventional commit title like feat(scope): ..."""
    m = SCOPE_RE.match(title.lower().strip())
    return m.group(1) if m else None


def is_bug_fix(title: str) -> bool:
    t = title.lower().strip()
    return t.startswith("fix:") or t.startswith("fix(")


def is_chore(title: str) -> bool:
    t = title.lower().strip()
    return t.startswith("chore:") or t.startswith("chore(")


def compute_raw_metrics(prs: list, issues: list) -> dict:
    """Compute raw metrics for each engineer."""
    metrics = defaultdict(lambda: {
        "prs_merged": 0,
        "total_additions": 0,
        "total_deletions": 0,
        "pr_sizes": [],
        "reviews_given": 0,
        "review_comments": 0,
        "approvals_given": 0,
        "prs_reviewed": set(),
        "bug_fix_prs": 0,
        "issues_involved": set(),
        "areas_touched": set(),
        "chore_prs": 0,
    })

    for pr in prs:
        author = pr["author"]
        if not author:
            continue

        m = metrics[author]
        m["prs_merged"] += 1
        m["total_additions"] += pr.get("additions", 0)
        m["total_deletions"] += pr.get("deletions", 0)
        m["pr_sizes"].append(pr.get("additions", 0) + pr.get("deletions", 0))

        if is_bug_fix(pr.get("title", "")):
            m["bug_fix_prs"] += 1
        if is_chore(pr.get("title", "")):
            m["chore_prs"] += 1

        scope = extract_scope(pr.get("title", ""))
        if scope:
            m["areas_touched"].add(scope)

        # Process reviews on this PR
        for review in pr.get("reviews", []):
            reviewer = review.get("author", "")
            if not reviewer or reviewer == author:
                continue
            rm = metrics[reviewer]
            rm["reviews_given"] += 1
            rm["prs_reviewed"].add(pr["number"])
            if review.get("bodyLength", 0) > 0:
                rm["review_comments"] += 1
            if review.get("state") == "APPROVED":
                rm["approvals_given"] += 1

    # Process issues
    for issue in issues:
        author = issue.get("author", "")
        if author:
            metrics[author]["issues_involved"].add(issue["number"])
        for assignee in issue.get("assignees", []):
            if assignee:
                metrics[assignee]["issues_involved"].add(issue["number"])

    # Convert to serializable form
    result = {}
    for login, m in metrics.items():
        result[login] = {
            "prs_merged": m["prs_merged"],
            "total_additions": m["total_additions"],
            "total_deletions": m["total_deletions"],
            "avg_pr_size": round(sum(m["pr_sizes"]) / len(m["pr_sizes"]), 2) if m["pr_sizes"] else 0,
            "reviews_given": m["reviews_given"],
            "review_comments": m["review_comments"],
            "approvals_given": m["approvals_given"],
            "unique_prs_reviewed": len(m["prs_reviewed"]),
            "bug_fix_prs": m["bug_fix_prs"],
            "issues_involved": len(m["issues_involved"]),
            "unique_areas_touched": len(m["areas_touched"]),
            "chore_prs": m["chore_prs"],
        }
    return result


def min_max_normalize(engineers: dict, metric: str) -> dict:
    """Return {login: normalized_value} for a single metric."""
    values = [e[metric] for e in engineers.values()]
    mn, mx = min(values), max(values)
    rng = mx - mn
    if rng == 0:
        return {login: 0.0 for login in engineers}
    return {login: round((e[metric] - mn) / rng, 6) for login, e in engineers.items()}


def main():
    # Load data
    try:
        with open("data/raw_prs.json") as f:
            prs = json.load(f)
        with open("data/raw_issues.json") as f:
            issues = json.load(f)
    except FileNotFoundError as e:
        print(f"Error: {e}. Run fetch_data.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(prs)} PRs and {len(issues)} issues")

    # Compute raw metrics
    all_metrics = compute_raw_metrics(prs, issues)
    print(f"Total engineers found: {len(all_metrics)}")

    # Filter to qualifying engineers
    qualifying = {k: v for k, v in all_metrics.items() if v["prs_merged"] >= MIN_PR_THRESHOLD}
    print(f"Qualifying engineers (>={MIN_PR_THRESHOLD} PRs): {len(qualifying)}")

    # Normalize each metric
    all_metric_names = [
        "prs_merged", "total_additions", "total_deletions", "avg_pr_size",
        "reviews_given", "review_comments", "approvals_given", "unique_prs_reviewed",
        "bug_fix_prs", "issues_involved", "unique_areas_touched", "chore_prs",
    ]

    normalized = {login: {} for login in qualifying}
    for metric_name in all_metric_names:
        norm_values = min_max_normalize(qualifying, metric_name)
        for login, val in norm_values.items():
            normalized[login][metric_name] = val

    # Compute category and composite scores
    engineers_output = []
    for login in qualifying:
        category_scores = {}
        for category, weights in METRIC_WEIGHTS.items():
            score = sum(normalized[login][m] * w for m, w in weights.items())
            category_scores[category] = round(score, 6)

        composite = sum(category_scores[cat] * w for cat, w in DEFAULT_CATEGORY_WEIGHTS.items())

        engineers_output.append({
            "login": login,
            "raw_metrics": qualifying[login],
            "normalized_metrics": normalized[login],
            "category_scores": category_scores,
            "composite_score": round(composite, 6),
        })

    # Sort by composite score descending
    engineers_output.sort(key=lambda x: x["composite_score"], reverse=True)

    output = {
        "metadata": {
            "date_range": "2025-12-11 to 2026-03-11",
            "total_prs": len(prs),
            "total_engineers": len(all_metrics),
            "qualifying_engineers": len(qualifying),
            "min_pr_threshold": MIN_PR_THRESHOLD,
        },
        "metric_weights": METRIC_WEIGHTS,
        "default_category_weights": DEFAULT_CATEGORY_WEIGHTS,
        "engineers": engineers_output,
    }

    with open("data/scored_engineers.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved scored data to data/scored_engineers.json")
    print(f"\nTop 10 engineers by composite score:")
    for i, eng in enumerate(engineers_output[:10], 1):
        print(f"  {i}. {eng['login']}: {eng['composite_score']:.4f} "
              f"(collab={eng['category_scores']['collaboration']:.3f}, "
              f"own={eng['category_scores']['ownership']:.3f}, "
              f"out={eng['category_scores']['output']:.3f})")


if __name__ == "__main__":
    main()
