#!/usr/bin/env python3
"""Build site/index.html from data/cache/github.json, data/notes.yml and data/tasks.yml.

Run scripts/sync.py first. Never edit site/ by hand: it is rebuilt every time.
"""

import datetime as dt
import html
import json
import re
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
CSS = (ROOT / "assets" / "hub.css").read_text()
JS = (ROOT / "assets" / "hub.js").read_text()

# PR states, in the order they are worth looking at.
STATES = [
    ("merge", "Lista para mergear"),
    ("fail", "CI falla"),
    ("changes", "Cambios pedidos"),
    ("approved", "Aprobada, CI en curso"),
    ("review", "En revisión"),
    ("rebase", "Necesita rebase"),
    ("draft", "Draft"),
]
STATE_LABEL = dict(STATES)
STATE_ORDER = {k: i for i, (k, _) in enumerate(STATES)}
WAITING = {"me": "Yo", "review": "Revisión", "design": "Diseño", "ci": "CI", "other": "Otros"}

e = html.escape


def load_yaml(name, default):
    path = ROOT / "data" / name
    return (yaml.safe_load(path.read_text()) if path.exists() else None) or default


def pr_state(p):
    if p["draft"]:
        return "draft"
    if p["conflict"]:
        return "rebase"
    if p["ci"] == "fail":
        return "fail"
    if p["changes_requested"]:
        return "changes"
    if p["approved_by"] and p["ci"] == "ok":
        return "merge"
    if p["approved_by"]:
        return "approved"
    return "review"


def strip_emoji(title):
    return re.sub(r"^:[a-z_]+:\s*", "", title)


def link_ref(ref, repo):
    """'#123' → link to penpot/penpot; a URL → link with a short label."""
    ref = str(ref)
    if ref.startswith("#"):
        return f'<a href="https://github.com/{repo}/issues/{ref[1:]}">{e(ref)}</a>'
    m = re.search(r"github\.com/([^/]+)/([^/]+)/(pull|issues)/(\d+)", ref)
    if m:
        # Issues of another repo (an idea of the hub) carry the repo name.
        label = f"#{m[4]}" if f"{m[1]}/{m[2]}" == repo else f"{m[2]}#{m[4]}"
    else:
        label = ref
    return f'<a href="{e(ref)}">{e(label)}</a>'


def pill(state):
    return f'<span class="pill st-{state}"><i></i>{e(STATE_LABEL[state])}</span>'


def wait_tag(key):
    return f'<span class="tag w-{e(key)}">{e(WAITING.get(key, key))}</span>' if key else ""


def ci_tag(ci):
    label = {"ok": "CI ok", "fail": "CI falla", "running": "CI en curso", "none": "sin CI"}[ci]
    return f'<span class="ci ci-{ci}">{label}</span>'


def pr_row(p, repo):
    note = p["note"] or {}
    who = ", ".join(p["approved_by"]) or ", ".join(p["assignees"]) or "—"
    search = " ".join([str(p["number"]), p["title"], note.get("next", ""), who]).lower()
    return f"""
<tr data-state="{p['state']}" data-search="{e(search)}">
  <td class="num"><a href="{e(p['url'])}">#{p['number']}</a></td>
  <td class="title">{e(strip_emoji(p['title']))}</td>
  <td>{pill(p['state'])}</td>
  <td class="next">{e(note.get('next', '—'))} {wait_tag(note.get('waiting'))}</td>
  <td>{ci_tag(p['ci'])}</td>
  <td class="narrow">{e(p['base'])}</td>
  <td class="narrow">{e(who)}</td>
</tr>"""


def pr_table(prs, repo, table_id):
    rows = "".join(pr_row(p, repo) for p in prs)
    return f"""
<div class="tablebox"><table id="{table_id}">
  <thead><tr><th>PR</th><th>Título</th><th>Estado</th><th>Siguiente paso</th><th>CI</th>
  <th class="narrow">Base</th><th class="narrow">Aprobada / asignada</th></tr></thead>
  <tbody>{rows}</tbody>
</table></div>"""


