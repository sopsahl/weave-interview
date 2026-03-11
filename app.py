import streamlit as st

st.set_page_config(
    page_title="Engineering Impact Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed",
)

import json
import os
import random
import plotly.graph_objects as go
import plotly.express as px

# ---------------------------------------------------------------------------
# Metric metadata
# ---------------------------------------------------------------------------
METRIC_INFO = {
    "reviews_given": ("Reviews Given", "Number of pull request reviews submitted on others' PRs"),
    "review_comments": ("Review Comments", "Reviews that included substantive written feedback"),
    "approvals_given": ("Approvals Given", "Number of PRs explicitly approved"),
    "unique_prs_reviewed": ("Unique PRs Reviewed", "Distinct pull requests reviewed (breadth of review coverage)"),
    "bug_fix_prs": ("Bug Fixes", "PRs with fix: prefix indicating bug resolution"),
    "issues_involved": ("Issues Involved", "GitHub issues authored or assigned to"),
    "unique_areas_touched": ("Areas Touched", "Distinct codebase areas modified (from PR scope tags)"),
    "chore_prs": ("Maintenance PRs", "PRs with chore: prefix (dependency updates, cleanup, etc.)"),
    "prs_merged": ("PRs Merged", "Total pull requests merged in the period"),
    "total_additions": ("Lines Added", "Total lines of code added across all PRs"),
    "total_deletions": ("Lines Removed", "Total lines of code removed across all PRs"),
    "avg_pr_size": ("Avg PR Size", "Average lines changed per PR (additions + deletions)"),
}

CATEGORY_METRICS = {
    "collaboration": ["reviews_given", "review_comments", "approvals_given", "unique_prs_reviewed"],
    "ownership": ["bug_fix_prs", "issues_involved", "unique_areas_touched", "chore_prs"],
    "output": ["prs_merged", "total_additions", "total_deletions", "avg_pr_size"],
}

CATEGORY_COLORS = {
    "collaboration": "#FF6B6B",
    "ownership": "#4ECDC4",
    "output": "#45B7D1",
}

# ---------------------------------------------------------------------------
# Mock data generator (used until real data is wired in)
# ---------------------------------------------------------------------------
# MOCK DATA -- replace with real scored_engineers.json when available


def generate_mock_data() -> dict:
    """Return a synthetic dataset matching the scored_engineers.json schema."""
    random.seed(42)
    logins = [
        "timgl", "mariusandra", "paolodamico", "yakkomajuri", "neilkakkar",
        "EDsCODE", "liyiy", "macobo", "alexkim205", "karlgalway",
        "kpthatsme", "hazzadous", "Twixes", "rcmarron", "sethsahin",
        "jamesefhawkins", "annikaschmid", "benwhit", "daibhin", "samwinslow",
    ]

    metric_weights = {
        "collaboration": {"reviews_given": 0.25, "review_comments": 0.20, "approvals_given": 0.20, "unique_prs_reviewed": 0.35},
        "ownership": {"bug_fix_prs": 0.30, "issues_involved": 0.25, "unique_areas_touched": 0.25, "chore_prs": 0.20},
        "output": {"prs_merged": 0.40, "total_additions": 0.15, "total_deletions": 0.10, "avg_pr_size": 0.35},
    }
    default_category_weights = {"collaboration": 0.35, "ownership": 0.30, "output": 0.35}

    # Raw metric ranges for realistic values
    raw_ranges = {
        "prs_merged": (5, 80), "total_additions": (500, 30000), "total_deletions": (200, 15000),
        "avg_pr_size": (30, 500), "reviews_given": (2, 60), "review_comments": (1, 40),
        "approvals_given": (2, 50), "unique_prs_reviewed": (3, 50), "bug_fix_prs": (0, 25),
        "issues_involved": (0, 20), "unique_areas_touched": (1, 15), "chore_prs": (0, 15),
    }

    engineers = []
    all_raw: dict[str, list[float]] = {m: [] for m in raw_ranges}

    # Generate raw metrics
    for login in logins:
        raw = {}
        for m, (lo, hi) in raw_ranges.items():
            if m == "avg_pr_size":
                raw[m] = round(random.uniform(lo, hi), 1)
            else:
                raw[m] = random.randint(lo, hi)
        all_raw_entry = raw
        for m in raw_ranges:
            all_raw[m].append(all_raw_entry[m])
        engineers.append({"login": login, "raw_metrics": raw})

    # Min-max normalise
    mins = {m: min(vals) for m, vals in all_raw.items()}
    maxs = {m: max(vals) for m, vals in all_raw.items()}

    for eng in engineers:
        norm = {}
        for m in raw_ranges:
            denom = maxs[m] - mins[m] if maxs[m] != mins[m] else 1
            norm[m] = round((eng["raw_metrics"][m] - mins[m]) / denom, 4)
        eng["normalized_metrics"] = norm

        # Category scores
        cat_scores = {}
        for cat, weights in metric_weights.items():
            cat_scores[cat] = round(sum(weights[m] * norm[m] for m in weights), 4)
        eng["category_scores"] = cat_scores

        # Composite
        eng["composite_score"] = round(
            sum(default_category_weights[c] * cat_scores[c] for c in default_category_weights), 4
        )

    engineers.sort(key=lambda e: e["composite_score"], reverse=True)

    return {
        "metadata": {
            "date_range": "2025-12-11 to 2026-03-11",
            "total_prs": 5400,
            "total_engineers": 150,
            "qualifying_engineers": len(logins),
            "min_pr_threshold": 5,
        },
        "metric_weights": metric_weights,
        "default_category_weights": default_category_weights,
        "engineers": engineers,
    }


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "scored_engineers.json")


