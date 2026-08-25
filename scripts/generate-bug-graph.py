#!/usr/bin/env python3
"""
generate-bug-graph.py — Parse git log and generate BUG-SMASHED.md

Usage:
    python3 scripts/generate-bug-graph.py [--repo PATH] [--output PATH] [--commits N]

Parses the last N commits (default 200) from the git log and produces
a chronologically organized bug-fix graph with per-subsystem breakdowns,
severity estimates, and a density chart.

Run from repo root or pass --repo explicitly. The output file (default
BUG-SMASHED.md) is overwritten in place.
"""

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime


def git_log(repo: str, n: int) -> list[dict]:
    """Return the last n commits as dicts with hash, date, subject."""
    result = subprocess.run(
        [
            "git", "-C", repo, "log",
            f"-{n}",
            "--format=%h|%ad|%s",
            "--date=short",
        ],
        capture_output=True, text=True, check=True,
    )
    commits = []
    for line in result.stdout.strip().splitlines():
        if "|" not in line:
            continue
        h, date, subject = line.split("|", 2)
        commits.append({"hash": h.strip(), "date": date.strip(), "subject": subject.strip()})
    return commits


BUG_PATTERNS = re.compile(
    r"\b(fix|crash|break|wrong|stale|dead|corrupt|leak|miss|fail|error|CVE|XSS|race|hang|false.positive|orphan|dangl|residual|revert|misalign|collision|broke|stuck|missing)\b",
    re.IGNORECASE,
)
# Exclude docs-only commits that mention "bug" in a filename, not a real bug
DOC_EXCLUDE = re.compile(r"docs?:\s*.*BUG-SMASHED", re.IGNORECASE)

# Subsystem classification keywords
SUBSYSTEMS = {
    "Usenet Pipeline": re.compile(r"nzbdav|usenet|fuse|mount|altmount|bearmount|rclone|infinidysk|webdav", re.I),
    "Plex": re.compile(r"plex|pms|jellyfin|media.server|tautulli|kometa", re.I),
    "Control Panel — Backend": re.compile(r"control.panel|django|api/v2|router|endpoint|service.error|rate.limit|session|auth|middleware|envelope|bootstrap", re.I),
    "Control Panel — Frontend": re.compile(r"ui|css|htmx|toast|sse|sparkline|rail|theme|modal|poster.sync|catalog.card|html|font|color|display|hidden", re.I),
    "Django Migration": re.compile(r"django|migrate|fastapi|whitenoise|static.file|dockerfile|pytest.httpx|requirements", re.I),
    "Monitoring Stack": re.compile(r"prometheus|grafana|loki|promtail|scrutiny|speedtest|cadvisor|node.exporter|alert|discord|webhook", re.I),
    "Exporter": re.compile(r"exporter|nzbdav.export|metric|scrape|label|config.metric", re.I),
    "CI/CD": re.compile(r"ci|workflow|trivy|release.please|validate.compose|shellcheck|ruff|claude.review|dependabot|pytest.version", re.I),
    "Security": re.compile(r"security|password|credential|secret|xss|csrf|cookie|allowed.host|rate.limit|privilege", re.I),
    "Fish Functions": re.compile(r"fish.function|stack-.*|api path|dead.*path|dead.*fastapi|wrapper.*parse", re.I),
}

SEVERITY_KEYWORDS = {
    "Critical": re.compile(r"(leak|data.loss|crash|xss|security|password|secret|500.*stale|connection.leak|provider.rejection|autoEmptyTrash)", re.I),
    "High": re.compile(r"(broken|down|missing|stale.*host|rate.limit.*miss|missing.*mount|502|unhandled|crash.*boot|image.*not.*found)", re.I),
    "Medium": re.compile(r"(wrong|mismatch|shape|form.field|stale.*label|collision|orphan|residual|late|race|reconnect)", re.I),
}


def classify_subsystems(subject: str) -> list[str]:
    matches = []
    for name, pattern in SUBSYSTEMS.items():
        if pattern.search(subject):
            matches.append(name)
    return matches or ["Uncategorized"]


def estimate_severity(subject: str) -> str:
    for level in ["Critical", "High", "Medium"]:
        if SEVERITY_KEYWORDS[level].search(subject):
            return level
    return "Low"


def is_bug(subject: str) -> bool:
    if DOC_EXCLUDE.search(subject):
        return False
    return bool(BUG_PATTERNS.search(subject))