BOARD = [("ideas", "Ideas"), ("todo", "Por empezar"), ("doing", "En curso"), ("waiting", "Esperando"),
         ("review", "En revisión"), ("done", "Listo")]
DONE_DAYS = 7
IDEAS_HINT = '<p class="muted col-hint">Issues abiertas del repo del hub: cosas que no queremos olvidar.</p>'


def pr_column(p):
    """Board column of an open PR, from its state and its note."""
    waiting = (p["note"] or {}).get("waiting")
    if p["state"] in ("merge", "fail", "changes") or waiting == "me":
        return "doing"
    if waiting in ("design", "other"):
        return "waiting"
    if p["state"] == "draft":
        return "doing"
    return "review"


def task_column(t):
    return {"todo": "todo", "doing": "doing", "waiting": "waiting", "done": "done"}.get(t.get("status"), "todo")


def recent(date, days=DONE_DAYS):
    if not date:
        return True
    date = date if isinstance(date, dt.date) else dt.date.fromisoformat(str(date)[:10])
    return (dt.date.today() - date).days <= days


def pr_card(p):
    note = p["note"] or {}
    meta = " ".join(x for x in (wait_tag(note.get("waiting")), ci_tag(p["ci"]) if p["ci"] != "none" else "") if x)
    return f"""
<li class="bcard k-pr">
  <div class="bcard-head"><a class="ref" href="{e(p['url'])}">#{p['number']}</a> {pill(p['state'])}</div>
  <div class="bcard-title">{e(strip_emoji(p['title']))}</div>
  {f'<p class="muted">{e(note["next"])}</p>' if note.get("next") else ""}
  {f'<div class="bcard-meta">{meta}</div>' if meta else ""}
</li>"""


def merged_card(p):
    return f"""
<li class="bcard k-pr">
  <div class="bcard-head"><a class="ref" href="{e(p['url'])}">#{p['number']}</a> <span class="tag">Mergeada</span></div>
  <div class="bcard-title">{e(strip_emoji(p['title']))}</div>
  <div class="bcard-meta"><span class="muted" data-date="{e(p['mergedAt'])}"></span></div>
</li>"""


def idea_card(i):
    body = " ".join((i["body"] or "").split())
    body = body[:160] + "…" if len(body) > 160 else body
    return f"""
<li class="bcard k-idea">
  <div class="bcard-head"><a class="ref" href="{e(i['url'])}">#{i['number']}</a> <span class="tag">Idea</span></div>
  <div class="bcard-title">{e(i['title'])}</div>
  {f'<p class="muted">{e(body)}</p>' if body else ""}
  <div class="bcard-meta"><span class="muted" data-date="{e(i['created'])}"></span>
    <span class="hint" title="Crea la tarea en data/tasks.yml y cierra la issue">Para pasarla a tarea: <code>scripts/promote.py {i['number']}</code></span></div>
</li>"""


def task_card(t, repo):
    links = " ".join(link_ref(l, repo) for l in t.get("links") or [])
    items = "".join(f"<li>{e(i)}</li>" for i in t.get("items") or [])
    waiting = wait_tag(t.get("waiting")) if t.get("status") == "waiting" else ""
    return f"""
<li class="bcard k-task">
  <div class="bcard-head"><span class="tag">Tarea</span> {waiting}</div>
  <div class="bcard-title">{e(t['title'])}</div>
  {f'<p class="muted">{e(t["note"])}</p>' if t.get("note") else ""}
  {f'<ul class="task-items">{items}</ul>' if items else ""}
  <div class="bcard-meta">{links}</div>
</li>"""


