#!/usr/bin/env python3
"""Turn an idea (an issue of this repo) into a task in data/tasks.yml.

Usage: scripts/promote.py <issue number> [--status todo|doing|waiting] [--dry-run]

Adds the task at the top of the list, with the issue text as its note and a
link back to the issue, then closes the issue with a comment. Commit and push
data/tasks.yml afterwards so the board shows it.
"""

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "data" / "tasks.yml"
HUB_REPO = "EvaMarco/eva-hub"


def gh(*args):
    out = subprocess.run(["gh", *args], check=True, capture_output=True, text=True)
    return out.stdout


def yaml_str(text):
    # A double-quoted YAML string on one line.
    return json.dumps(" ".join(text.split()), ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("number", type=int)
    parser.add_argument("--status", default="todo", choices=["todo", "doing", "waiting"])
    parser.add_argument("--dry-run", action="store_true",
                        help="print the task without writing it or closing the issue")
    args = parser.parse_args()

    issue = json.loads(gh("issue", "view", str(args.number), "--repo", HUB_REPO,
                          "--json", "title,body,url,state"))
    if issue["state"] != "OPEN":
        sys.exit(f"#{args.number} is already closed: nothing to promote")

    entry = [f"- title: {yaml_str(issue['title'])}", f"  status: {args.status}"]
    if args.status == "waiting":
        entry.append("  waiting: other")
    entry.append(f"  links: [{yaml_str(issue['url'])}]")
    if (issue["body"] or "").strip():
        entry.append(f"  note: {yaml_str(issue['body'])}")
    entry.append(f"  added: {dt.date.today().isoformat()}")

    if args.dry_run:
        print("\n".join(entry))
        return

    # Insert after the header comments, before the first task.
    lines = TASKS.read_text().splitlines(keepends=True)
    first = next((i for i, l in enumerate(lines) if l.startswith("- ")), len(lines))
    lines[first:first] = [l + "\n" for l in entry] + ["\n"]
    TASKS.write_text("".join(lines))

    gh("issue", "close", str(args.number), "--repo", HUB_REPO,
       "--comment", "Pasada a tarea en `data/tasks.yml`.")
    print(f"#{args.number} → task \"{issue['title']}\" ({args.status}); issue closed.")
    print("Commit and push data/tasks.yml to see it on the board.")


if __name__ == "__main__":
    main()