def month_key(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return d.strftime("%Y-%m")
    except ValueError:
        return date_str[:7]


def generate(commits: list[dict]) -> str:
    bugs_by_month: dict[str, list[dict]] = defaultdict(list)
    bugs_by_subsystem: dict[str, list[dict]] = defaultdict(list)
    total_bugs = 0
    total_features = 0
    total_commits = len(commits)

    for c in commits:
        subj = c["subject"]
        if is_bug(subj):
            total_bugs += 1
            mk = month_key(c["date"])
            bugs_by_month[mk].append(c)
            for sub in classify_subsystems(subs if (subs := subj) else subj):
                bugs_by_subsystem[sub].append(c)
        if re.search(r"\bfeat\b", subj, re.I):
            total_features += 1

    lines = []
    lines.append("# BUG-SMASHED.md\n")
    lines.append("> **Every bug found and fixed in this repo, chronologically organized by subsystem.**")
    lines.append(f"> {total_bugs} fixes in the last {total_commits} commits. This document is the historical record — the graveyard of smashed bugs.\n")
    lines.append("---\n")

    # Timeline graph
    lines.append("## Bug Timeline Graph\n")
    lines.append("```")
    sorted_months = sorted(bugs_by_month.keys())
    for mk in sorted_months:
        bugs = bugs_by_month[mk]
        try:
            label = datetime.strptime(mk, "%Y-%m").strftime("%B %Y")
        except ValueError:
            label = mk
        bar = "█" * min(len(bugs), 40)
        lines.append(f"{mk} ({label}): {bar} {len(bugs)} bugs")
    lines.append("```\n")

    # Bug details by month
    lines.append("## Bug Details by Month\n")
    for mk in sorted_months:
        bugs = bugs_by_month[mk]
        try:
            label = datetime.strptime(mk, "%Y-%m").strftime("%B %Y")
        except ValueError:
            label = mk
        lines.append(f"### {label} ({len(bugs)} bugs)\n")
        lines.append("| Date | Hash | Subsystem | Severity | Description |")
        lines.append("|------|------|-----------|----------|-------------|")
        for c in sorted(bugs, key=lambda x: x["date"]):
            sub = ", ".join(classify_subsystems(c["subject"]))
            sev = estimate_severity(c["subject"])
            # Clean up conventional commit prefix
            desc = re.sub(r"^(fix|chore|ci|docs|refactor|test|style)\s*:\s*", "", c["subject"], flags=re.I)
            lines.append(f"| {c['date']} | `{c['hash']}` | {sub} | {sev} | {desc} |")
        lines.append("")

    # By subsystem
    lines.append("---\n")
    lines.append("## By Subsystem\n")
    for sub_name in sorted(bugs_by_subsystem.keys()):
        bugs = bugs_by_subsystem[sub_name]
        lines.append(f"### {sub_name} ({len(bugs)} bugs)\n")
        lines.append("| Date | Hash | Severity | Description |")
        lines.append("|------|------|----------|-------------|")
        for c in sorted(bugs, key=lambda x: x["date"]):
            sev = estimate_severity(c["subject"])
            desc = re.sub(r"^(fix|chore|ci|docs|refactor|test|style)\s*:\s*", "", c["subject"], flags=re.I)
            lines.append(f"| {c['date']} | `{c['hash']}` | {sev} | {desc} |")
        lines.append("")

    # Severity summary
    lines.append("---\n")
    lines.append("## Severity Summary\n")
    sev_counts = defaultdict(int)
    for c in commits:
        if is_bug(c["subject"]):
            sev_counts[estimate_severity(c["subject"])] += 1
    lines.append("| Level | Count | Meaning |")
    lines.append("|-------|-------|---------|")
    for level in ["Critical", "High", "Medium", "Low"]:
        count = sev_counts.get(level, 0)
        meanings = {
            "Critical": "Data loss, security exposure, or complete service outage",
            "High": "Major feature broken, requires immediate fix",
            "Medium": "Degraded functionality, wrong behavior in edge cases",
            "Low": "Cosmetic, documentation, or minor inconvenience",
        }
        lines.append(f"| **{level}** | {count} | {meanings[level]} |")
    lines.append("")

    # Bug density
    lines.append("## Bug Density by Month\n")
    lines.append("```")
    for mk in sorted_months:
        count = len(bugs_by_month[mk])
        bar = "█" * min(count, 40)
        lines.append(f"{mk}: {bar} {count} bugs")
    lines.append("```")
    lines.append(f"\n**Total: {total_bugs} bugs fixed across {total_commits} commits.**\n")

    # Stats
    lines.append("---\n")
    lines.append(f"*Last updated: {datetime.now().strftime('%Y-%m-%d')}. Auto-generated from `git log` by `scripts/generate-bug-graph.py`.*\n")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate BUG-SMASHED.md from git log")
    parser.add_argument("--repo", default=".", help="Path to git repo root")
    parser.add_argument("--output", default="BUG-SMASHED.md", help="Output file path")
    parser.add_argument("--commits", type=int, default=200, help="Number of commits to analyze")
    args = parser.parse_args()

    commits = git_log(args.repo, args.commits)
    if not commits:
        print("No commits found.", file=sys.stderr)
        sys.exit(1)

    output = generate(commits)

    import os
    outpath = os.path.join(args.repo, args.output)
    with open(outpath, "w") as f:
        f.write(output)

    bug_count = sum(1 for c in commits if is_bug(c["subject"]))
    print(f"Generated {outpath}: {len(commits)} commits analyzed, {bug_count} bugs found")


if __name__ == "__main__":
    main()
