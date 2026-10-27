// Tabs from the URL hash, PR filters, and relative dates.
(() => {
  const views = [...document.querySelectorAll(".view")];
  const tabs = [...document.querySelectorAll('nav a[role="tab"]')];

  function show() {
    const id = location.hash.slice(1);
    const current = views.find((v) => v.id === "v-" + id) || views[0];
    views.forEach((v) => (v.hidden = v !== current));
    // A group view ("#epica-12377") keeps its parent tab ("#epica") selected.
    tabs.forEach((t) => {
      const base = "v-" + t.hash.slice(1);
      t.setAttribute("aria-selected", String(current.id === base || current.id.startsWith(base + "-")));
    });
    window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", show);
  show();

  // PR filters: one state tile at a time, plus free text.
  let state = null;
  const search = document.getElementById("search");
  const title = document.getElementById("prs-title");
  const rows = [...document.querySelectorAll("#t-all tbody tr")];
  const tiles = [...document.querySelectorAll(".tile")];

  function filter() {
    const q = (search.value || "").trim().toLowerCase();
    let n = 0;
    rows.forEach((r) => {
      const visible = (!state || r.dataset.state === state) && (!q || r.dataset.search.includes(q));
      r.hidden = !visible;
      if (visible) n++;
    });
    tiles.forEach((t) => t.setAttribute("aria-pressed", String(t.dataset.filter === state)));
    const label = state ? tiles.find((t) => t.dataset.filter === state).querySelector(".tile-label").textContent : "Todas las PRs abiertas";
    title.textContent = `${label} (${n})`;
  }
  tiles.forEach((t) => t.addEventListener("click", () => {
    state = state === t.dataset.filter ? null : t.dataset.filter;
    filter();
  }));
  search.addEventListener("input", filter);

  // "Listo" column: collapsed by default; the choice is remembered in this browser.
  const board = document.querySelector(".board");
  const toggle = document.querySelector(".col-toggle");
  if (board && toggle) {
    const KEY = "hub.done-open";
    const setOpen = (open) => {
      board.classList.toggle("done-collapsed", !open);
      toggle.setAttribute("aria-expanded", String(open));
      toggle.textContent = open ? "Ocultar" : "Mostrar";
    };
    let open = false;
    try { open = localStorage.getItem(KEY) === "1"; } catch (_) {}
    setOpen(open);
    toggle.addEventListener("click", () => {
      open = !open;
      setOpen(open);
      try { localStorage.setItem(KEY, open ? "1" : "0"); } catch (_) {}
    });
  }

  // "hace 3 h" style dates.
  const rtf = new Intl.RelativeTimeFormat("es", { numeric: "auto" });
  const units = [["day", 86400], ["hour", 3600], ["minute", 60]];
  document.querySelectorAll("[data-date]").forEach((el) => {
    const s = (new Date(el.dataset.date) - Date.now()) / 1000;
    const [unit, size] = units.find(([, size]) => Math.abs(s) >= size) || ["minute", 60];
    el.textContent = rtf.format(Math.round(s / size), unit);
    el.title = new Date(el.dataset.date).toLocaleString("es-ES");
  });
})();
