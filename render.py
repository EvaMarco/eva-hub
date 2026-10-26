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
TASK_STATUS = [("doing", "En curso"), ("todo", "Por hacer"), ("waiting", "Esperando"), ("done", "Hecho")]

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
    m = re.search(r"/(pull|issues)/(\d+)", ref)
    label = f"#{m[2]}" if m else ref
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


def task_item(t, repo):
    links = " ".join(link_ref(l, repo) for l in t.get("links") or [])
    note = f'<p class="muted">{e(t["note"])}</p>' if t.get("note") else ""
    waiting = wait_tag(t.get("waiting")) if t.get("status") == "waiting" else ""
    return f"""
<li class="task t-{e(t.get('status', 'todo'))}">
  <div class="task-head"><span class="task-title">{e(t['title'])}</span> {waiting}</div>
  {note}
  <div class="task-meta">{links}<span class="muted">{e(str(t.get('added', '')))}</span></div>
</li>"""


def section(title, body, note=""):
    note = f'<p class="muted">{note}</p>' if note else ""
    return f'<section class="card"><h2>{title}</h2>{note}{body}</section>'


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
    counts = Counter(p["state"] for p in prs)

    # Now: what is mine to do
    mine = [p for p in prs if p["state"] in ("merge", "fail", "changes")
            or (p["note"] or {}).get("waiting") == "me"]
    my_tasks = [t for t in tasks if t.get("status") in ("doing", "todo")]
    waiting_on = Counter((p["note"] or {}).get("waiting") for p in prs
                         if (p["note"] or {}).get("waiting") not in (None, "me"))
    waiting_on += Counter(t.get("waiting") for t in tasks if t.get("status") == "waiting")
    open_ideas = [i for i in gh["ideas"] if i["open"]]

    tiles = "".join(
        f'<button class="tile st-{k}" data-filter="{k}" aria-pressed="false">'
        f'<span class="tile-label"><i></i>{e(label)}</span><span class="tile-n">{counts.get(k, 0)}</span></button>'
        for k, label in STATES)

    now_body = ""
    now_body += section(
        "Te toca",
        (pr_table(mine, repo, "t-mine") if mine else '<p class="empty">Ninguna PR necesita nada de ti ahora.</p>')
        + (f'<ul class="tasks">{"".join(task_item(t, repo) for t in my_tasks)}</ul>' if my_tasks else ""),
        "PRs que se pueden mergear, con el CI roto, con cambios pedidos o con una nota que dice que te toca; y tus tareas en curso o por hacer.")
    wait_chips = "".join(f'<span class="chip">{wait_tag(k)} <b>{n}</b></span>'
                         for k, n in waiting_on.most_common() if k)
    now_body += section("Esperando a otros", f'<div class="chips">{wait_chips or "—"}</div>',
                        "PRs y tareas que dependen de otra persona, según las notas.")
    merged = "".join(
        f'<li><a href="{e(p["url"])}">#{p["number"]}</a> {e(strip_emoji(p["title"]))} '
        f'<span class="muted" data-date="{e(p["mergedAt"])}"></span></li>' for p in gh["merged_prs"])
    now_body += section(f'Mergeadas en los últimos {cfg["merged_days"]} días ({len(gh["merged_prs"])})',
                        f'<ul class="plain">{merged or "<li>—</li>"}</ul>')

    issues = "".join(
        f'<li><a href="{e(i["url"])}">#{i["number"]}</a> {e(i["title"])}'
        f'{" · " + e(i["milestone"]) if i["milestone"] else ""}</li>' for i in gh["issues"])
    now_body += section(f'Issues asignadas ({len(gh["issues"])})', f'<ul class="plain">{issues or "<li>—</li>"}</ul>')

    # PRs tab
    prs_body = f"""
<div class="tiles" id="tiles">{tiles}</div>
<section class="card">
  <div class="card-top"><h2 id="prs-title">Todas las PRs abiertas ({len(prs)})</h2>
  <input type="search" id="search" placeholder="Buscar PR, título o nota" aria-label="Buscar"></div>
  {pr_table(prs, repo, "t-all")}
</section>"""

    # Epic tab
    ep = gh["epic"]
    gprs = ep["group"]["prs"]
    gcount = Counter(p["state"] for p in gprs)
    total = len(gprs) or 1
    bar = "".join(
        f'<span class="seg s-{k}" style="flex:{gcount.get(k, 0)}" title="{label}: {gcount.get(k, 0)}"></span>'
        for k, label in (("merged", "Mergeadas"), ("open", "En revisión"), ("draft", "Draft"), ("closed", "Cerradas")))
    legend = "".join(
        f'<span class="legend"><i class="s-{k}"></i>{label} <b>{gcount.get(k, 0)}</b></span>'
        for k, label in (("merged", "Mergeadas"), ("open", "En revisión"), ("draft", "Draft"), ("closed", "Cerradas")))
    drift = [p for p in gprs
             if (p["state"] == "merged" and p["table_state"] != "Merged")
             or (p["state"] == "open" and p["table_state"] == "Draft")]
    drift_html = (
        f'<details class="warn"><summary>La tabla de <a href="{e(ep["group"]["url"])}">#{ep["group"]["number"]}</a> '
        f'tiene {len(drift)} filas con el estado desactualizado</summary><p>'
        + ", ".join(f'<a href="{e(p.get("url", ""))}">#{p["number"]}</a> '
                    f'({e(p["table_state"])} → {e(p["state"])})' for p in drift)
        + "</p></details>") if drift else ""
    gstate = {"merged": "Mergeada", "open": "En revisión", "draft": "Draft", "closed": "Cerrada", "unknown": "?"}
    grows = "".join(
        f'<tr><td class="num"><a href="{e(p.get("url", ""))}">#{p["number"]}</a></td>'
        f'<td class="title">{e(p["area"])}</td><td><span class="gst s-{p["state"]}">{gstate.get(p["state"], p["state"])}</span></td></tr>'
        for p in sorted(gprs, key=lambda p: ({"open": 0, "draft": 1, "merged": 2}.get(p["state"], 3), -p["number"])))
    groups = "".join(
        f'<li class="g-{g["state"]}"><a href="{e(g["url"])}">#{g["number"]}</a> {e(g["title"])}'
        f'{" <b>(en curso)</b>" if g["number"] == ep["group"]["number"] else ""}</li>' for g in ep["groups"])
    epic_body = f"""
<section class="card">
  <h2><a href="{e(ep['url'])}">#{e(str(cfg['epic']))}</a> {e(ep['title'])}</h2>
  <p class="muted">Grupo en curso: <a href="{e(ep['group']['url'])}">#{ep['group']['number']}</a> {e(ep['group']['title'])}. {round(100 * gcount.get('merged', 0) / total)}% de sus PRs mergeadas.</p>
  <div class="bar">{bar}</div><div class="legends">{legend}</div>
  {drift_html}
</section>
<div class="grid2">
  <section class="card"><h2>PRs del grupo ({len(gprs)})</h2>
    <div class="tablebox"><table><thead><tr><th>PR</th><th>Área</th><th>Estado</th></tr></thead><tbody>{grows}</tbody></table></div></section>
  <section class="card"><h2>Grupos de la épica ({len(ep['groups'])})</h2><ol class="groups">{groups}</ol></section>
</div>"""

    # Tasks and ideas tab
    by_status = "".join(
        f'<h3>{label} ({sum(1 for t in tasks if t.get("status") == k)})</h3>'
        f'<ul class="tasks">{"".join(task_item(t, repo) for t in tasks if t.get("status") == k) or "<li class=muted>—</li>"}</ul>'
        for k, label in TASK_STATUS)
    idea_items = "".join(
        f'<li><a href="{e(i["url"])}">#{i["number"]}</a> {e(i["title"])} '
        f'<span class="muted" data-date="{e(i["created"])}"></span></li>' for i in open_ideas)
    new_idea = f"https://github.com/{hub}/issues/new"
    tasks_body = f"""
<div class="grid2">
  <section class="card"><div class="card-top"><h2>Ideas ({len(open_ideas)})</h2>
    <a class="button" href="{e(new_idea)}">Nueva idea</a></div>
    <p class="muted">Issues abiertas de <a href="https://github.com/{e(hub)}/issues">{e(hub)}</a>. Ciérralas al terminar.</p>
    <ul class="plain">{idea_items or '<li class="muted">Aún no hay ideas.</li>'}</ul></section>
  <section class="card"><h2>Tareas</h2><p class="muted">De <code>data/tasks.yml</code>.</p>{by_status}</section>
</div>"""

    n_mine = len(mine) + len(my_tasks)
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
      <a role="tab" href="#ahora">Ahora <b>{n_mine}</b></a>
      <a role="tab" href="#prs">PRs <b>{len(prs)}</b></a>
      <a role="tab" href="#epica">Épica DS <b>{round(100 * gcount.get('merged', 0) / total)}%</b></a>
      <a role="tab" href="#tareas">Tareas e ideas <b>{len(open_ideas) + sum(1 for t in tasks if t.get('status') != 'done')}</b></a>
    </nav>
  </div>
</header>
<main>
  <div class="view" id="v-ahora">{now_body}</div>
  <div class="view" id="v-prs">{prs_body}</div>
  <div class="view" id="v-epica">{epic_body}</div>
  <div class="view" id="v-tareas">{tasks_body}</div>
</main>
<script>{JS}</script>
</body></html>"""

    out = ROOT / "site" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page)
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    build()
