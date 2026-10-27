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
    "merged_days": 14,
}


def gh(*args):
    out = subprocess.run(["gh", *args], check=True, capture_output=True, text=True)
    return json.loads(out.stdout) if out.stdout.strip() else None


# CI rollup state of a PR's last commit → ok | fail | running | none
CI_STATES = {"SUCCESS": "ok", "FAILURE": "fail", "ERROR": "fail",
             "PENDING": "running", "EXPECTED": "running"}

PR_FIELDS = """
  number title url isDraft baseRefName mergeable updatedAt mergedAt
  repository { nameWithOwner }
  reviews(last: 50) { nodes { state author { login } } }
  assignees(first: 10) { nodes { login } }
  labels(first: 20) { nodes { name } }
  commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
"""


def user_prs(state, limit):
    """The user's PRs in the repo, newest first.

    Reads user.pullRequests instead of `gh pr list --author`, which goes
    through the search API: with the Actions token, search only finds repos
    the token can reach, so penpot/penpot came back empty.
    """
    query = f"""query($login: String!) {{
      user(login: $login) {{
        pullRequests(states: {state}, first: {limit},
                     orderBy: {{field: UPDATED_AT, direction: DESC}}) {{
          nodes {{ {PR_FIELDS} }}
        }}
      }}
    }}"""
    data = gh("api", "graphql", "-f", f"query={query}", "-F", f"login={CONFIG['user']}")
    return [p for p in data["data"]["user"]["pullRequests"]["nodes"]
            if p["repository"]["nameWithOwner"] == CONFIG["repo"]]


def open_prs():
    rows = []
    for p in user_prs("OPEN", 100):
        reviews = p["reviews"]["nodes"]
        rollup = p["commits"]["nodes"][0]["commit"]["statusCheckRollup"] if p["commits"]["nodes"] else None
        rows.append({
            "number": p["number"],
            "title": p["title"],
            "url": p["url"],
            "draft": p["isDraft"],
            "base": p["baseRefName"],
            "conflict": p["mergeable"] == "CONFLICTING",
            "approved_by": sorted({r["author"]["login"] for r in reviews
                                   if r["state"] == "APPROVED" and r["author"]}),
            "changes_requested": any(r["state"] == "CHANGES_REQUESTED" for r in reviews),
            "assignees": [a["login"] for a in p["assignees"]["nodes"]],
            "ci": CI_STATES.get((rollup or {}).get("state"), "none"),
            "updated": p["updatedAt"],
            "labels": [l["name"] for l in p["labels"]["nodes"]],
        })
    return sorted(rows, key=lambda r: r["number"], reverse=True)


def merged_prs():
    since = (dt.datetime.now(dt.timezone.utc)
             - dt.timedelta(days=CONFIG["merged_days"])).isoformat()
    prs = [{"number": p["number"], "title": p["title"], "url": p["url"],
            "mergedAt": p["mergedAt"]}
           for p in user_prs("MERGED", 100) if p["mergedAt"] >= since[:19]]
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


# The PR table in a group issue: "| #123 | Area | State |"
PR_ROW = re.compile(r"^\|\s*#(\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$")


def table_rows(body):
    rows = []
    for line in (body or "").splitlines():
        m = PR_ROW.match(line)
        if m:
            rows.append({"number": int(m[1]), "area": m[2], "table_state": m[3]})
    return rows


def epic():
    repo = CONFIG["repo"]
    meta = gh("issue", "view", str(CONFIG["epic"]), "--repo", repo, "--json", "title,url,state")
    # Sub-issues come with their body, where each group keeps its PR table.
    subs = gh("api", f"repos/{repo}/issues/{CONFIG['epic']}/sub_issues")

    groups = [{"number": g["number"], "title": g["title"], "url": g["html_url"],
               "state": g["state"], "prs": table_rows(g.get("body"))} for g in subs]
    states = pr_states([r["number"] for g in groups for r in g["prs"]])
    for g in groups:
        for r in g["prs"]:
            r.update(states.get(r["number"], {"state": "unknown"}))

    return {"title": meta["title"], "url": meta["url"], "state": meta["state"],
            "groups": groups}


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
          f"{len(data['issues'])} issues, "
          f"{sum(len(g['prs']) for g in data['epic']['groups'])} epic PRs, "
          f"{len(data['ideas'])} ideas")


if __name__ == "__main__":
    main()