@st.cache_data
def load_data() -> dict:
    """Load scored_engineers.json if it exists, otherwise fall back to mock data."""
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r") as f:
            return json.load(f)
    return generate_mock_data()


data = load_data()
metadata = data["metadata"]
all_engineers = data["engineers"]
default_weights = data["default_category_weights"]

# ---------------------------------------------------------------------------
# Section 1: Header
# ---------------------------------------------------------------------------
st.markdown(
    "<h1 style='margin-bottom:0'>Engineering Impact Dashboard</h1>"
    "<p style='color:#aaa;margin-top:0;font-size:1.1rem'>PostHog/posthog &middot; Last 90 Days</p>",
    unsafe_allow_html=True,
)

c1, c2, c3 = st.columns(3)
c1.metric("Total PRs Analyzed", f"{metadata['total_prs']:,}")
c2.metric("Qualifying Engineers", metadata["qualifying_engineers"])
c3.metric("Date Range", metadata["date_range"])

st.divider()

# ---------------------------------------------------------------------------
# Section 2: Category weight sliders
# ---------------------------------------------------------------------------
st.subheader("Category Weights")
st.caption("Adjust how much each category contributes to the composite score. Values are auto-normalized to sum to 100%.")

w_col1, w_col2, w_col3 = st.columns(3)
with w_col1:
    w_collab = st.slider("Collaboration", 0, 100, int(default_weights["collaboration"] * 100), key="w_collab")
with w_col2:
    w_owner = st.slider("Ownership", 0, 100, int(default_weights["ownership"] * 100), key="w_owner")
with w_col3:
    w_output = st.slider("Output", 0, 100, int(default_weights["output"] * 100), key="w_output")

raw_sum = w_collab + w_owner + w_output
if raw_sum == 0:
    nw = {"collaboration": 1 / 3, "ownership": 1 / 3, "output": 1 / 3}
else:
    nw = {
        "collaboration": w_collab / raw_sum,
        "ownership": w_owner / raw_sum,
        "output": w_output / raw_sum,
    }

if raw_sum != 100:
    st.info(
        f"Weights sum to {raw_sum}. Effective weights: "
        f"Collaboration {nw['collaboration']:.0%}, "
        f"Ownership {nw['ownership']:.0%}, "
        f"Output {nw['output']:.0%}"
    )

# Recompute composite scores with current weights and re-sort
for eng in all_engineers:
    cs = eng["category_scores"]
    eng["composite_score"] = round(
        nw["collaboration"] * cs["collaboration"]
        + nw["ownership"] * cs["ownership"]
        + nw["output"] * cs["output"],
        4,
    )

ranked = sorted(all_engineers, key=lambda e: e["composite_score"], reverse=True)
top5 = ranked[:5]

st.divider()

# ---------------------------------------------------------------------------
# Section 3: Leaderboard + Stacked bar
# ---------------------------------------------------------------------------
left, right = st.columns([1, 2.5])

