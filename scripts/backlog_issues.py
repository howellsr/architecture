"""Create the repository's labels and one issue for each guardrail backlog row.

The guardrail backlog is the table under "Guardrail backlog" on
docs/about/roadmap.md. This script reads that table, so the issues always
match the page, and is run by .github/workflows/backlog-issues.yml:

    python scripts/backlog_issues.py --dry-run   # show what would be created
    python scripts/backlog_issues.py             # create, using the gh CLI

It is safe to run more than once: labels are updated in place, and a row
whose issue already exists (open or closed, matched by title) is skipped.
Each row on the roadmap links to an issue search for its title, so the page
needs no change once the issues exist.
"""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import subprocess
import sys
from urllib.parse import quote_plus

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROADMAP = os.path.join(ROOT, "docs", "about", "roadmap.md")
LABELS = os.path.join(ROOT, ".github", "labels.yml")
REPO = "DEFRA/architecture"
SITE = "https://defra.github.io/architecture/"
LABEL = "guardrail-backlog"
TITLE_PREFIX = "Guardrail backlog: "

SECTION = re.compile(r"^## Guardrail backlog.*?\n(.*?)(?=^## )", re.M | re.S)
ROW = re.compile(r"^\| (High|Medium|Low) \| (.+?) \| (.+?) \| (.+?) \|$", re.M)
NAME = re.compile(r"^\*\*(?:\[([^\]]+)\]\([^)]+\)|([^*]+))\*\*")
LINK = re.compile(r"\]\(([^)\s]+)\)")


def issue_title(name: str) -> str:
    return f"{TITLE_PREFIX}{name}"


def search_url(name: str) -> str:
    """The issue search a backlog row links to: its issue, open or closed, once the workflow has run."""
    query = f'is:issue label:{LABEL} in:title "{issue_title(name)}"'
    return f"https://github.com/{REPO}/issues?q={quote_plus(query)}"


def absolute(markdown: str, page: str = "about/roadmap.md") -> str:
    """Turn links relative to a docs page into links to the published site."""

    def fix(match: re.Match) -> str:
        target = match.group(1)
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            return match.group(0)
        path, _, anchor = target.partition("#")
        path = posixpath.normpath(posixpath.join(posixpath.dirname(page), path))
        path = re.sub(r"(^|/)index\.md$", r"\1", path)
        path = re.sub(r"\.md$", "/", path)
        return f"]({SITE}{path}{'#' + anchor if anchor else ''})"

    return LINK.sub(fix, markdown)


def rows(text: str) -> list[dict]:
    """The backlog rows on the roadmap page."""
    section = SECTION.search(text)
    if not section:
        raise ValueError("docs/about/roadmap.md has no Guardrail backlog section")
    found = []
    for priority, cell, gap, doctrine in ROW.findall(section.group(1)):
        name = NAME.match(cell)
        if not name:
            raise ValueError(f"backlog row does not start with a bold name: {cell}")
        found.append(
            {
                "priority": priority,
                "name": (name.group(1) or name.group(2)).strip(),
                "cell": cell,
                "gap": gap,
                "doctrine": doctrine,
            }
        )
    return found


def issue(row: dict) -> dict:
    """The title, body and labels of the issue for a backlog row."""
    cell = NAME.sub(f"**{row['name']}**", row["cell"], count=1)
    body = "\n\n".join(
        [
            f"From the [guardrail backlog]({SITE}about/roadmap/#guardrail-backlog).",
            f"**Priority:** {row['priority']}",
            f"**Proposed guardrails:** {absolute(cell)}",
            f"**The gap:** {absolute(row['gap'])}",
            f"**Doctrine and principle:** {absolute(row['doctrine'])}",
            "Comment here with evidence, examples or a proposed wording. New guardrails take the next free id "
            "in their area and start as `status: draft`.",
        ]
    )
    return {"title": issue_title(row["name"]), "body": body + "\n", "labels": [LABEL]}


def labels() -> list[dict]:
    with open(LABELS, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args, "--repo", REPO], check=True, capture_output=True, text=True).stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="show what would be created, without creating it")
    dry_run = parser.parse_args().dry_run
    with open(ROADMAP, encoding="utf-8") as handle:
        wanted = [issue(r) for r in rows(handle.read())]

    for label in labels():
        print(f"Label: {label['name']}")
        if not dry_run:
            colour, description = label["color"], label["description"]
            gh("label", "create", label["name"], "--color", colour, "--description", description, "--force")

    existing = set()
    if not dry_run:
        listed = gh("issue", "list", "--label", LABEL, "--state", "all", "--limit", "500", "--json", "title")
        existing = {i["title"] for i in json.loads(listed)}
    for item in wanted:
        if item["title"] in existing:
            print(f"Exists: {item['title']}")
            continue
        print(f"Create: {item['title']}")
        if not dry_run:
            gh("issue", "create", "--title", item["title"], "--body", item["body"], "--label", ",".join(item["labels"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