def build():
    gh = json.loads((ROOT / "data" / "cache" / "github.json").read_text())
    notes = load_yaml("notes.yml", {})
    tasks = load_yaml("tasks.yml", [])
    cfg = gh["config"]
    repo, hub = cfg["repo"], cfg["hub_repo"]

    prs = []
    for p in gh["open_prs"]:
        p = dict(p, state=pr_state(p), note=notes.get(p["number"]))
        prs.append(p)
    prs.sort(key=lambda p: (STATE_ORDER[p["state"]], -p["number"]))

    # Board: tasks and PRs in columns
    open_ideas = [i for i in gh["ideas"] if i["open"]]
    columns = {k: [] for k, _ in BOARD}
    for p in prs:
        columns[pr_column(p)].append(pr_card(p))
    for t in tasks:
        col = task_column(t)
        if col != "done" or recent(t.get("done")):
            columns[col].append(task_card(t, repo))
    for p in gh["merged_prs"]:
        if recent(p["mergedAt"]):
            columns["done"].append(merged_card(p))
    for i in open_ideas:
        columns["ideas"].append(idea_card(i))
    board_body = '<div class="board">' + "".join(
        f'<section class="bcol c-{k}"><h2>{label} <b>{len(columns[k])}</b></h2>'
        f'{IDEAS_HINT if k == "ideas" else ""}'
        f'<ul class="bcards">{"".join(columns[k]) or "<li class=empty>—</li>"}</ul></section>'
        for k, label in BOARD) + "</div>"

    merged = "".join(
        f'<li><a href="{e(p["url"])}">#{p["number"]}</a> {e(strip_emoji(p["title"]))} '
        f'<span class="muted" data-date="{e(p["mergedAt"])}"></span></li>' for p in gh["merged_prs"])
    issues = "".join(
        f'<li><a href="{e(i["url"])}">#{i["number"]}</a> {e(i["title"])}'
        f'{" · " + e(i["milestone"]) if i["milestone"] else ""}</li>' for i in gh["issues"])

    # PRs tab
    counts = Counter(p["state"] for p in prs)
    tiles = "".join(
        f'<button class="tile st-{k}" data-filter="{k}" aria-pressed="false">'
        f'<span class="tile-label"><i></i>{e(label)}</span><span class="tile-n">{counts.get(k, 0)}</span></button>'
        for k, label in STATES)
    prs_body = f"""
<div class="tiles" id="tiles">{tiles}</div>
<section class="card">
  <div class="card-top"><h2 id="prs-title">Todas las PRs abiertas ({len(prs)})</h2>
  <input type="search" id="search" placeholder="Buscar PR, título o nota" aria-label="Buscar"></div>
  {pr_table(prs, repo, "t-all")}
</section>
<div class="grid2">
  <section class="card"><h2>Mergeadas en los últimos {cfg["merged_days"]} días ({len(gh["merged_prs"])})</h2>
    <ul class="plain">{merged or "<li>—</li>"}</ul></section>
  <section class="card"><h2>Issues asignadas ({len(gh["issues"])})</h2>
    <ul class="plain">{issues or "<li>—</li>"}</ul></section>
</div>"""

    # Epic tab: an overview of every group, and one view per group
    ep = gh["epic"]
    states = (("merged", "Mergeadas"), ("open", "En revisión"), ("draft", "Draft"), ("closed", "Cerradas"))
    gstate = {"merged": "Mergeada", "open": "En revisión", "draft": "Draft", "closed": "Cerrada", "unknown": "?"}

    def group_bar(prs):
        count = Counter(p["state"] for p in prs)
        bar = "".join(
            f'<span class="seg s-{k}" style="flex:{count.get(k, 0)}" title="{label}: {count.get(k, 0)}"></span>'
            for k, label in states)
        legend = "".join(
            f'<span class="legend"><i class="s-{k}"></i>{label} <b>{count.get(k, 0)}</b></span>'
            for k, label in states if count.get(k, 0))
        return count, f'<div class="bar">{bar}</div><div class="legends">{legend}</div>'

    def group_summary(g):
        count = Counter(p["state"] for p in g["prs"])
        if not g["prs"]:
            return "Sin empezar"
        done = round(100 * count.get("merged", 0) / len(g["prs"]))
        n = len(g["prs"])
        return f'{done}% mergeadas · {n} {"PR" if n == 1 else "PRs"}'

    def group_view(g):
        prs = g["prs"]
        _, bar = group_bar(prs)
        drift = [p for p in prs
                 if (p["state"] == "merged" and p["table_state"] != "Merged")
                 or (p["state"] == "open" and p["table_state"] == "Draft")]
        drift_html = (
            f'<details class="warn"><summary>La tabla de <a href="{e(g["url"])}">#{g["number"]}</a> '
            f'tiene {len(drift)} filas con el estado desactualizado</summary><p>'
            + ", ".join(f'<a href="{e(p.get("url", ""))}">#{p["number"]}</a> '
                        f'({e(p["table_state"])} → {e(p["state"])})' for p in drift)
            + "</p></details>") if drift else ""
        rows = "".join(
            f'<tr><td class="num"><a href="{e(p.get("url", ""))}">#{p["number"]}</a></td>'
            f'<td class="title">{e(p["area"])}</td><td><span class="gst s-{p["state"]}">{gstate.get(p["state"], p["state"])}</span></td></tr>'
            for p in sorted(prs, key=lambda p: ({"open": 0, "draft": 1, "merged": 2}.get(p["state"], 3), -p["number"])))
        table = (f'<div class="tablebox"><table><thead><tr><th>PR</th><th>Área</th><th>Estado</th></tr></thead>'
                 f'<tbody>{rows}</tbody></table></div>') if prs else '<p class="muted">Todavía no tiene PRs.</p>'
        return f"""
<div class="view" id="v-epica-{g['number']}">
<p class="back"><a href="#epica">← Todos los grupos</a></p>
<section class="card">
  <h2><a href="{e(g['url'])}">#{g['number']}</a> {e(g['title'])}</h2>
  <p class="muted">{group_summary(g)}</p>
  {bar if prs else ''}
  {drift_html}
</section>
<section class="card"><h2>PRs del grupo ({len(prs)})</h2>{table}</section>
</div>"""

    group_rows = "".join(
        f'<li class="g-{g["state"]}"><a class="gname" href="#epica-{g["number"]}">'
        f'<span class="num">#{g["number"]}</span> {e(g["title"])}</a>'
        f'<span class="muted">{group_summary(g)}</span>{group_bar(g["prs"])[1] if g["prs"] else ""}</li>'
        for g in ep["groups"])
    all_prs = [p for g in ep["groups"] for p in g["prs"]]
    all_count = Counter(p["state"] for p in all_prs)
    started = sum(1 for g in ep["groups"] if g["prs"])
    epic_body = f"""
<section class="card">
  <h2><a href="{e(ep['url'])}">#{e(str(cfg['epic']))}</a> {e(ep['title'])}</h2>
  <p class="muted">{len(ep['groups'])} grupos, {started} empezados. {all_count.get('merged', 0)} de {len(all_prs)} PRs mergeadas en total.</p>
</section>
<section class="card"><h2>Grupos</h2><ol class="groups">{group_rows}</ol></section>"""
    group_views = "".join(group_view(g) for g in ep["groups"])
    merged_total = all_count.get("merged", 0)

    new_idea = f"https://github.com/{hub}/issues/new"

    n_doing = len(columns["doing"])
    refresh = f"https://github.com/{hub}/actions/workflows/hub.yml"
    page = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Hub de Eva</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Work+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>{CSS}</style></head>
<body>
<header class="top">
  <div class="top-in">
    <div><h1>Hub de Eva</h1>
      <p class="muted">Datos de GitHub <span data-date="{e(gh['generated_at'])}"></span> ·
      <a href="{e(refresh)}">Actualizar ahora</a> · <a href="{e(new_idea)}">Nueva idea</a></p></div>
    <nav role="tablist">
      <a role="tab" href="#tablero">Tablero <b>{n_doing}</b></a>
      <a role="tab" href="#prs">PRs <b>{len(prs)}</b></a>
      <a role="tab" href="#epica">Épica DS <b>{merged_total}</b></a>
    </nav>
  </div>
</header>
<main>
  <div class="view" id="v-tablero">{board_body}</div>
  <div class="view" id="v-prs">{prs_body}</div>
  <div class="view" id="v-epica">{epic_body}</div>
  {group_views}
</main>
<script>{JS}</script>
</body></html>"""

    out = ROOT / "site" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page)
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    build()
