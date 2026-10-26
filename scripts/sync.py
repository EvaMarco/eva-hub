#!/usr/bin/env python3
"""Fetch everything the hub shows from GitHub and write data/cache/github.json.

Needs the `gh` CLI, logged in (locally) or with GH_TOKEN set (in Actions).
Reads only: penpot/penpot is public, so the default Actions token is enough.
"""

import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = {
    "user": os.environ.get("HUB_USER", "EvaMarco"),
    "repo": "penpot/penpot",
    "hub_repo": os.environ.get("GITHUB_REPOSITORY", "EvaMarco/eva-hub"),
    "epic": 12375,
    "group": 12376,
    "merged_days": 14,
}


def gh(*args):
    out = subprocess.run(["gh", *args], check=True, capture_output=True, text=True)
    return json.loads(out.stdout) if out.stdout.strip() else None


def ci_state(checks):
    checks = checks or []
    if any(c.get("conclusion") in ("FAILURE", "TIMED_OUT", "CANCELLED") for c in checks):
        return "fail"
    if any(c.get("status") not in (None, "COMPLETED") for c in checks):
        return "running"
    return "ok" if checks else "none"


def open_prs():
    prs = gh("pr", "list", "--repo", CONFIG["repo"], "--author", CONFIG["user"],
             "--state", "open", "--limit", "100", "--json",
             "number,title,url,isDraft,baseRefName,mergeable,reviews,"
             "assignees,statusCheckRollup,updatedAt,labels")
    rows = []
    for p in prs:
        rows.append({
            "number": p["number"],
            "title": p["title"],
            "url": p["url"],
            "draft": p["isDraft"],
            "base": p["baseRefName"],
            "conflict": p["mergeable"] == "CONFLICTING",
            "approved_by": sorted({r["author"]["login"] for r in p["reviews"]
                                   if r["state"] == "APPROVED"}),
            "changes_requested": any(r["state"] == "CHANGES_REQUESTED" for r in p["reviews"]),
            "assignees": [a["login"] for a in p["assignees"]],
            "ci": ci_state(p["statusCheckRollup"]),
            "updated": p["updatedAt"],
            "labels": [l["name"] for l in p["labels"]],
        })
    return rows


def merged_prs():
    since = (dt.date.today() - dt.timedelta(days=CONFIG["merged_days"])).isoformat()
    prs = gh("pr", "list", "--repo", CONFIG["repo"], "--author", CONFIG["user"],
             "--state", "merged", "--search", f"merged:>={since}", "--limit", "100",
             "--json", "number,title,url,mergedAt")
    return sorted(prs, key=lambda p: p["mergedAt"], reverse=True)


def assigned_issues():
    issues = gh("issue", "list", "--repo", CONFIG["repo"], "--assignee", CONFIG["user"],
                "--state", "open", "--limit", "100",
                "--json", "number,title,url,labels,milestone,updatedAt")
    return [{
        "number": i["number"],
        "title": i["title"],
        "url": i["url"],
        "labels": [l["name"] for l in i["labels"]],
        "milestone": (i.get("milestone") or {}).get("title"),
        "updated": i["updatedAt"],
    } for i in issues]


def pr_states(numbers):
    """State of many PRs in one GraphQL call."""
    if not numbers:
        return {}
    owner, name = CONFIG["repo"].split("/")
    fields = " ".join(f"p{n}: pullRequest(number: {n}) {{ number state isDraft title url }}"
                      for n in numbers)
    query = f'query {{ repository(owner: "{owner}", name: "{name}") {{ {fields} }} }}'
    data = gh("api", "graphql", "-f", f"query={query}")
    out = {}
    for pr in data["data"]["repository"].values():
        if pr:
            state = "draft" if pr["isDraft"] and pr["state"] == "OPEN" else pr["state"].lower()
            out[pr["number"]] = {"state": state, "title": pr["title"], "url": pr["url"]}
    return out


def epic():
    repo = CONFIG["repo"]
    meta = gh("issue", "view", str(CONFIG["epic"]), "--repo", repo, "--json", "title,url,state")
    groups = gh("api", f"repos/{repo}/issues/{CONFIG['epic']}/sub_issues")
    group = gh("issue", "view", str(CONFIG["group"]), "--repo", repo, "--json", "title,url,body")

    # The PR table in the group issue: "| #123 | Area | State |"
    rows = []
    for line in group["body"].splitlines():
        m = re.match(r"^\|\s*#(\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$", line)
        if m:
            rows.append({"number": int(m[1]), "area": m[2], "table_state": m[3]})
    states = pr_states([r["number"] for r in rows])
    for r in rows:
        r.update(states.get(r["number"], {"state": "unknown"}))

    return {
        "title": meta["title"],
        "url": meta["url"],
        "state": meta["state"],
        "groups": [{"number": g["number"], "title": g["title"], "url": g["html_url"],
                    "state": g["state"]} for g in groups],
        "group": {"number": CONFIG["group"], "title": group["title"], "url": group["url"],
                  "prs": rows},
    }


def ideas():
    try:
        issues = gh("issue", "list", "--repo", CONFIG["hub_repo"], "--state", "all",
                    "--limit", "100",
                    "--json", "number,title,url,state,labels,createdAt,closedAt,body")
    except subprocess.CalledProcessError as e:
        print(f"ideas: {e.stderr.strip()}", file=sys.stderr)
        return []
    return [{
        "number": i["number"],
        "title": i["title"],
        "url": i["url"],
        "open": i["state"] == "OPEN",
        "labels": [l["name"] for l in i["labels"]],
        "created": i["createdAt"],
        "closed": i["closedAt"],
        "body": (i["body"] or "")[:400],
    } for i in issues]


def main():
    data = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "config": CONFIG,
        "open_prs": open_prs(),
        "merged_prs": merged_prs(),
        "issues": assigned_issues(),
        "epic": epic(),
        "ideas": ideas(),
    }
    out = ROOT / "data" / "cache" / "github.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"wrote {out.relative_to(ROOT)}: {len(data['open_prs'])} open PRs, "
          f"{len(data['issues'])} issues, {len(data['epic']['group']['prs'])} epic PRs, "
          f"{len(data['ideas'])} ideas")


if __name__ == "__main__":
    main()
