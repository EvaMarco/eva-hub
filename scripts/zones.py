"""Inventory the DS migration epic (#12375) by zone and write data/zones.yml.

For each group of the epic, find the files that still use the legacy
control the group replaces, group them into zones (a folder, or a file
when a folder has many) and estimate how many issues each zone needs.

Run it against a Penpot checkout on develop:

    python3 scripts/zones.py ~/penpot/frontend

The counts are rough: they come from text patterns, not from parsing.
"""

import math
import re
import sys
from datetime import date
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "data" / "zones.yml"

# Folders split into one zone per file when they have more files than this.
SPLIT_OVER = 6


def refactor_mixins(frontend):
    path = frontend / "resources/styles/common/refactor/mixins.scss"
    names = re.findall(r"@mixin ([\w-]*typography)\b", path.read_text())
    return "|".join(sorted(set(names)))


def groups(frontend):
    """Each group: issue, name, files to scan, patterns, uses per issue."""
    typo = refactor_mixins(frontend)
    return [
        {"issue": 12377, "name": "Selects", "ext": "cljs", "per_issue": 4,
         "patterns": [r"\[:[&>] (cs/)?select(?![\w*-])", r"\[:[&>] fm/select(?![\w*-])"],
         "needs": r"app\.main\.ui\.components\.(select|forms)",
         "skip": ["components/select.cljs", "components/forms.cljs"]},
        {"issue": 12378, "name": "Radio buttons", "ext": "cljs", "per_issue": 4,
         "patterns": [r"\[:[&>] radio-buttons(?![\w*-])"],
         "needs": r"app\.main\.ui\.components\.radio-buttons",
         "skip": ["components/radio_buttons.cljs"]},
        {"issue": 12379, "name": "Numeric inputs", "ext": "cljs", "per_issue": 8,
         "patterns": [r"\[:[&>] deprecated-input/numeric-input\*?"],
         "needs": r"app\.main\.ui\.components\.numeric-input",
         "skip": ["components/numeric_input.cljs"]},
        {"issue": 12380, "name": "Text inputs and checkboxes", "ext": "scss",
         "per_issue": 6,
         "patterns": [r"@extend %(input-[\w-]+|checkbox[\w-]*)"],
         "skip": []},
        {"issue": 12543, "name": "Modals", "ext": "cljs", "per_issue": 3,
         "patterns": [r"::mf/register-as "],
         "skip": []},
        {"issue": 12544, "name": "Dropdowns and context menus", "ext": "cljs",
         "per_issue": 4,
         "patterns": [r"\[:[&>] dropdown(-content\*)?(?![\w*-])", r"\[:[&>] context-menu\*"],
         "needs": r"app\.main\.ui\.components\.(dropdown|context-menu-a11y)",
         "skip": ["components/dropdown.cljs", "components/context_menu_a11y.cljs"]},
        {"issue": 12545, "name": "Tooltips", "ext": "cljs", "per_issue": 15,
         "patterns": [r":title [\"(]"],
         "skip": []},
        {"issue": 12546, "name": "Title bars and search bars", "ext": "cljs",
         "per_issue": 6,
         "patterns": [r"\[:[&>] (inspect-)?title-bar\*", r"\[:[&>] search-bar\*"],
         "needs": r"app\.main\.ui\.components\.(title-bar|search-bar)",
         "skip": ["components/title_bar.cljs", "components/search_bar.cljs"]},
        {"issue": 12547, "name": "Headings and text", "ext": "both",
         "per_issue": 10,
         "patterns": [r"\[:h[1-6][\s.#{]", rf"@include ({typo})\b"],
         "skip": []},
        {"issue": 12548, "name": "Notifications, color bullets and widgets",
         "ext": "cljs", "per_issue": 6,
         "patterns": [r"\[:[&>] (context-notification|inline-notification|(cb|bc)/[\w-]+|editable-label\*?|editable-select|lb/link-button)\b"],
         "skip": ["notifications/", "components/color_bullet.cljs",
                  "components/editable_label.cljs",
                  "components/editable_select.cljs",
                  "components/link_button.cljs"]},
        {"issue": 12549, "name": "Remaining deprecated SCSS", "ext": "scss",
         "per_issue": 3,
         "patterns": [r"@use \"refactor/|@import \"refactor/|common/refactor/"],
         "count": "files",
         "skip": []},
    ]


def scan(ui, group):
    exts = {"cljs": [".cljs"], "scss": [".scss"], "both": [".cljs", ".scss"]}
    hits = {}
    for path in sorted(ui.rglob("*")):
        if path.suffix not in exts[group["ext"]]:
            continue
        rel = path.relative_to(ui).as_posix()
        if rel.startswith(("ds/", "releases/")) or rel == "releases.cljs":
            continue
        if any(rel.startswith(s) or rel == s for s in group["skip"]):
            continue
        text = path.read_text()
        if group.get("needs") and path.suffix == ".cljs" \
                and not re.search(group["needs"], text):
            continue
        n = sum(len(re.findall(p, text)) for p in group["patterns"])
        if n:
            hits[rel] = 1 if group.get("count") == "files" else n
    return hits


def zone_of(rel):
    return rel.rsplit("/", 1)[0] if "/" in rel else "(root)"


def zones(hits, per_issue):
    by_dir = {}
    for rel, n in hits.items():
        by_dir.setdefault(zone_of(rel), {})[rel] = n
    out = []
    for folder, files in sorted(by_dir.items()):
        parts = [(f.rsplit(".", 1)[0], {f: n}) for f, n in files.items()] \
            if len(files) > SPLIT_OVER else [(folder, files)]
        for name, fs in parts:
            uses = sum(fs.values())
            out.append({
                "zone": name,
                "files": sorted(fs),
                "uses": uses,
                "issues": max(1, math.ceil(uses / per_issue)),
            })
    return out


def main():
    frontend = Path(sys.argv[1]).expanduser().resolve()
    ui = frontend / "src/app/main/ui"
    result = {"generated": date.today().isoformat(), "groups": []}
    for g in groups(frontend):
        zs = zones(scan(ui, g), g["per_issue"])
        result["groups"].append({
            "issue": g["issue"],
            "name": g["name"],
            "per_issue": g["per_issue"],
            "uses": sum(z["uses"] for z in zs),
            "issues": sum(z["issues"] for z in zs),
            "zones": zs,
        })
    OUT.write_text(
        "# Generated by scripts/zones.py: do not edit by hand.\n"
        + yaml.safe_dump(result, allow_unicode=True, sort_keys=False))
    for g in result["groups"]:
        print(f"#{g['issue']} {g['name']}: {g['uses']} uses, "
              f"{len(g['zones'])} zones, ~{g['issues']} issues")


if __name__ == "__main__":
    main()