with left:
    st.subheader("Top 5 Leaderboard")
    options = [
        f"#{i+1}  {e['login']}  —  {e['composite_score']:.3f}" for i, e in enumerate(top5)
    ]
    selected_label = st.radio(
        "Select an engineer",
        options,
        index=0,
        label_visibility="collapsed",
    )
    selected_index = options.index(selected_label)
    selected_login = top5[selected_index]["login"]

    # Mini sparkline-style category indicators for the selected engineer
    sel = top5[selected_index]
    spark_cols = st.columns(3)
    for idx, cat in enumerate(["collaboration", "ownership", "output"]):
        val = sel["category_scores"][cat]
        color = CATEGORY_COLORS[cat]
        spark_cols[idx].markdown(
            f"<div style='text-align:center'>"
            f"<span style='color:{color};font-weight:bold'>{cat.title()[:5]}</span><br>"
            f"<span style='font-size:1.3rem;color:{color}'>{val:.2f}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

with right:
    st.subheader("Score Breakdown")
    logins_top5 = [e["login"] for e in top5]
    collab_vals = [round(e["category_scores"]["collaboration"] * nw["collaboration"], 4) for e in top5]
    owner_vals = [round(e["category_scores"]["ownership"] * nw["ownership"], 4) for e in top5]
    output_vals = [round(e["category_scores"]["output"] * nw["output"], 4) for e in top5]

    # Build opacity list: selected engineer is fully bright, others are dimmer
    bar_opacity = [1.0 if l == selected_login else 0.55 for l in logins_top5]

    fig_stack = go.Figure()
    for cat, vals, color in [
        ("Collaboration", collab_vals, CATEGORY_COLORS["collaboration"]),
        ("Ownership", owner_vals, CATEGORY_COLORS["ownership"]),
        ("Output", output_vals, CATEGORY_COLORS["output"]),
    ]:
        fig_stack.add_trace(go.Bar(
            y=logins_top5,
            x=vals,
            name=cat,
            orientation="h",
            marker=dict(
                color=color,
                opacity=bar_opacity,
                line=dict(
                    width=[2 if l == selected_login else 0 for l in logins_top5],
                    color="white",
                ),
            ),
            hovertemplate="%{y}: %{x:.3f}<extra>" + cat + "</extra>",
        ))

    fig_stack.update_layout(
        barmode="stack",
        height=300,
        margin=dict(l=0, r=20, t=10, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        xaxis=dict(title="Weighted Score", gridcolor="rgba(255,255,255,0.1)"),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig_stack, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Section 4: Per-metric breakdown (3 columns)
# ---------------------------------------------------------------------------
st.subheader("Per-Metric Breakdown")

TOP_N = 10


def metric_bar_chart(metric_key: str, category: str) -> go.Figure:
    """Create a horizontal bar chart for a single metric showing top N engineers."""
    display_name, description = METRIC_INFO[metric_key]

    # Sort all engineers by this raw metric descending, take top N
    sorted_engs = sorted(all_engineers, key=lambda e: e["raw_metrics"][metric_key], reverse=True)[:TOP_N]
    logins = [e["login"] for e in sorted_engs]
    values = [e["raw_metrics"][metric_key] for e in sorted_engs]

    base_color = CATEGORY_COLORS[category]
    colors = []
    for login in logins:
        if login == selected_login:
            colors.append("white")
        else:
            colors.append(base_color)

    fig = go.Figure(go.Bar(
        y=logins,
        x=values,
        orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        hovertemplate="%{y}: %{x:,.1f}<extra>" + display_name + "</extra>",
    ))
    fig.update_layout(
        title=dict(text=f"{display_name}", font=dict(size=13)),
        height=230,
        margin=dict(l=0, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="white",
        xaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
        yaxis=dict(autorange="reversed"),
    )
    return fig


cat_cols = st.columns(3)

for col, (category, metrics) in zip(cat_cols, CATEGORY_METRICS.items()):
    with col:
        color = CATEGORY_COLORS[category]
        st.markdown(
            f"<h4 style='color:{color}'>{category.title()}</h4>",
            unsafe_allow_html=True,
        )
        for m in metrics:
            _, desc = METRIC_INFO[m]
            st.plotly_chart(metric_bar_chart(m, category), use_container_width=True)
            st.caption(desc)

st.divider()

# ---------------------------------------------------------------------------
# Section 5: Methodology
# ---------------------------------------------------------------------------
with st.expander("How Scores Are Calculated"):
    st.markdown("""
**Three-Category Framework**

Every engineer is evaluated across three categories, each capturing a different facet of impact:

| Category | What it measures |
|---|---|
| **Collaboration** | How actively an engineer reviews and supports teammates' work |
| **Ownership** | Responsibility for bug fixes, issue triage, breadth of codebase involvement, and maintenance |
| **Output** | Volume and efficiency of code contributions |

**Metric Weights Within Each Category**

Each category is a weighted sum of its constituent metrics (normalized values):
""")

    mw = data["metric_weights"]
    for cat, weights in mw.items():
        st.markdown(f"*{cat.title()}*")
        rows = "| Metric | Weight |\n|---|---|\n"
        for m, w in weights.items():
            rows += f"| {METRIC_INFO[m][0]} | {w:.0%} |\n"
        st.markdown(rows)

    st.markdown("""
**Normalization**

All raw metrics are min-max normalized across qualifying engineers so that the highest value maps to 1.0 and the lowest to 0.0. This puts every metric on a comparable scale before weighting.

**Minimum PR Threshold**

Only engineers with at least **5 merged PRs** in the period are included. This filters out drive-by contributors and ensures the scores reflect sustained activity.

**Category Weight Sliders**

The sliders at the top of this dashboard let you adjust how much each category contributes to the final composite score. The three weights are automatically normalized to sum to 100%, so you can freely move them without worrying about the math. The default split is 35% Collaboration / 30% Ownership / 35% Output.
""")
