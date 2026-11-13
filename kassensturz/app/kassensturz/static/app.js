// Kassensturz – Oberfläche. Läuft hinter dem Home-Assistant-Ingress, daher nur relative Pfade.

/* ------------------------------------------------------------------ Grundlagen */
class Raw { constructor(s) { this.s = s; } toString() { return this.s; } }
const raw = (s) => new Raw(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function html(strings, ...vals) {
  let out = strings[0];
  vals.forEach((v, i) => {
    if (v instanceof Raw) out += v.s;
    else if (Array.isArray(v)) out += v.map((x) => (x instanceof Raw ? x.s : esc(x))).join("");
    else if (v === false || v === null || v === undefined) out += "";
    else out += esc(v);
    out += strings[i + 1];
  });
  return raw(out);
}
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
function on(root, sel, ev, fn) {
  $$(sel, root).forEach((el) => el.addEventListener(ev, (e) => fn(e, el)));
}

async function api(path, { method = "GET", body, form } = {}) {
  const opts = { method, headers: {} };
  if (form) opts.body = form;
  else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers["Content-Type"] = "application/json"; }
  const res = await fetch("api/" + path, opts);
  let data = null;
  try { data = await res.json(); } catch { /* leer */ }
  if (!res.ok) {
    const msg = data?.error?.message || (data && data.detail ? (typeof data.detail === "string" ? data.detail : "Eingabe ungültig.") : `Fehler ${res.status}`);
    throw new Error(msg);
  }
  return data;
}

const NF = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const NF0 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
function money(cents, { plus = false } = {}) {
  if (cents === null || cents === undefined) return "–";
  const s = NF.format(Math.abs(cents) / 100) + " €";
  if (cents < 0) return "−" + s;
  return (plus && cents > 0 ? "+" : "") + s;
}
function moneyRound(cents) {
  if (cents === null || cents === undefined) return "–";
  return (cents < 0 ? "−" : "") + NF0.format(Math.abs(cents) / 100) + " €";
}
function parseMoney(text) {
  let s = String(text || "").trim().replace(/[€\s]/g, "").replace("−", "-");
  if (!s) return null;
  if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
  const v = Number(s);
  return Number.isFinite(v) ? Math.round(v * 100) : null;
}
const toInput = (cents) => (cents === null || cents === undefined ? "" : NF.format(cents / 100).replace(/\./g, ""));
const D = (iso) => new Date(iso + "T12:00:00");
const fmtShort = new Intl.DateTimeFormat("de-DE", { day: "numeric", month: "short" });
const fmtDay = new Intl.DateTimeFormat("de-DE", { weekday: "long", day: "numeric", month: "long" });
const fmtFull = new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
const fmtMonth = new Intl.DateTimeFormat("de-DE", { month: "long", year: "numeric" });
const dShort = (iso) => (iso ? fmtShort.format(D(iso)) : "–");
const dFull = (iso) => (iso ? fmtFull.format(D(iso)) : "–");
const todayIso = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
function relDay(iso) {
  const days = Math.round((D(iso) - D(todayIso())) / 86400000);
  if (days === 0) return "heute";
  if (days === 1) return "morgen";
  if (days === -1) return "gestern";
  if (days > 1 && days < 7) return `in ${days} Tagen`;
  return dShort(iso);
}
const KIND_LABEL = { giro: "Girokonto", tagesgeld: "Tagesgeld", sparkonto: "Sparkonto", festgeld: "Festgeld", vl: "VL / Bausparen", depot: "Depot", immobilie: "Immobilie", kredit: "Kredit", kreditkarte: "Kreditkarte", paypal: "PayPal", sonstiges: "Sonstiges" };
// Konten, deren Wert man einträgt statt Buchungen abzurufen.
const VALUE_KINDS = new Set(["depot", "festgeld", "vl", "immobilie", "kredit"]);
const SAVINGS_KINDS = new Set(["tagesgeld", "sparkonto", ...VALUE_KINDS]);
const MATURING_KINDS = new Set(["festgeld", "kredit"]);
const GROUP_LABEL = { alltag: "Alltag", ruecklagen: "Rücklagen", depots: "Depots", immobilien: "Immobilien", kredite: "Kredite" };

const ICON = {
  warn: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4m0 3v.01"/></svg>',
  info: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v5m0-8v.01"/></svg>',
  close: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  search: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5"/></svg>',
  file: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 14l2 2 4-4"/></svg>',
  bank: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 10l9-6 9 6M5 10v8m4.7-8v8m4.6-8v8M19 10v8M3 20h18"/></svg>',
  play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19V9m5 10V5m5 14v-7m5 7V8"/></svg>',
  sync: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 0 0-14.3-4.9L4 8m0-4v4h4M4 13a8 8 0 0 0 14.3 4.9L20 16m0 4v-4h-4"/></svg>',
  over: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v6m0 3v.01"/></svg>',
};

let toastTimer;
function toast(text) {
  const el = $("#toast");
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}

/* ------------------------------------------------------------------ Zustand */
const store = { cats: [], catById: new Map(), accounts: [], state: {} };
async function loadBase() {
  const [cats, accounts, state] = await Promise.all([api("categories"), api("accounts"), api("state")]);
  store.cats = cats;
  store.catById = new Map(cats.map((c) => [c.id, c]));
  store.accounts = accounts;
  store.state = state;
}
function catName(id) { return store.catById.get(id)?.name || "Ohne Kategorie"; }
function topCats() { return store.cats.filter((c) => !c.parent_id); }
function childCats(id) { return store.cats.filter((c) => c.parent_id === id); }

/* ------------------------------------------------------------------ Sheet */
let sheetStack = [];
function openSheet(content, { onClose, wide = false } = {}) {
  const root = $("#sheet-root");
  const back = document.createElement("div");
  back.className = "sheet-backdrop";
  back.innerHTML = `<div class="sheet" role="dialog" aria-modal="true" ${wide ? 'style="max-width:820px"' : ""}><div class="sheet-grip"></div>${content}</div>`;
  root.appendChild(back);
  const sheet = $(".sheet", back);
  const prevFocus = document.activeElement;
  const close = () => {
    back.remove();
    sheetStack = sheetStack.filter((s) => s !== api_);
    document.removeEventListener("keydown", onKey);
    if (onClose) onClose();
    if (prevFocus && prevFocus.focus) prevFocus.focus();
  };
  const onKey = (e) => { if (e.key === "Escape" && sheetStack[sheetStack.length - 1] === api_) close(); };
  document.addEventListener("keydown", onKey);
  back.addEventListener("mousedown", (e) => { if (e.target === back) close(); });
  on(sheet, "[data-close]", "click", close);
  const api_ = { el: sheet, close, set(content2) { sheet.innerHTML = `<div class="sheet-grip"></div>${content2}`; on(sheet, "[data-close]", "click", close); } };
  sheetStack.push(api_);
  setTimeout(() => { const f = $("[autofocus]", sheet) || $("h2", sheet); if (f) { f.setAttribute("tabindex", "-1"); f.focus(); } }, 30);
  return api_;
}
const sheetHead = (title) => html`<div class="sheet-head"><h2>${title}</h2><button class="icon-btn" data-close aria-label="Schließen">${raw(ICON.close)}</button></div>`;

function confirmButton(btn, label, fn) {
  let armed = false;
  btn.addEventListener("click", async () => {
    if (!armed) { armed = true; btn.dataset.label = btn.textContent; btn.textContent = label; setTimeout(() => { armed = false; btn.textContent = btn.dataset.label; }, 4000); return; }
    await fn();
  });
}

/* ------------------------------------------------------------------ Router */
const routes = {
  "": renderOverview, umsaetze: renderTransactions, vertraege: renderContracts, budgets: renderBudgets,
  konten: renderAccounts, einstellungen: renderSettings,
};
const TAB_FOR = { "": "uebersicht", umsaetze: "umsaetze", vertraege: "vertraege", budgets: "budgets", konten: "konten" };
function parseHash() {
  const h = location.hash.replace(/^#\/?/, "");
  const [path, qs] = h.split("?");
  return { path: path || "", params: Object.fromEntries(new URLSearchParams(qs || "")) };
}
function go(path, params) {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  location.hash = "#/" + path + qs;
}
let renderSeq = 0;
async function route() {
  const { path, params } = parseHash();
  const tab = TAB_FOR[path];
  $$(".tabs a").forEach((a) => { if (a.dataset.tab === tab) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
  $(".settings-link").classList.toggle("active", path === "einstellungen");
  const view = $("#view");
  const seq = ++renderSeq;
  try {
    await loadBase();
    if (seq !== renderSeq) return;
    if (!store.state.accounts && !["konten", "einstellungen"].includes(path)) {
      renderEmpty(view);
      return;
    }
    await (routes[path] || renderOverview)(view, params, seq);
  } catch (err) {
    if (seq !== renderSeq) return;
    view.innerHTML = html`<div class="empty"><h2>Das hat nicht geklappt</h2><p class="muted">${err.message}</p><button class="btn" id="retry">Neu laden</button></div>`.s;
    $("#retry").onclick = route;
  }
}
window.addEventListener("hashchange", () => { window.scrollTo(0, 0); route(); });
const rerender = () => route();

/* ------------------------------------------------------------------ Leerer Start */
function renderEmpty(view) {
  view.innerHTML = html`
    <section class="empty">
      <h1>Noch keine Konten</h1>
      <p class="muted">Lade einen Kontoauszug als Datei hoch oder verbinde dein Girokonto direkt per FinTS. Alles bleibt auf deinem Home Assistant.</p>
      <div class="start-options">
        <button class="start-option" id="start-file">${raw(ICON.file)}<div><strong>Kontoauszug-Datei importieren</strong>
          <span>CSV, CAMT oder MT940 – von Sparkasse, Volksbank, ING, DKB, comdirect, N26, Revolut, PayPal, Amex und anderen.</span></div></button>
        <button class="start-option" id="start-bank">${raw(ICON.bank)}<div><strong>Bank verbinden</strong>
          <span>Umsätze automatisch abrufen – per Open Banking (auch N26, Revolut) oder FinTS, mit Freigabe in deiner Banking-App.</span></div></button>
        <button class="start-option" id="start-demo">${raw(ICON.play)}<div><strong>Mit Beispieldaten ausprobieren</strong>
          <span>Sieben Monate erfundene Buchungen. Mit einem Klick wieder entfernt.</span></div></button>
      </div>
    </section>`.s;
  $("#start-file").onclick = () => pickImportFile();
  $("#start-bank").onclick = async () => bankChooser(await api("eb"));
  $("#start-demo").onclick = async () => {
    $("#start-demo").disabled = true;
    await api("demo", { method: "POST" });
    toast("Beispieldaten geladen");
    rerender();
  };
}

/* ------------------------------------------------------------------ Übersicht */
async function renderOverview(view, _params, seq) {
  const o = await api("overview");
  if (seq !== renderSeq) return;
  const fc = o.forecast;
  const free = fc.free_cents;
  const freeAbs = Math.abs(free);
  const euros = NF0.format(Math.floor(freeAbs / 100));
  const cents = String(freeAbs % 100).padStart(2, "0");
  const periodText = fc.period_label === "bis zum nächsten Gehalt"
    ? `frei bis zum Gehalt am ${dShort(new Date(D(fc.period_end).getTime() + 86400000).toISOString().slice(0, 10))}`
    : `frei bis Monatsende`;
  const perDay = fc.free_per_day_cents > 0 ? `, etwa ${moneyRound(fc.free_per_day_cents)} pro Tag` : "";
  const alerts = o.alerts.map((a) => html`
      <button class="alert ${a.level}" data-alert='${JSON.stringify({ c: a.contract || null, a: a.account || null, k: a.key, e: a.eb || null, i: a.inbox || null })}'>
        ${raw(a.level === "info" ? ICON.info : ICON.warn)}<div><strong>${a.title}</strong><span>${a.text}</span></div></button>`);
  const upcoming = o.upcoming.slice(0, 8).map((u) => html`
      <li class="row static"><span class="title">${u.name}</span><span class="sub">${relDay(u.date)}${u.overdue ? ", überfällig" : ""}</span>
      <span class="amount ${u.amount_cents > 0 ? "pos" : ""}">${money(u.amount_cents, { plus: true })}</span></li>`);
  const budgets = o.budgets.slice(0, 4).map(budgetRow);
  const accounts = o.accounts.filter((a) => !a.archived).map((a) => html`
      <button class="acc-tile" data-acc="${a.id}"><div class="name">${a.name}</div>
      <div class="bal num">${a.balance_known ? money(a.balance_now) : "Stand fehlt"}</div></button>`);
  view.innerHTML = html`
    ${o.alerts.length ? html`<div class="alerts">${alerts}</div>` : ""}
    <div class="overview">
      <div>
        <section class="tally" aria-label="Kassensturz">
          <ul class="tally-lines">
            <li><span class="op"></span><span>Kontostand heute</span><span class="amount">${money(fc.balance_now)}</span></li>
            ${fc.fixed_in_cents ? html`<li><span class="op">+</span><span>feste Eingänge bis ${dShort(fc.period_end)}</span><span class="amount">${money(fc.fixed_in_cents)}</span></li>` : ""}
            <li><span class="op">−</span><span>feste Abbuchungen bis ${dShort(fc.period_end)}</span><span class="amount">${money(Math.abs(fc.fixed_out_cents))}</span></li>
            ${fc.buffer_cents ? html`<li><span class="op">−</span><span>Sicherheitspuffer</span><span class="amount">${money(fc.buffer_cents)}</span></li>` : ""}
            ${fc.reserve_deducted && fc.reserve_cents ? html`<li><span class="op">−</span><span>Rücklage für Jahreskosten</span><span class="amount">${money(fc.reserve_cents)}</span></li>` : ""}
          </ul>
          <div class="tally-sum">
            <span class="hero-number ${free < 0 ? "negative" : ""}">${free < 0 ? "−" : ""}${euros}<span class="cur">,${cents} €</span></span>
            <p class="hero-caption">${(periodText + perDay).replace(/\.$/, "")}. Für den Alltag gibst du sonst rund ${moneyRound(fc.variable_daily_cents * 30)} im Monat aus.</p>
          </div>
        </section>
        <section class="section">
          <div class="section-head"><h2>Kann ich mir das leisten?</h2></div>
          <form class="afford" id="afford-form"><input class="input" id="afford-amt" inputmode="decimal" placeholder="Betrag in Euro" aria-label="Betrag in Euro">
            <button class="btn primary" type="submit">Prüfen</button></form>
          <div id="afford-out" aria-live="polite"></div>
        </section>
        <section class="section">
          <div class="section-head"><h2>Kontostand und Prognose</h2></div>
          <div class="chart" id="fc-chart"></div>
          <div class="legend"><span><i></i>bisher</span><span><i class="dashed"></i>erwartet</span>
            ${fc.month_end_cents !== null ? html`<span>Monatsende: <strong class="num">${money(fc.month_end_cents)}</strong></span>` : ""}</div>
        </section>
      </div>
      <div>
        <section class="section">
          <div class="section-head"><h2>Als Nächstes</h2><a href="#/vertraege">Alle Verträge</a></div>
          ${o.upcoming.length ? html`<ul class="list">${upcoming}</ul>` : html`<p class="muted">In den nächsten zwei Wochen ist nichts Festes fällig.</p>`}
        </section>
        <section class="section">
          <div class="section-head"><h2>Budgets im ${fmtMonth.format(new Date()).split(" ")[0]}</h2><a href="#/budgets">Alle Budgets</a></div>
          ${o.budgets.length ? html`<div>${budgets}</div>` : html`<p class="muted">Noch keine Budgets. <a href="#/budgets">Budget festlegen</a></p>`}
        </section>
        <section class="section">
          <div class="section-head"><h2>Konten</h2><a href="#/konten">Verwalten</a></div>
          <div class="accounts-strip">${accounts}</div>
          <p class="small muted" style="margin-top:12px">Diesen Monat: Einnahmen <span class="num pos">${money(o.month.income_cents, { plus: true })}</span>,
            Ausgaben <span class="num">${money(-o.month.expense_cents)}</span>. Fixkosten insgesamt ${money(o.fixed_monthly_cents)} im Monat.</p>
        </section>
      </div>
    </div>`.s;
  forecastChart($("#fc-chart"), fc);
  $("#afford-form").onsubmit = async (e) => {
    e.preventDefault();
    const cents = parseMoney($("#afford-amt").value);
    if (cents === null || cents === 0) { toast("Bitte einen Betrag eintragen"); return; }
    try { $("#afford-out").innerHTML = affordHtml(await api("afford?amount_cents=" + Math.abs(cents))); } catch (err) { toast(err.message); }
  };
  on(view, "[data-acc]", "click", (_e, el) => go("umsaetze", { account: el.dataset.acc }));
  on(view, "[data-alert]", "click", async (_e, el) => {
    const d = JSON.parse(el.dataset.alert);
    if (d.c) { const list = await api("contracts"); const c = list.items.find((x) => x.key === d.c); if (c) contractSheet(c); }
    else if (d.a) { const acc = store.accounts.find((x) => x.id === d.a); if (acc) balanceSheet(acc); }
    else if (d.e) { const eb = await api("eb"); const s = eb.sessions.find((x) => x.id === d.e); if (s) ebConnectSheet(s); }
    else if (d.i) go("konten");
    else if (d.k.startsWith("budget")) go("budgets");
  });
  bindBudgetRows(view);
}

function bindBudgetRows(view) {
  on(view, "[data-budget]", "click", (_e, el) => budgetSheet(Number(el.dataset.budget)));
  on(view, "[data-budget]", "keydown", (e, el) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); budgetSheet(Number(el.dataset.budget)); } });
}

function budgetRow(b) {
  const pct = Math.min(100, Math.round(b.ratio * 100));
  const state = b.state === "over" ? html`<span class="state over">${raw(ICON.over)}überschritten</span>`
    : b.state === "warn" ? html`<span class="state warn">${raw(ICON.warn)}knapp</span>` : "";
  return html`<div class="budget-row" data-budget="${b.category_id}" role="button" tabindex="0" style="cursor:pointer">
      <div><span class="title">${b.name}</span> ${state}</div>
      <div class="num small">${money(b.spent_cents)} <span class="muted">von ${moneyRound(b.budget_cents)}</span></div>
      <div class="meter" title="${pct} % ausgegeben, ${Math.round(b.pace * 100)} % des Monats vorbei">
        <div class="fill ${b.state === "over" ? "over" : b.state === "warn" ? "warn" : ""}" style="width:${pct}%"></div>
        <div class="pace" style="left:calc(${Math.round(b.pace * 1000) / 10}% - 1px)"></div></div>
      <div class="tiny muted" style="grid-column:1/-1">${b.left_cents >= 0 ? `noch ${money(b.left_cents)} übrig` : `${money(-b.left_cents)} drüber`}</div>
    </div>`;
}

/* ------------------------------------------------------------------ Diagramm: Prognose */
function forecastChart(el, fc) {
  const past = fc.past.slice(-31).map(([d, v]) => ({ d, v, f: false }));
  const fut = fc.future.map(([d, v]) => ({ d, v, f: true }));
  const pts = [...past, ...fut];
  if (pts.length < 2) { el.innerHTML = '<p class="muted">Noch zu wenig Daten für einen Verlauf.</p>'; return; }
  const W = Math.max(300, el.clientWidth || 600), H = 190, L = 54, R = 8, T = 12, B = 24;
  let min = Math.min(...pts.map((p) => p.v), 0), max = Math.max(...pts.map((p) => p.v));
  const pad = (max - min) * 0.08 || 10000;
  min -= min < 0 ? pad : 0; max += pad;
  const step = niceStep((max - min) / 4);
  min = Math.floor(min / step) * step; max = Math.ceil(max / step) * step;
  const x = (i) => L + (i / (pts.length - 1)) * (W - L - R);
  const y = (v) => T + (1 - (v - min) / (max - min)) * (H - T - B);
  const ti = past.length - 1;
  const path = (arr, off) => arr.map((p, i) => `${i ? "L" : "M"}${x(i + off).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
  let grid = "";
  for (let v = min; v <= max + 1; v += step) {
    grid += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${moneyRound(v)}</text>`;
  }
  let xl = "";
  pts.forEach((p, i) => {
    if (p.d.endsWith("-01") && Math.abs(x(i) - x(ti)) > 44) xl += `<text class="axis" x="${x(i)}" y="${H - 6}" text-anchor="middle">${fmtShort.format(D(p.d))}</text>`;
  });
  xl += `<text class="axis" x="${x(ti)}" y="${H - 6}" text-anchor="middle" style="font-weight:600">heute</text>`;
  const low = fut.reduce((a, p, i) => (p.v < a.v ? { ...p, i: i + past.length } : a), { v: Infinity, i: -1 });
  const svg = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="Kontostand der letzten 30 Tage und Prognose für ${fut.length} Tage">
    ${grid}
    ${min < 0 ? `<line class="threshold" x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}"/>` : ""}
    <path class="area" d="${path(past, 0)}L${x(ti)},${y(min)}L${x(0)},${y(min)}Z"/>
    <path class="line" d="${path(past, 0)}"/>
    <path class="line future" d="${path([past[ti], ...fut], ti)}"/>
    <line class="today" x1="${x(ti)}" x2="${x(ti)}" y1="${T}" y2="${H - B}"/>
    ${low.i > 0 ? `<circle class="dot low" cx="${x(low.i)}" cy="${y(low.v)}" r="4.5"/>` : ""}
    ${xl}
    <line class="cross" id="fc-cross" y1="${T}" y2="${H - B}" style="display:none"/>
    <circle class="dot" id="fc-dot" r="4.5" style="display:none"/>
  </svg><div class="tooltip" id="fc-tip"></div>`;
  el.innerHTML = svg;
  const s = $("svg", el), tip = $("#fc-tip", el), cross = $("#fc-cross", el), dot = $("#fc-dot", el);
  const move = (clientX) => {
    const r = s.getBoundingClientRect();
    const px = ((clientX - r.left) / r.width) * W;
    const i = Math.max(0, Math.min(pts.length - 1, Math.round(((px - L) / (W - L - R)) * (pts.length - 1))));
    const p = pts[i];
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.style.display = "";
    dot.setAttribute("cx", x(i)); dot.setAttribute("cy", y(p.v)); dot.style.display = "";
    tip.innerHTML = `${esc(i === ti ? "heute" : fmtShort.format(D(p.d)))}: <strong>${esc(money(p.v))}</strong>${p.f ? " erwartet" : ""}`;
    tip.style.left = `${(x(i) / W) * 100}%`; tip.style.top = `${(y(p.v) / H) * r.height}px`;
    tip.classList.add("show");
  };
  const hide = () => { tip.classList.remove("show"); cross.style.display = "none"; dot.style.display = "none"; };
  s.addEventListener("pointermove", (e) => move(e.clientX));
  s.addEventListener("pointerdown", (e) => move(e.clientX));
  s.addEventListener("pointerleave", hide);
}
function niceStep(raw_) {
  const mag = Math.pow(10, Math.floor(Math.log10(Math.max(1, raw_))));
  const n = raw_ / mag;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
}

/* ------------------------------------------------------------------ Umsätze */
const txState = { offset: 0, items: [] };
async function renderTransactions(view, params, seq) {
  const months = [];
  const now = new Date();
  for (let i = 0; i < 14; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    months.push({ v: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`, l: fmtMonth.format(d) });
  }
  const kinds = [["", "Alle"], ["out", "Ausgaben"], ["in", "Einnahmen"], ["transfer", "Umbuchungen"], ["uncat", "Ohne Kategorie"]];
  const catOptions = topCats().map((c) => html`<option value="${c.id}" ${String(c.id) === params.category ? raw("selected") : ""}>${c.name}</option>${childCats(c.id).map((ch) => html`<option value="${ch.id}" ${String(ch.id) === params.category ? raw("selected") : ""}>\u00a0\u00a0${ch.name}</option>`)}`);
  view.innerHTML = html`
    <div class="page-head"><h1>Umsätze</h1>
      <button class="btn small" id="tx-import">${raw(ICON.file)}Datei importieren</button></div>
    <div class="filters">
      <label class="search">${raw(ICON.search)}<input id="tx-q" type="search" placeholder="Suchen nach Name, Zweck oder Betrag" value="${params.q || ""}" aria-label="Suchen"></label>
      <select id="tx-account" aria-label="Konto"><option value="">Alle Konten</option>${store.accounts.map((a) => html`<option value="${a.id}" ${String(a.id) === params.account ? raw("selected") : ""}>${a.name}</option>`)}</select>
      <select id="tx-cat" aria-label="Kategorie"><option value="">Alle Kategorien</option>${catOptions}</select>
      <select id="tx-month" aria-label="Monat"><option value="">Alle Monate</option>${months.map((m) => html`<option value="${m.v}" ${m.v === params.month ? raw("selected") : ""}>${m.l}</option>`)}</select>
    </div>
    <div class="filters"><div class="segmented" role="group" aria-label="Art">${kinds.map(([v, l]) => html`<button data-kind="${v}" aria-pressed="${(params.kind || "") === v}">${l}</button>`)}</div></div>
    ${params.contract ? html`<p class="small">Gefiltert nach Vertrag. <a href="#/umsaetze">Filter entfernen</a></p>` : ""}
    <p class="small muted" id="tx-summary"></p>
    <div id="tx-list"></div>
    <div class="actions" id="tx-more-wrap" hidden><button class="btn" id="tx-more">Weitere laden</button></div>`.s;
  const update = (patch) => {
    const p = { ...params, ...patch };
    Object.keys(p).forEach((k) => { if (p[k] === "" || p[k] === undefined) delete p[k]; });
    history.replaceState(null, "", "#/umsaetze" + (Object.keys(p).length ? "?" + new URLSearchParams(p) : ""));
    Object.assign(params, patch);
    loadTx(params, true);
  };
  let t;
  $("#tx-q").addEventListener("input", (e) => { clearTimeout(t); t = setTimeout(() => update({ q: e.target.value.trim() }), 250); });
  $("#tx-account").onchange = (e) => update({ account: e.target.value });
  $("#tx-cat").onchange = (e) => update({ category: e.target.value });
  $("#tx-month").onchange = (e) => update({ month: e.target.value });
  on(view, "[data-kind]", "click", (_e, el) => { $$("[data-kind]").forEach((b) => b.setAttribute("aria-pressed", b === el)); update({ kind: el.dataset.kind }); });
  $("#tx-more").onclick = () => loadTx(params, false);
  $("#tx-import").onclick = () => pickImportFile();
  await loadTx(params, true, seq);
}
async function loadTx(params, reset, seq) {
  if (reset) { txState.offset = 0; txState.items = []; }
  const q = new URLSearchParams({ offset: txState.offset, limit: 100 });
  ["q", "account", "category", "month", "kind", "contract"].forEach((k) => { if (params[k]) q.set(k, params[k]); });
  const res = await api("transactions?" + q);
  if (seq && seq !== renderSeq) return;
  txState.items.push(...res.items);
  txState.offset += res.items.length;
  $("#tx-summary").textContent = `${res.total} Buchungen. Einnahmen ${money(res.sum_in, { plus: true })}, Ausgaben ${money(res.sum_out)}.`;
  $("#tx-more-wrap").hidden = txState.offset >= res.total;
  const list = $("#tx-list");
  if (!txState.items.length) { list.innerHTML = '<p class="muted">Keine Buchungen gefunden.</p>'; return; }
  let out = "", day = null;
  const sums = {};
  txState.items.forEach((t) => { sums[t.booking_date] = (sums[t.booking_date] || 0) + (t.is_transfer ? 0 : t.amount_cents); });
  txState.items.forEach((t) => {
    if (t.booking_date !== day) {
      if (day) out += "</ul>";
      day = t.booking_date;
      out += html`<div class="day-head"><span>${fmtDay.format(D(day))}</span><span class="num">${sums[day] ? money(sums[day], { plus: true }) : ""}</span></div><ul class="list">`.s;
    }
    out += txRow(t).s;
  });
  list.innerHTML = out + "</ul>";
  on(list, "[data-tx]", "click", (_e, el) => txSheet(txState.items.find((x) => x.id === Number(el.dataset.tx))));
}
function txRow(t) {
  const name = t.counterparty || t.purpose || t.booking_text || "Ohne Bezeichnung";
  const cat = t.splits && t.splits.length ? "Aufgeteilt" : (t.is_transfer ? "Umbuchung" : t.category_name || "Ohne Kategorie");
  const sub = [cat, store.accounts.length > 1 ? t.account_name : null, t.note].filter(Boolean).join(", ");
  return html`<li><button class="row" data-tx="${t.id}"><span class="title">${name}</span><span class="sub">${sub}</span>
    <span class="amount ${t.amount_cents > 0 && !t.is_transfer ? "pos" : ""} ${t.is_transfer ? "muted" : ""}">${money(t.amount_cents, { plus: true })}</span></button></li>`;
}

function categoryPicker(selectedId, amount) {
  const prefer = amount > 0 ? "income" : "expense";
  const tops = topCats().slice().sort((a, b) => (a.kind === prefer ? -1 : 0) - (b.kind === prefer ? -1 : 0));
  return html`<input class="input" id="cat-filter" placeholder="Kategorie suchen" style="width:100%;margin-top:8px" aria-label="Kategorie suchen">
    <div class="cat-list" id="cat-list">${tops.map((c) => html`
      <button class="parent" data-cat="${c.id}" aria-pressed="${c.id === selectedId}">${c.name}</button>
      ${childCats(c.id).map((ch) => html`<button class="child" data-cat="${ch.id}" aria-pressed="${ch.id === selectedId}">${ch.name}</button>`)}`)}</div>`;
}
function bindCategoryPicker(root, onPick) {
  on(root, "#cat-list [data-cat]", "click", (_e, el) => {
    $$("#cat-list [data-cat]", root).forEach((b) => b.setAttribute("aria-pressed", b === el));
    onPick(Number(el.dataset.cat));
  });
  $("#cat-filter", root).addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    $$("#cat-list [data-cat]", root).forEach((b) => { b.hidden = q && !b.textContent.toLowerCase().includes(q); });
  });
}

async function txSheet(t) {
  const name = t.counterparty || t.purpose || "Buchung";
  const rule = t.rule_ref || "";
  const how = t.category_locked ? "von dir gesetzt" : rule.startsWith("user:") ? "durch deine Regel" : rule === "learned" ? "aus deiner Korrektur gelernt" : rule.startsWith("builtin") ? "automatisch erkannt"
    : rule === "own-iban" ? "Überweisung zwischen eigenen Konten" : rule.startsWith("settlement") ? "Ausgleich eines anderen Kontos"
    : rule === "paypal-funding" ? "Aufladung des PayPal-Kontos" : rule === "card-payment" ? "Ausgleich der Kartenabrechnung" : "keine Regel gefunden";
  const sh = openSheet(html`
    ${sheetHead(name)}
    <div class="big-amount ${t.amount_cents > 0 ? "pos" : ""}">${money(t.amount_cents, { plus: true })}</div>
    <dl class="facts">
      <dt>Gebucht</dt><dd>${dFull(t.booking_date)}${t.value_date && t.value_date !== t.booking_date ? `, Wertstellung ${dFull(t.value_date)}` : ""}</dd>
      <dt>Konto</dt><dd>${t.account_name}</dd>
      ${t.purpose ? html`<dt>Zweck</dt><dd>${t.purpose}</dd>` : ""}
      ${t.booking_text ? html`<dt>Art</dt><dd>${t.booking_text}</dd>` : ""}
      ${t.counterparty_iban ? html`<dt>IBAN</dt><dd>${t.counterparty_iban}</dd>` : ""}
      ${t.creditor_id ? html`<dt>Gläubiger-ID</dt><dd>${t.creditor_id}${t.mandate_ref ? `, Mandat ${t.mandate_ref}` : ""}</dd>` : ""}
      ${t.contract_key ? html`<dt>Vertrag</dt><dd><button class="link-btn" id="tx-contract">Vertrag ansehen</button></dd>` : ""}
    </dl>
    <h3>Kategorie</h3>
    <p class="small muted">${t.splits.length ? "Aufgeteilt in " + t.splits.map((s) => `${catName(s.category_id)} ${money(s.amount_cents)}`).join(", ") : `${t.is_transfer ? "Umbuchung" : catName(t.category_id)}, ${how}.`}</p>
    <details id="tx-cat-details"><summary class="link-btn">Kategorie ändern</summary>
    ${categoryPicker(t.category_id, t.amount_cents)}
    <div id="rule-box"></div></details>
    <label class="field"><span>Notiz</span><input class="input" id="tx-note" value="${t.note || ""}" maxlength="200"></label>
    <h3>Steuer und Belege</h3>
    <label class="field"><span>Für die Steuererklärung</span><select class="input" id="tx-tax">
      <option value="">Nicht relevant</option>
      ${TAX_KINDS.map(([k, label]) => html`<option value="${k}" ${t.tax_kind === k ? raw("selected") : ""}>${label}</option>`)}
    </select></label>
    ${t.amount_cents < 0 ? html`<label class="field"><span>Garantie bis</span>
      <input class="input" id="tx-warranty" type="date" value="${t.warranty_until || ""}"></label>
    <div class="actions" style="margin-top:0">
      <button class="btn small" type="button" data-warranty-years="2">2 Jahre</button>
      <button class="btn small" type="button" data-warranty-years="3">3 Jahre</button>
      <button class="btn small" type="button" data-warranty-years="5">5 Jahre</button>
      <button class="btn small" type="button" data-warranty-years="0">Keine</button>
    </div>` : ""}
    <div id="tx-receipts"></div>
    <div class="actions">
      <button class="btn primary" id="tx-save">Speichern</button>
      <button class="btn" id="tx-split">Aufteilen</button>
      ${t.category_locked ? html`<button class="btn" id="tx-reset">Automatisch zuordnen</button>` : ""}
    </div>`.s);
  let picked = null;
  $("#tx-cat-details", sh.el).addEventListener("toggle", (e) => {
    const sel = $('#cat-list [aria-pressed="true"]', sh.el);
    if (e.target.open && sel) sel.scrollIntoView({ block: "center" });
  });
  bindCategoryPicker(sh.el, async (id) => {
    picked = id;
    const s = await api(`transactions/${t.id}/suggest-rule`);
    if (!s.pattern) { $("#rule-box", sh.el).innerHTML = ""; return; }
    $("#rule-box", sh.el).innerHTML = html`<label class="check"><input type="checkbox" id="rule-on" checked>
      <span>Auch künftig so zuordnen, wenn „<input class="input" id="rule-pattern" value="${s.pattern}" style="min-height:30px;padding:2px 6px;width:12em">“ vorkommt
      <span class="muted small">(passt aktuell auf ${s.matches} Buchungen)</span></span></label>`.s;
  });
  $("#tx-save", sh.el).onclick = async () => {
    const body = { note: $("#tx-note", sh.el).value, tax_kind: $("#tx-tax", sh.el).value || null };
    if ($("#tx-warranty", sh.el)) body.warranty_until = $("#tx-warranty", sh.el).value || null;
    if (picked) {
      body.category_id = picked;
      if ($("#rule-on", sh.el)?.checked && $("#rule-pattern", sh.el).value.trim()) {
        body.rule = { pattern: $("#rule-pattern", sh.el).value.trim(), sign: t.amount_cents > 0 ? "in" : "out" };
      } else if ($("#rule-on", sh.el)) {
        body.learn = false; // Haken entfernt: nur diese eine Buchung
      }
    }
    const r = await api(`transactions/${t.id}`, { method: "PATCH", body });
    sh.close();
    toast(r.recategorized ? `Gespeichert, ${r.recategorized} weitere Buchungen neu zugeordnet` : "Gespeichert");
    rerender();
  };
  $$("[data-warranty-years]", sh.el).forEach((b) => b.onclick = () => {
    const years = Number(b.dataset.warrantyYears);
    // Vom Kaufdatum aus gerechnet; der 29.2. landet auf dem 28.2.
    const [y, m, d] = t.booking_date.split("-").map(Number);
    const last = new Date(Date.UTC(y + years, m, 0)).getUTCDate();
    $("#tx-warranty", sh.el).value = years ? `${y + years}-${String(m).padStart(2, "0")}-${String(Math.min(d, last)).padStart(2, "0")}` : "";
  });
  bindReceipts($("#tx-receipts", sh.el), t.id);
  $("#tx-split", sh.el).onclick = () => { sh.close(); splitSheet(t); };
  if ($("#tx-reset", sh.el)) $("#tx-reset", sh.el).onclick = async () => { await api(`transactions/${t.id}/reset`, { method: "POST" }); sh.close(); toast("Wieder automatisch zugeordnet"); rerender(); };
  if ($("#tx-contract", sh.el)) $("#tx-contract", sh.el).onclick = async () => {
    const list = await api("contracts");
    const c = list.items.find((x) => x.key === t.contract_key);
    sh.close();
    if (c) contractSheet(c);
  };
}

const TAX_KINDS = [["handwerker", "Handwerkerleistung"], ["haushaltsnah", "Haushaltsnahe Dienstleistung"],
  ["arbeitsmittel", "Arbeitsmittel und Werbungskosten"], ["spende", "Spende"], ["versicherung", "Versicherung und Vorsorge"],
  ["gesundheit", "Krankheitskosten"], ["kinder", "Kinderbetreuung"], ["sonstiges", "Sonstiges"]];

function fileSize(bytes) {
  return bytes >= 1048576 ? NF.format(bytes / 1048576).replace(/\d$/, "") + " MB" : NF0.format(Math.max(1, bytes / 1024)) + " KB";
}

// Belege einer Buchung: anzeigen, hochladen, entfernen. Wirkt sofort, ohne „Speichern“.
async function bindReceipts(box, txId) {
  const draw = async () => {
    let res;
    try { res = await api(`transactions/${txId}/receipts`); } catch { return; }
    box.innerHTML = html`
      ${res.items.length ? html`<ul class="list receipts">${res.items.map((r) => html`<li class="row static ${r.mime.startsWith("image/") ? "has-thumb" : ""}">
        ${r.mime.startsWith("image/") ? html`<a class="receipt-thumb" href="api/receipts/${r.id}" target="_blank" rel="noopener"><img src="api/receipts/${r.id}" alt="" loading="lazy"></a>` : ""}
        <span class="title"><a href="api/receipts/${r.id}" target="_blank" rel="noopener">${r.filename}</a></span>
        <span class="sub">${fileSize(r.size)}</span>
        <span class="amount"><button class="btn small" data-rcpt-del="${r.id}">Entfernen</button></span></li>`)}</ul>` : ""}
      ${res.items.length < res.max ? html`<label class="btn small receipt-add">Beleg hinzufügen
        <input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" hidden></label>
        <span class="small muted" id="rcpt-status">${res.items.length ? "" : "Foto oder PDF, bis 10 MB."}</span>` : ""}`.s;
    $$("[data-rcpt-del]", box).forEach((b) => b.onclick = async () => {
      try { await api(`receipts/${b.dataset.rcptDel}`, { method: "DELETE" }); } catch (e) { toast(e.message); }
      draw();
    });
    const input = $('input[type="file"]', box);
    if (input) input.onchange = async () => {
      const f = input.files[0];
      if (!f) return;
      const form = new FormData();
      form.append("file", f);
      $("#rcpt-status", box).textContent = "Wird hochgeladen …";
      try { await api(`transactions/${txId}/receipts`, { method: "POST", form }); toast("Beleg gespeichert"); }
      catch (e) { toast(e.message); }
      draw();
    };
  };
  await draw();
}

async function drawWarranties(box) {
  let w;
  try { w = await api("warranties"); } catch { return; }
  const left = (n) => n === 0 ? "endet heute" : n === 1 ? "noch 1 Tag" : n < 60 ? `noch ${n} Tage` : `noch ${Math.round(n / 30.4)} Monate`;
  const row = (i, sub) => html`<li class="row static">
    <span class="title">${i.label}</span>
    <span class="sub">${sub}${i.receipt_count ? "" : ", ohne Beleg"}</span>
    <span class="amount">${dFull(i.warranty_until)}</span></li>`;
  box.innerHTML = (w.running.length || w.expired.length) ? html`
    ${w.running.length ? html`<ul class="list">${w.running.map((i) => row(i, `${money(-i.amount_cents)}, ${left(i.days_left)}`))}</ul>` : ""}
    ${w.expired.length ? html`<p class="small muted" style="margin-top:14px">Kürzlich abgelaufen</p>
      <ul class="list">${w.expired.map((i) => row(i, `${money(-i.amount_cents)}, abgelaufen`))}</ul>` : ""}
    <p class="small muted">30 Tage vor dem Ende erinnert Kassensturz in der Übersicht und per Mitteilung.</p>`.s
    : html`<p class="small muted">Noch keine Garantie eingetragen. Öffne den Kauf unter Umsätze und setze „Garantie bis“. Kassensturz erinnert 30 Tage vor dem Ende.</p>`.s;
}

async function drawTax(box, year) {
  let t;
  try { t = await api("tax" + (year ? `?year=${year}` : "")); } catch { return; }
  const years = t.years.includes(t.year) ? t.years : [t.year, ...t.years];
  box.innerHTML = html`
    ${t.count ? html`
      <div class="actions" style="margin-top:0">
        <select class="input" id="tax-year" aria-label="Jahr" style="width:auto">${years.map((y) => html`<option value="${y}" ${y === t.year ? raw("selected") : ""}>${y}</option>`)}</select>
        <a class="btn small" href="api/tax.csv?year=${t.year}" download>Als CSV</a>
      </div>
      <ul class="list">${t.groups.map((g) => html`<li class="row" data-tax-kind="${g.kind}" tabindex="0" role="button">
        <span class="title">${g.label}</span>
        <span class="sub">${g.count} ${g.count === 1 ? "Buchung" : "Buchungen"}${g.missing_receipts ? `, ${g.missing_receipts} ohne Beleg` : ""}</span>
        <span class="amount">${money(g.total_cents)}</span></li>`)}</ul>
      <p class="small muted">Zusammen ${money(t.total_cents)} in ${t.year}. Die Liste ist eine Sammlung für die Steuererklärung, keine Steuerberatung.</p>`
      : html`<p class="small muted">Noch nichts markiert. Öffne eine Buchung und wähle unter „Für die Steuererklärung“ eine Art, zum Beispiel Handwerkerleistung oder Spende. Hier sammelt Kassensturz sie dann je Jahr.</p>`}`.s;
  if ($("#tax-year", box)) $("#tax-year", box).onchange = (e) => drawTax(box, e.target.value);
  $$("[data-tax-kind]", box).forEach((row) => {
    const open = () => {
      const g = t.groups.find((x) => x.kind === row.dataset.taxKind);
      openSheet(html`${sheetHead(`${g.label} ${t.year}`)}
        <ul class="list">${g.items.map((i) => html`<li class="row static">
          <span class="title">${i.counterparty || i.purpose || "Buchung"}</span>
          <span class="sub">${dFull(i.booking_date)}, ${i.receipt_count ? (i.receipt_count === 1 ? "1 Beleg" : `${i.receipt_count} Belege`) : "ohne Beleg"}</span>
          <span class="amount">${money(-i.amount_cents)}</span></li>`)}</ul>
        <p class="small muted">Summe ${money(g.total_cents)}. Belege hängst du in der Buchung an, unter Umsätze.</p>`.s);
    };
    row.onclick = open;
    row.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } };
  });
}

function splitSheet(t) {
  const sign = t.amount_cents < 0 ? -1 : 1;
  let parts = t.splits.length ? t.splits.map((s) => ({ amount: Math.abs(s.amount_cents), cat: s.category_id })) : [{ amount: Math.abs(t.amount_cents), cat: t.category_id }, { amount: 0, cat: null }];
  const catSelect = (sel, i) => html`<select data-pcat="${i}" aria-label="Kategorie">${topCats().map((c) => html`<option value="${c.id}" ${c.id === sel ? raw("selected") : ""}>${c.name}</option>${childCats(c.id).map((ch) => html`<option value="${ch.id}" ${ch.id === sel ? raw("selected") : ""}>\u00a0\u00a0${ch.name}</option>`)}`)}</select>`;
  const sh = openSheet("");
  const draw = () => {
    const used = parts.reduce((a, p) => a + (p.amount || 0), 0);
    const rest = Math.abs(t.amount_cents) - used;
    sh.set(html`${sheetHead("Buchung aufteilen")}
      <p class="muted small">${t.counterparty || ""}, ${money(t.amount_cents)}. Ein nicht verteilter Rest behält die ursprüngliche Kategorie.</p>
      <table class="map-table">${parts.map((p, i) => html`<tr><td style="width:38%"><input class="input" data-pamt="${i}" inputmode="decimal" value="${p.amount ? toInput(p.amount) : ""}" placeholder="0,00" style="width:100%"></td><td>${catSelect(p.cat, i)}</td></tr>`)}</table>
      <p class="small ${rest < 0 ? "" : "muted"}" style="${rest < 0 ? "color:var(--crit)" : ""}">${rest >= 0 ? `Rest: ${money(rest)}` : `${money(-rest)} zu viel verteilt`}</p>
      <div class="actions"><button class="btn" id="sp-add">Zeile hinzufügen</button><button class="btn primary" id="sp-save" ${rest < 0 ? raw("disabled") : ""}>Speichern</button>
      ${t.splits.length ? html`<button class="btn danger" id="sp-clear">Aufteilung entfernen</button>` : ""}</div>`.s);
    on(sh.el, "[data-pamt]", "change", (e, el) => { parts[Number(el.dataset.pamt)].amount = Math.abs(parseMoney(el.value) || 0); draw(); });
    on(sh.el, "[data-pcat]", "change", (e, el) => { parts[Number(el.dataset.pcat)].cat = Number(el.value); });
    $("#sp-add", sh.el).onclick = () => { parts.push({ amount: 0, cat: null }); draw(); };
    $("#sp-save", sh.el).onclick = async () => {
      $$("[data-pcat]", sh.el).forEach((el) => { parts[Number(el.dataset.pcat)].cat = Number(el.value); });
      const splits = parts.filter((p) => p.amount > 0).map((p) => ({ amount_cents: sign * p.amount, category_id: p.cat }));
      try { await api(`transactions/${t.id}/splits`, { method: "PUT", body: { splits } }); sh.close(); toast("Aufteilung gespeichert"); rerender(); }
      catch (e) { toast(e.message); }
    };
    if ($("#sp-clear", sh.el)) $("#sp-clear", sh.el).onclick = async () => { await api(`transactions/${t.id}/splits`, { method: "PUT", body: { splits: [] } }); sh.close(); rerender(); };
  };
  draw();
}

/* ------------------------------------------------------------------ Verträge */
async function renderContracts(view, _params, seq) {
  const data = await api("contracts");
  if (seq !== renderSeq) return;
  const today = todayIso();
  const items = data.items;
  const isCancelledPast = (c) => c.status === "cancelled" && (!c.cancel_effective || c.cancel_effective < today);
  const running = items.filter((c) => c.kind === "expense" && c.status !== "ignored" && c.active && !isCancelledPast(c) && c.status !== "cancelled");
  const cancelled = items.filter((c) => c.status === "cancelled");
  const income = items.filter((c) => c.kind === "income" && c.status !== "ignored" && c.active);
  const ended = items.filter((c) => !c.active && !c.manual && c.status !== "ignored" && c.status !== "cancelled");
  const ignored = items.filter((c) => c.status === "ignored");
  const priceUp = running.filter((c) => c.price_change_cents && c.price_change_cents < 0).length;
  const deadlineItems = running
    .filter((c) => c.deadline && c.days_to_deadline <= 90)
    .sort((a, b) => a.days_to_deadline - b.days_to_deadline);
  const pendingCancellations = data.pending_cancellations || [];
  const cancellationStatus = {
    prepared: "Vorbereitet – Versand noch offen",
    handed_off: "An Mail-App übergeben – Versand bestätigen",
    sent: "Versendet – Anbieterbestätigung offen",
  };
  const cancellationMode = { ordinary: "Fristgerechte Kündigung", extraordinary: "Sonderkündigung", withdrawal: "Widerruf" };
  const row = (c) => {
    const chips = [];
    if (c.price_change_cents && c.kind === "expense" && c.price_change_cents < 0) chips.push(html`<span class="chip warn">${money(-c.price_change_cents, { plus: true })}</span>`);
    if (c.days_to_deadline !== null && c.days_to_deadline <= 90) {
      const urgency = c.days_to_deadline < 0 || c.days_to_deadline <= 45 ? "crit" : "warn";
      const label = c.days_to_deadline < 0 ? "Frist abgelaufen" : `Frist ${dShort(c.deadline)}`;
      chips.push(html`<span class="chip ${urgency}">${label}</span>`);
    }
    if (c.status === "cancelled") chips.push(html`<span class="chip neutral">gekündigt${c.cancel_effective ? " zum " + dShort(c.cancel_effective) : ""}</span>`);
    const sub = c.active ? `${c.interval}, nächste ${relDay(c.next_due)}` : `zuletzt ${dShort(c.last_date)}`;
    const monthly = c.interval !== "monatlich" && c.monthly_cents ? html`<small>≈ ${money(c.monthly_cents)} im Monat</small>` : "";
    return html`<li><button class="row" data-contract="${c.key}"><span class="title">${c.name} ${chips}</span><span class="sub">${sub}${c.category_name ? ", " + c.category_name : ""}</span>
      <span class="amount ${c.kind === "income" ? "pos" : ""}">${money(c.amount_cents, { plus: true })}${monthly}</span></button></li>`;
  };
  const section = (title, list, note) => list.length ? html`<section class="section"><div class="section-head"><h2>${title}</h2><span class="small muted">${note || ""}</span></div><ul class="list">${list.map(row)}</ul></section>` : "";
  view.innerHTML = html`
    <div class="page-head"><h1>Verträge und Abos</h1><button class="btn small" id="c-add">Vertrag hinzufügen</button></div>
    <section class="tally" style="padding-top:4px">
      <span class="hero-number" style="font-size:clamp(2.6rem,11vw,4rem)">${NF0.format(Math.floor(Math.abs(data.fixed_monthly_cents) / 100))}<span class="cur">,${String(Math.abs(data.fixed_monthly_cents) % 100).padStart(2, "0")} €</span></span>
      <p class="hero-caption">Fixkosten pro Monat aus ${running.length} laufenden Verträgen${priceUp ? html`, davon ${priceUp} zuletzt teurer geworden` : ""}. Jährliche und vierteljährliche Zahlungen sind anteilig eingerechnet.</p>
    </section>
    ${items.length ? "" : html`<p class="muted">Noch keine wiederkehrenden Zahlungen erkannt. Dafür braucht es meist drei Monate Umsätze.</p>`}
    ${pendingCancellations.length ? html`<section class="section">
      <div class="section-head"><h2>Offene Kündigungsvorgänge</h2><span class="small muted">${pendingCancellations.length} offen</span></div>
      <ul class="list">${pendingCancellations.map((event) => html`<li><button class="row" data-pending-contract="${event.contract_key}">
        <span class="title">${event.contract_name}</span>
        <span class="sub">${cancellationMode[event.mode] || "Kündigung"} · ${cancellationStatus[event.status] || event.status} · erstellt ${new Date(event.prepared_at).toLocaleDateString("de-DE")}</span>
        <span class="amount">Öffnen</span></button></li>`)}</ul>
    </section>` : ""}
    <div class="cols"><div>
      ${section("Kündigungsfristen", deadlineItems, "überfällig oder innerhalb von 90 Tagen")}
      ${section("Laufend", running, "nach Betrag")}
      ${section("Gekündigt", cancelled)}
    </div><div>
      ${section("Regelmäßige Einnahmen", income)}
      ${section("Nicht mehr abgebucht", ended)}
      ${ignored.length ? html`<section class="section"><details><summary class="link-btn">${ignored.length} ausgeblendete Zahlungen</summary><ul class="list">${ignored.map(row)}</ul></details></section>` : ""}
    </div></div>`.s;
  on(view, "[data-contract]", "click", (_e, el) => contractSheet(items.find((c) => c.key === el.dataset.contract)));
  on(view, "[data-pending-contract]", "click", (_e, el) => contractSheet(items.find((c) => c.key === el.dataset.pendingContract)));
  $("#c-add").onclick = () => manualContractSheet(data.intervals);
}

function contractSheet(c) {
  const intervalFact = c.interval + (c.interval !== "monatlich" ? `, ≈ ${money(c.monthly_cents)} im Monat` : "");
  const priceBox = c.price_change_cents && c.kind === "expense" && c.price_change_cents < 0 ? html`
      <div class="alert warning" style="cursor:default">${raw(ICON.warn)}<div><strong>Preis gestiegen</strong>
      <span>Vorher ${money(-c.prev_amount_cents)}, jetzt ${money(-c.amount_cents)}. Oft gibt es bei Preiserhöhungen ein Sonderkündigungsrecht.</span>
      <div class="actions" style="margin-top:8px"><button class="btn small" id="c-letter2">Sonderkündigung schreiben</button><button class="btn small" id="c-ack">Zur Kenntnis genommen</button></div></div></div>` : "";
  const sh = openSheet(html`
    ${sheetHead(c.name)}
    <div class="big-amount ${c.kind === "income" ? "pos" : ""}">${money(c.amount_cents, { plus: true })}</div>
    ${priceBox}
    <dl class="facts">
      <dt>Rhythmus</dt><dd>${intervalFact}</dd>
      <dt>Nächste Zahlung</dt><dd>${c.active ? dFull(c.next_due) : "keine erwartet"}</dd>
      <dt>Zuletzt</dt><dd>${dFull(c.last_date)}${c.count ? `, ${c.count} Zahlungen seit ${dShort(c.first_date)}` : ""}</dd>
      ${c.account_name ? html`<dt>Konto</dt><dd>${c.account_name}</dd>` : ""}
      ${c.deadline ? html`<dt>Kündigen bis</dt><dd>${dFull(c.deadline)}${c.days_to_deadline >= 0 ? ` (noch ${c.days_to_deadline} Tage)` : ", Frist vorbei"}</dd>` : ""}
    </dl>
    <div class="actions" style="margin-top:4px">
      ${c.count ? html`<a class="btn small" href="#/umsaetze?contract=${encodeURIComponent(c.key)}" id="c-tx">Buchungen ansehen</a>` : ""}
      ${c.kind === "expense" && c.status !== "cancelled" ? html`<button class="btn small" id="c-letter">Kündigung schreiben</button>` : ""}
      ${c.status === "detected" ? html`<button class="btn small" id="c-confirm">Ist ein Vertrag</button>` : ""}
      <button class="btn small" id="c-hide">${c.manual ? "Löschen" : c.status === "ignored" ? "Wieder einblenden" : "Kein Vertrag, ausblenden"}</button>
    </div>
    <details style="margin-top:18px" ${c.customer_no || c.contract_end || c.status === "cancelled" ? raw("open") : ""}><summary class="link-btn">Vertragsdaten und Kündigung</summary>
      <label class="field"><span>Name</span><input class="input" id="c-name" value="${c.name}"></label>
      <div class="field-row">
        <label class="field"><span>Kunden- oder Vertragsnummer</span><input class="input" id="c-cno" value="${c.customer_no || ""}"></label>
        <label class="field"><span>Kündigungsfrist in Monaten</span><input class="input" id="c-notice" inputmode="numeric" value="${c.notice_months ?? ""}"></label>
      </div>
      <div class="field-row">
        <label class="field"><span>Vertragsende oder Verlängerung am</span><input class="input" type="date" id="c-end" value="${c.contract_end || ""}"></label>
        <label class="field"><span>E-Mail des Anbieters</span><input class="input" type="email" id="c-mail" value="${c.provider_email || ""}"></label>
      </div>
      <label class="field"><span>Anschrift des Anbieters</span><textarea id="c-addr" rows="3">${c.provider_address || ""}</textarea></label>
      <label class="check"><input type="checkbox" id="c-cancelled" ${c.status === "cancelled" ? raw("checked") : ""}><span>Gekündigt</span></label>
      <label class="field" id="c-eff-wrap" ${c.status === "cancelled" ? "" : raw("hidden")}><span>Letzte Zahlung bis einschließlich</span><input class="input" type="date" id="c-eff" value="${c.cancel_effective || ""}"></label>
      <label class="field"><span>Notizen</span><textarea id="c-notes" rows="2">${c.notes || ""}</textarea></label>
      <div class="actions"><button class="btn primary" id="c-save">Speichern</button><button class="btn" id="c-research">Anbieter recherchieren</button></div>
      <div id="c-research-results" class="note" aria-live="polite"></div>
      <section class="section" style="margin-top:14px">
        <strong>Kündigungshistorie</strong>
        <div id="c-cancellation-history" class="note" aria-live="polite">Lade Verlauf …</div>
      </section>
    </details>`.s);
  const history = $("#c-cancellation-history", sh.el);
  api(`contracts/${encodeURIComponent(c.key)}/cancellation-events`).then((result) => {
    const items = result.items || [];
    const mode = { ordinary: "Fristgerechte Kündigung", extraordinary: "Sonderkündigung", withdrawal: "Widerruf" };
    const status = { prepared: "Vorbereitet", handed_off: "An Mail-App übergeben", sent: "Von dir als versendet bestätigt", provider_confirmed: "Eingangsbestätigung vom Anbieter erhalten", aborted: "Abgebrochen" };
    const when = (value) => value ? new Date(value).toLocaleString("de-DE") : "";
    history.innerHTML = items.length ? items.map((event) => {
      let row = "<p><strong>" + (mode[event.mode] || "Kündigung") + "</strong><br>" + (status[event.status] || event.status);
      row += "<br><small>Erstellt: " + when(event.prepared_at);
      if (event.handed_off_at) row += "<br>Übergeben: " + when(event.handed_off_at);
      if (event.user_confirmed_sent_at) row += "<br>Versand bestätigt: " + when(event.user_confirmed_sent_at);
      if (event.provider_confirmed_at) row += "<br>Anbieterbestätigung: " + when(event.provider_confirmed_at);
      if (event.aborted_at) row += "<br>Abgebrochen: " + when(event.aborted_at);
      row += "</small>";
      if (["prepared", "handed_off"].includes(event.status)) row += '<br><button class="btn small" data-abort-cancellation="' + event.id + '">Vorgang abbrechen</button>';
      if (event.status === "sent") row += '<br><button class="btn small" data-confirm-received="' + event.id + '">Bestätigung vom Anbieter erhalten</button>';
      return row + "</p>";
    }).join("") : "Bisher keine Kündigungsvorgänge dokumentiert.";
  }).catch((error) => { history.textContent = "Verlauf konnte nicht geladen werden: " + error.message; });
  on(history, "[data-abort-cancellation]", "click", async (_event, button) => {
    if (!window.confirm("Diesen Vorgang in Kassensturz abbrechen? Eine bereits geöffnete Mail-App wird dadurch nicht geschlossen oder verändert. Der Vertragsstatus bleibt unverändert.")) return;
    button.disabled = true;
    try {
      await api("contracts/" + encodeURIComponent(c.key) + "/cancellation-events/" + button.dataset.abortCancellation + "/abort", { method: "POST", body: { user_confirmed_aborted: true } });
      toast("Kündigungsvorgang abgebrochen");
      sh.close();
      rerender();
    } catch (error) { toast(error.message); button.disabled = false; }
  });
  on(history, "[data-confirm-received]", "click", async (_event, button) => {
    button.disabled = true;
    try {
      await api(`contracts/${encodeURIComponent(c.key)}/cancellation-events/${button.dataset.confirmReceived}/confirm-received`, { method: "POST", body: { user_confirmed_received: true } });
      toast("Anbieterbestätigung dokumentiert");
      sh.close();
      contractSheet(c);
    } catch (error) { toast(error.message); button.disabled = false; }
  });
  const patch = async (body, msg) => { await api(`contracts/${encodeURIComponent(c.key)}`, { method: body === null ? "DELETE" : "PATCH", body: body || undefined }); sh.close(); toast(msg); rerender(); };
  $("#c-cancelled", sh.el).onchange = (e) => { $("#c-eff-wrap", sh.el).hidden = !e.target.checked; };
  $("#c-save", sh.el).onclick = () => patch({
    name: $("#c-name", sh.el).value.trim() || c.name, customer_no: $("#c-cno", sh.el).value.trim(), notice_months: $("#c-notice", sh.el).value.trim() ? Number($("#c-notice", sh.el).value) : "",
    contract_end: $("#c-end", sh.el).value, provider_email: $("#c-mail", sh.el).value.trim(), provider_address: $("#c-addr", sh.el).value.trim(),
    notes: $("#c-notes", sh.el).value.trim(), status: $("#c-cancelled", sh.el).checked ? "cancelled" : (c.status === "cancelled" ? "confirmed" : c.status),
    cancel_effective: $("#c-cancelled", sh.el).checked ? $("#c-eff", sh.el).value : "",
  }, "Vertrag gespeichert");
  if ($("#c-confirm", sh.el)) $("#c-confirm", sh.el).onclick = () => patch({ status: "confirmed" }, "Als Vertrag bestätigt");
  $("#c-hide", sh.el).onclick = () => (c.manual ? patch(null, "Vertrag gelöscht") : patch({ status: c.status === "ignored" ? "detected" : "ignored" }, c.status === "ignored" ? "Wieder eingeblendet" : "Ausgeblendet"));
  if ($("#c-ack", sh.el)) $("#c-ack", sh.el).onclick = () => patch({ price_change_ack: true }, "Preisänderung bestätigt");
  if ($("#c-letter", sh.el)) $("#c-letter", sh.el).onclick = () => { sh.close(); letterSheet(c, "ordentlich"); };
  if ($("#c-letter2", sh.el)) $("#c-letter2", sh.el).onclick = () => { sh.close(); letterSheet(c, "sonder"); };
  if ($("#c-tx", sh.el)) $("#c-tx", sh.el).onclick = () => sh.close();
  $("#c-research", sh.el).onclick = async () => {
    const btn = $("#c-research", sh.el);
    const out = $("#c-research-results", sh.el);
    btn.disabled = true;
    out.textContent = "Suche nach offiziellen Kontakt- und Kündigungsseiten …";
    try {
      const result = await api(`contracts/${encodeURIComponent(c.key)}/cancellation-research`, { method: "POST" });
      const sources = result.results || [];
      out.innerHTML = html`
        <strong>${sources.length ? "Gefundene Suchtreffer – noch nicht verifiziert" : "Keine Suchtreffer gefunden"}</strong>
        ${sources.map((source, index) => html`<p><a href="${source.url}" target="_blank" rel="noopener noreferrer">${source.title}</a><br><small>${source.domain} · ${source.snippet}</small><br><button class="btn small" data-source-check="${index}">Öffentliche DNS prüfen</button> <button class="btn small" data-page-check="${index}">Webseite sicher prüfen</button> <small id="source-check-${index}"></small></p>`)}
        ${sources.length ? html`<button class="btn small" id="c-save-sources">Quellen als ungeprüft speichern</button>` : ""}
        ${sources.length ? html`<div class="field"><span>Kontaktangaben aus geprüfter Quelle übernehmen</span>
          <select class="input" id="c-confirm-source">${sources.map((source, index) => html`<option value="${index}">${source.domain} – ${source.title}</option>`)}</select>
          <input class="input" id="c-confirm-email" type="email" placeholder="Kündigungs-E-Mail (optional)">
          <textarea id="c-confirm-address" rows="2" placeholder="Postanschrift (optional)"></textarea>
          <input class="input" id="c-confirm-url" type="url" placeholder="Direkter Kündigungslink (optional)">
          <label class="check"><input type="checkbox" id="c-user-confirmed"><span>Ich habe diese Angaben selbst auf der ausgewählten Anbieterquelle geprüft.</span></label>
          <button class="btn primary small" id="c-confirm-contact">Geprüfte Kontaktdaten übernehmen</button>
        </div>` : ""}
        <p><small>${result.notice}</small></p>`.s;
      out.querySelectorAll("[data-source-check]").forEach((checkButton) => {
        checkButton.onclick = async () => {
          const index = Number(checkButton.dataset.sourceCheck);
          const status = $(`#source-check-${index}`, out);
          checkButton.disabled = true;
          status.textContent = "Prüfe DNS-Ziel …";
          try {
            const checked = await api(`contracts/${encodeURIComponent(c.key)}/cancellation-source-check`, {
              method: "POST", body: { url: sources[index].url },
            });
            status.textContent = `Öffentliche DNS-Adresse: ${checked.addresses.join(", ")} – Anbieteridentität weiterhin ungeprüft.`;
          } catch (error) {
            status.textContent = error.message;
          } finally {
            checkButton.disabled = false;
          }
        };
      });
      out.querySelectorAll("[data-page-check]").forEach((checkButton) => {
        checkButton.onclick = async () => {
          const index = Number(checkButton.dataset.pageCheck);
          const status = $(`#source-check-${index}`, out);
          checkButton.disabled = true;
          status.textContent = "Rufe die öffentliche Webseite begrenzt und ohne Weiterleitungen ab …";
          try {
            const evidence = await api(`contracts/${encodeURIComponent(c.key)}/cancellation-page-evidence`, {
              method: "POST", body: { url: sources[index].url },
            });
            status.textContent = `Seitentitel: ${evidence.page_title || "nicht vorhanden"} · E-Mail-Hinweise: ${evidence.emails_found.join(", ") || "keine gefunden"} · NICHT VERIFIZIERT`;
          } catch (error) {
            status.textContent = error.message;
          } finally {
            checkButton.disabled = false;
          }
        };
      });
      if ($("#c-confirm-contact", out)) $("#c-confirm-contact", out).onclick = async () => {
        const index = Number($("#c-confirm-source", out).value);
        const source = sources[index];
        const confirmed = $("#c-user-confirmed", out).checked;
        if (!confirmed) { toast("Bitte bestätige zuerst deine eigene Prüfung der Quelle"); return; }
        const email = $("#c-confirm-email", out).value.trim();
        const address = $("#c-confirm-address", out).value.trim();
        const cancellationUrl = $("#c-confirm-url", out).value.trim();
        if (!email && !address && !cancellationUrl) { toast("Bitte mindestens eine Kontaktangabe eintragen"); return; }
        const button = $("#c-confirm-contact", out);
        button.disabled = true;
        try {
          await api(`contracts/${encodeURIComponent(c.key)}/cancellation-contact`, {
            method: "PUT",
            body: {
              email: $("#c-mail", sh.el).value.trim(),
              postal_address: $("#c-addr", sh.el).value.trim(),
              status: "unverified",
              sources: sources.map(item => ({
                title: item.title, url: item.url, source_type: "search_candidate", excerpt: item.snippet,
              })),
            },
          });
          await api(`contracts/${encodeURIComponent(c.key)}/cancellation-contact/confirm`, {
            method: "POST",
            body: { user_confirmed: true, source_url: source.url, email, postal_address: address, cancellation_url: cancellationUrl },
          });
          toast("Kontaktangaben geprüft und gespeichert");
          $("#c-mail", sh.el).value = email || $("#c-mail", sh.el).value;
          $("#c-addr", sh.el).value = address || $("#c-addr", sh.el).value;
        } catch (error) {
          toast(error.message);
        } finally {
          button.disabled = false;
        }
      };
      if ($("#c-save-sources", out)) $("#c-save-sources", out).onclick = async () => {
        await api(`contracts/${encodeURIComponent(c.key)}/cancellation-contact`, {
          method: "PUT",
          body: {
            email: $("#c-mail", sh.el).value.trim(),
            postal_address: $("#c-addr", sh.el).value.trim(),
            status: "unverified",
            sources: sources.map(source => ({
              title: source.title, url: source.url, source_type: "search_candidate", excerpt: source.snippet
            })),
          },
        });
        toast("Quellen gespeichert – Kontaktdaten bleiben ungeprüft");
      };
    } catch (error) {
      out.textContent = error.message;
    } finally {
      btn.disabled = false;
    }
  };
}

async function letterSheet(c, mode) {
  let cancellationEventId = null;
  const sh = openSheet(html`${sheetHead("Kündigung " + c.name)}<div class="progress"><div class="spinner"></div></div>`.s, { wide: true });
  const draw = async () => {
    const date = mode === "termin" ? ($("#l-date", sh.el)?.value || c.contract_end || todayIso()) : null;
    const l = await api("letter", { method: "POST", body: { key: c.key, mode, date } });
    sh.set(html`${sheetHead("Kündigung " + c.name)}
      <div class="segmented" role="group" aria-label="Art der Kündigung" style="margin:6px 0 10px">
        ${[["ordentlich", "Fristgerecht"], ["termin", "Zum Datum"], ["sonder", "Sonderkündigung"]].map(([v, lbl]) => html`<button data-mode="${v}" aria-pressed="${mode === v}">${lbl}</button>`)}
      </div>
      ${mode === "termin" ? html`<label class="field"><span>Kündigen zum</span><input class="input" type="date" id="l-date" value="${date}"></label>` : ""}
      ${!l.profile_complete ? html`<p class="note">Dein Name und deine Anschrift fehlen noch. <a href="#/einstellungen" data-close>In den Einstellungen eintragen</a></p>` : ""}
      ${!c.customer_no || !c.provider_address ? html`<p class="note">Trag Kundennummer und Anschrift des Anbieters in den Vertragsdaten ein, dann stehen sie im Schreiben.</p>` : ""}
      <div class="letter print-area" id="l-text">${l.letter}</div>
      <details open style="margin-top:12px">
        <summary class="link-btn">E-Mail vor dem Öffnen prüfen und bearbeiten</summary>
        <label class="field"><span>Empfänger</span><input class="input" type="email" id="l-email-to" value="${c.provider_email || ""}" placeholder="kuendigung@anbieter.de"></label>
        <label class="field"><span>Betreff</span><input class="input" id="l-email-subject" value="${l.subject}"></label>
        <label class="field"><span>E-Mail-Text</span><textarea id="l-email-body" rows="10">${l.body}</textarea></label>
      </details>
      <p class="small muted">Eine Vorlage, keine Rechtsberatung. Vor dem Öffnen kannst du Empfänger, Betreff und Inhalt bearbeiten. Online abgeschlossene Verträge lassen sich außerdem über den Kündigungsbutton auf der Website des Anbieters beenden (§ 312k BGB).</p>
      <div class="actions">
        <button class="btn primary" id="l-email">E-Mail öffnen</button>
        ${cancellationEventId ? html`<button class="btn primary" id="l-confirm-sent">Ich habe die Kündigung tatsächlich versendet</button>` : ""}
        <button class="btn" id="l-copy">Text kopieren</button>
        <button class="btn" id="l-print">Drucken oder als PDF</button>
        <button class="btn" id="l-close">Schließen</button>
      </div>`.s);
    on(sh.el, "[data-mode]", "click", (_e, el) => { mode = el.dataset.mode; draw(); });
    if ($("#l-date", sh.el)) $("#l-date", sh.el).onchange = draw;
    $("#l-copy", sh.el).onclick = async () => {
      try { await navigator.clipboard.writeText(l.letter); toast("Text kopiert"); }
      catch { const r = document.createRange(); r.selectNodeContents($("#l-text", sh.el)); getSelection().removeAllRanges(); getSelection().addRange(r); toast("Text markiert – jetzt kopieren"); }
    };
    $("#l-print", sh.el).onclick = () => window.print();
    $("#l-close", sh.el).onclick = () => sh.close();
    if ($("#l-email", sh.el)) $("#l-email", sh.el).onclick = async () => {
      const button = $("#l-email", sh.el);
      button.disabled = true;
      try {
        const recipient = $("#l-email-to", sh.el).value.trim();
        const subject = $("#l-email-subject", sh.el).value.trim();
        const body = $("#l-email-body", sh.el).value;
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(recipient)) throw new Error("Bitte eine gültige Empfänger-E-Mail-Adresse eintragen.");
        if (!subject || !body.trim()) throw new Error("Betreff und E-Mail-Text dürfen nicht leer sein.");
        const mailto = "mailto:" + encodeURIComponent(recipient) + "?subject=" + encodeURIComponent(subject) + "&body=" + encodeURIComponent(body);
        const notes = mode === "termin" && date ? "Kündigung zum " + date : null;
        const event = await api(`contracts/${encodeURIComponent(c.key)}/cancellation-events`, {
          method: "POST", body: { mode: mode === "sonder" ? "extraordinary" : "ordinary", notes },
        });
        await api(`contracts/${encodeURIComponent(c.key)}/cancellation-events/${event.id}/handoff`, { method: "POST" });
        cancellationEventId = event.id;
        await draw();
        window.location.href = mailto;
      } catch (error) { toast(error.message); button.disabled = false; }
    };
    if ($("#l-confirm-sent", sh.el)) $("#l-confirm-sent", sh.el).onclick = async () => {
      const button = $("#l-confirm-sent", sh.el);
      button.disabled = true;
      try {
        await api(`contracts/${encodeURIComponent(c.key)}/cancellation-events/${cancellationEventId}/confirm-sent`, {
          method: "POST", body: { user_confirmed_sent: true },
        });
        toast("Versand von dir bestätigt und dokumentiert");
        sh.close();
      } catch (error) { toast(error.message); button.disabled = false; }
    };
  };
  draw();
}

function manualContractSheet(intervals) {
  const sh = openSheet(html`${sheetHead("Vertrag hinzufügen")}
    <p class="small muted">Für Zahlungen, die noch nicht oft genug vorkamen, zum Beispiel eine jährliche Versicherung.</p>
    <label class="field"><span>Name</span><input class="input" id="m-name" autofocus></label>
    <div class="field-row">
      <label class="field"><span>Betrag (Ausgabe negativ)</span><input class="input" id="m-amt" inputmode="decimal" placeholder="-412,38"></label>
      <label class="field"><span>Rhythmus</span><select id="m-int">${intervals.map((i) => html`<option ${i === "jährlich" ? raw("selected") : ""}>${i}</option>`)}</select></label>
    </div>
    <div class="field-row">
      <label class="field"><span>Nächste Zahlung</span><input class="input" type="date" id="m-next" value="${todayIso()}"></label>
      <label class="field"><span>Konto</span><select id="m-acc">${store.accounts.filter((a) => a.in_forecast).map((a) => html`<option value="${a.id}">${a.name}</option>`)}</select></label>
    </div>
    <label class="field"><span>Buchungen erkennen am Suchbegriff (optional)</span><input class="input" id="m-pat" placeholder="z. B. huk-coburg"></label>
    <div class="actions"><button class="btn primary" id="m-save">Hinzufügen</button></div>`.s);
  $("#m-save", sh.el).onclick = async () => {
    try {
      await api("contracts", { method: "POST", body: { name: $("#m-name", sh.el).value, amount_cents: parseMoney($("#m-amt", sh.el).value), interval: $("#m-int", sh.el).value,
        next_due: $("#m-next", sh.el).value, account_id: Number($("#m-acc", sh.el).value) || null, match_pattern: $("#m-pat", sh.el).value } });
      sh.close(); toast("Vertrag hinzugefügt"); rerender();
    } catch (e) { toast(e.message); }
  };
}

/* ------------------------------------------------------------------ Budgets & Auswertung */
function affordHtml(r) {
  const head = { yes: "Ja, das passt.", tight: "Knapp.", no: "Nein, das reißt ein Loch." }[r.verdict];
  const until = r.period_label === "bis Monatsende" ? "bis Monatsende" : `bis zum Gehalt am ${dShort(new Date(new Date(r.period_end).getTime() + 86400000).toISOString().slice(0, 10))}`;
  const lines = [];
  if (r.verdict === "no") lines.push(`Nach den festen Abbuchungen sind nur ${money(r.free_before_cents)} frei. Es fehlen ${money(-r.free_after_cents)}.`);
  else {
    lines.push(`Danach bleiben ${money(r.free_after_cents)} ${until}, das sind ${money(r.per_day_after_cents)} pro Tag statt ${money(r.per_day_before_cents)}.`);
    if (r.per_day_after_cents < r.usual_per_day_cents) lines.push(`Für den Alltag gibst du sonst ${money(r.usual_per_day_cents)} pro Tag aus.`);
  }
  if (r.below_threshold) lines.push(`Die Prognose fällt am ${dShort(r.low_point_after.date)} auf ${money(r.low_point_after.cents)}.`);
  return html`<div class="alert ${r.verdict === "yes" ? "" : r.verdict === "tight" ? "warning" : "critical"}" style="margin-top:10px"><div><strong>${money(r.amount_cents)}: ${head}</strong>
    <p class="small">${lines.join(" ")}</p></div></div>`.s;
}

function reviewHtml(r) {
  if (!r || !r.has_data || !r.complete) return "";
  const lines = [];
  if (r.saved_cents > 0 && r.savings_rate !== null) lines.push(`Gespart ${money(r.saved_cents)}, Sparquote ${Math.round(r.savings_rate * 100)} %.`);
  else if (r.saved_cents < 0) lines.push(`${money(-r.saved_cents)} mehr ausgegeben als eingenommen.`);
  if (r.expense_change_cents !== null && Math.abs(r.expense_change_cents) >= 5000) lines.push(`Ausgaben ${money(Math.abs(r.expense_change_cents))} ${r.expense_change_cents > 0 ? "höher" : "niedriger"} als ${r.compared_months === 1 ? "im Vormonat" : `im Schnitt der letzten ${r.compared_months} Monate`}.`);
  if (r.notable.length) lines.push(`Auffällig: ${r.notable.join(", ")}.`);
  if (r.biggest_expense) lines.push(`Größte Einzelausgabe: ${r.biggest_expense.name}, ${money(-r.biggest_expense.amount_cents)}.`);
  return lines.length ? html`<p class="review">${lines.join(" ")}</p>`.s : "";
}

async function renderBudgets(view, params, seq) {
  const month = params.month || todayIso().slice(0, 7);
  const [data, stats, plan] = await Promise.all([api("budgets?month=" + month), api("stats?month=" + month), api("goals")]);
  if (seq !== renderSeq) return;
  const [y, m] = month.split("-").map(Number);
  const prev = new Date(y, m - 2, 1), next = new Date(y, m, 1);
  const key = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  const isCurrent = month === todayIso().slice(0, 7);
  const st = data.stats;
  const maxCat = Math.max(1, ...st.breakdown.map((b) => b.cents));
  const withBudget = new Set(data.budgets.map((b) => b.category_id));
  view.innerHTML = html`
    <div class="page-head"><h1>${fmtMonth.format(new Date(y, m - 1, 1))}</h1>
      <div class="segmented"><button id="b-prev" aria-label="Vormonat">‹ ${fmtMonth.format(prev).split(" ")[0]}</button>
      ${!isCurrent ? html`<button id="b-next" aria-label="Folgemonat">${fmtMonth.format(next).split(" ")[0]} ›</button>` : ""}</div></div>
    <ul class="tally-lines" style="max-width:420px;font-size:1rem">
      <li><span class="op"></span><span>Einnahmen</span><span class="amount pos">${money(st.income_cents, { plus: true })}</span></li>
      <li><span class="op">−</span><span>Ausgaben</span><span class="amount">${money(st.expense_cents)}</span></li>
      <li class="tally-sum" style="font-weight:650"><span class="op">=</span><span>${st.saldo_cents >= 0 ? "Überschuss" : "Fehlbetrag"}</span><span class="amount">${money(st.saldo_cents)}</span></li>
    </ul>
    ${raw(reviewHtml(stats.review))}
    <div class="cols"><div>
      <section class="section"><div class="section-head"><h2>Budgets</h2><span class="small muted">Strich: so viel wäre bis heute im Plan</span></div>
        ${data.budgets.length ? html`<div>${data.budgets.map(budgetRow)}</div>` : html`<p class="muted">Tipp auf eine Kategorie rechts oder unten, um ein Monatsbudget festzulegen.</p>`}
      </section>
      <section class="section"><div class="section-head"><h2>Sparziele</h2><button class="link-btn" id="g-add">Ziel hinzufügen</button></div>
        ${plan.goals.length ? html`<div>${plan.goals.map((g) => html`<button class="goal" data-goal="${g.id}">
          <span class="goal-head"><strong>${g.name}</strong><span class="num">${money(g.saved_cents)} von ${money(g.target_cents)}</span></span>
          <span class="meter"><i style="width:${Math.round(g.progress * 100)}%"></i></span>
          <span class="small muted">${g.status === "done" ? "Erreicht" : g.status === "late" ? `Ziel war ${dFull(g.due_date)}, es fehlen ${money(g.rest_cents)}`
            : g.monthly_cents ? `${money(g.monthly_cents)} im Monat bis ${dFull(g.due_date)}` : `Es fehlen ${money(g.rest_cents)}`}${g.account_name ? ` · ${g.account_name}` : ""}</span></button>`)}</div>`
          : html`<p class="small muted">Noch keine Ziele. Lege fest, wofür du sparst, etwa einen Notgroschen oder einen Urlaub, und bis wann.</p>`}
      </section>
      <section class="section"><div class="section-head"><h2>Jahreskosten</h2>${plan.reserve.items.length ? html`<span class="small muted">${money(plan.reserve.monthly_cents)} im Monat</span>` : ""}</div>
        ${plan.reserve.items.length ? html`<p class="small muted">Dafür solltest du heute ${money(plan.reserve.reserved_cents)} zurückgelegt haben.${plan.reserve.deducted ? " Der Betrag ist von „frei verfügbar“ abgezogen." : ""}</p>
          <ul class="list">${plan.reserve.items.map((r) => html`<li class="row static"><span class="title">${r.name}</span>
            <span class="sub">${r.interval}, nächste Zahlung ${dFull(r.next_due)}, ${money(r.monthly_cents)} im Monat</span>
            <span class="amount">${money(r.amount_cents)}<small>${money(r.reserved_cents)} bis heute</small></span></li>`)}</ul>`
          : html`<p class="small muted">Keine viertel-, halb- oder jährlichen Verträge erkannt.</p>`}
      </section>
      <section class="section"><div class="section-head"><h2>Überschuss je Monat</h2></div><div class="chart" id="hist-chart"></div></section>
    </div><div>
      <section class="section"><div class="section-head"><h2>Ausgaben nach Kategorie</h2></div>
        ${st.breakdown.length ? html`<ul class="bars">${st.breakdown.map((b) => html`
          <li class="bar-row" data-cat="${b.category_id || ""}" title="${Math.round((b.cents / Math.max(1, st.expense_cents)) * 100)} % der Ausgaben">
            <span class="label">${b.name}${!b.category_id || withBudget.has(b.category_id) ? "" : html` <button class="link-btn tiny" data-setbudget="${b.category_id}">Budget</button>`}</span>
            <span class="val">${money(b.cents)}</span>
            <div class="bar-track"><div class="bar-fill" style="width:${(b.cents / maxCat) * 100}%"></div></div></li>`)}</ul>`
          : html`<p class="muted">Keine Ausgaben in diesem Monat.</p>`}
      </section>
    </div></div>`.s;
  $("#b-prev").onclick = () => go("budgets", { month: key(prev) });
  $("#g-add").onclick = () => goalSheet(null);
  on(view, "[data-goal]", "click", (_e, el) => goalSheet(plan.goals.find((g) => String(g.id) === el.dataset.goal)));
  if ($("#b-next")) $("#b-next").onclick = () => go("budgets", { month: key(next) });
  bindBudgetRows(view);
  on(view, "[data-setbudget]", "click", (e, el) => { e.stopPropagation(); budgetSheet(Number(el.dataset.setbudget)); });
  on(view, ".bar-row[data-cat]", "click", (_e, el) => { if (el.dataset.cat) go("umsaetze", { category: el.dataset.cat, month, kind: "out" }); });
  historyChart($("#hist-chart"), stats.history);
}

function historyChart(el, hist) {
  const W = Math.max(300, el.clientWidth || 500), H = 170, L = 50, R = 6, T = 10, B = 22;
  const vals = hist.map((h) => h.income_cents - h.expense_cents);
  let max = Math.max(0, ...vals), min = Math.min(0, ...vals);
  if (max === min) max = 10000;
  const step = niceStep((max - min) / 3);
  max = Math.ceil(max / step) * step; min = Math.floor(min / step) * step;
  const y = (v) => T + (1 - (v - min) / (max - min)) * (H - T - B);
  const bw = (W - L - R) / hist.length;
  let g = "";
  for (let v = min; v <= max + 1; v += step) g += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${moneyRound(v)}</text>`;
  const bars = hist.map((h, i) => {
    const v = vals[i];
    const x0 = L + i * bw + bw * 0.18, w = bw * 0.64;
    const top = y(Math.max(v, 0)), bot = y(Math.min(v, 0));
    const color = v >= 0 ? "var(--chart-line)" : "var(--neg-chart)";
    const label = fmtMonth.format(D(h.month + "-15"));
    return `<g class="hbar" data-i="${i}"><rect x="${L + i * bw}" y="${T}" width="${bw}" height="${H - T - B}" fill="transparent"/>
      ${v ? `<rect x="${x0}" y="${top}" width="${w}" height="${Math.max(1.5, bot - top)}" rx="3" fill="${color}"/>` : ""}
      <text class="axis" x="${x0 + w / 2}" y="${H - 6}" text-anchor="middle">${esc(label.slice(0, 3))}</text>
      <title>${esc(label)}: Einnahmen ${esc(money(h.income_cents))}, Ausgaben ${esc(money(h.expense_cents))}, Saldo ${esc(money(v))}</title></g>`;
  }).join("");
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="Überschuss oder Fehlbetrag der letzten zwölf Monate">${g}<line class="grid" x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}" style="stroke:var(--muted)"/>${bars}</svg><div class="tooltip"></div>`;
  const tip = $(".tooltip", el);
  $$(".hbar", el).forEach((gEl) => {
    const show = () => {
      const i = Number(gEl.dataset.i), h = hist[i];
      tip.innerHTML = `${esc(fmtMonth.format(D(h.month + "-15")))}: <strong>${esc(money(vals[i]))}</strong>`;
      tip.style.left = `${((L + (i + 0.5) * bw) / W) * 100}%`; tip.style.top = `${(y(Math.max(vals[i], 0)) / H) * el.clientHeight}px`;
      tip.classList.add("show");
    };
    gEl.addEventListener("pointerenter", show); gEl.addEventListener("pointerdown", show);
    gEl.addEventListener("pointerleave", () => tip.classList.remove("show"));
  });
}

function goalSheet(g) {
  const isNew = !g;
  g = g || { name: "", target_cents: null, saved_cents: 0, due_date: "", account_id: null, linked: false };
  const accounts = store.accounts.filter((a) => !a.archived);
  const sh = openSheet(html`${sheetHead(isNew ? "Sparziel anlegen" : g.name)}
    <label class="field"><span>Wofür</span><input class="input" id="g-name" value="${g.name}" placeholder="z. B. Notgroschen" ${isNew ? raw("autofocus") : ""}></label>
    <div class="field-row">
      <label class="field"><span>Zielbetrag</span><input class="input" id="g-target" inputmode="decimal" value="${g.target_cents ? toInput(g.target_cents) : ""}" placeholder="0,00"></label>
      <label class="field"><span>Bis wann (optional)</span><input class="input" type="date" id="g-due" value="${g.due_date || ""}"></label>
    </div>
    <label class="field"><span>Wo liegt das Geld</span><select id="g-acc"><option value="">Kein Konto, ich trage den Stand selbst ein</option>
      ${accounts.map((a) => html`<option value="${a.id}" ${a.id === g.account_id ? raw("selected") : ""}>${a.name}</option>`)}</select></label>
    <label class="field" id="g-saved-field" ${g.linked ? raw("hidden") : ""}><span>Schon gespart</span><input class="input" id="g-saved" inputmode="decimal" value="${toInput(isNew ? 0 : g.linked ? 0 : g.saved_cents)}"></label>
    <p class="small muted">Mit Konto zählt dessen Stand als gespart. Hängen mehrere Ziele am selben Konto, wird er der Reihe nach verteilt.</p>
    <div class="actions"><button class="btn primary" id="g-save">${isNew ? "Anlegen" : "Speichern"}</button>
      ${!isNew ? html`<button class="btn danger" id="g-del">Ziel löschen</button>` : ""}</div>`.s);
  $("#g-acc", sh.el).onchange = (e) => { $("#g-saved-field", sh.el).hidden = !!e.target.value; };
  $("#g-save", sh.el).onclick = async () => {
    const target = parseMoney($("#g-target", sh.el).value);
    const account = $("#g-acc", sh.el).value;
    const body = { name: $("#g-name", sh.el).value.trim(), target_cents: target === null ? 0 : Math.abs(target), due_date: $("#g-due", sh.el).value,
      account_id: account ? Number(account) : null, saved_cents: Math.abs(parseMoney($("#g-saved", sh.el).value) || 0) };
    try {
      if (isNew) await api("goals", { method: "POST", body }); else await api(`goals/${g.id}`, { method: "PATCH", body });
      sh.close(); toast("Sparziel gespeichert"); rerender();
    } catch (e) { toast(e.message); }
  };
  if ($("#g-del", sh.el)) confirmButton($("#g-del", sh.el), "Wirklich löschen?", async () => {
    await api(`goals/${g.id}`, { method: "DELETE" }); sh.close(); toast("Sparziel gelöscht"); rerender();
  });
}

function budgetSheet(catId) {
  const c = store.catById.get(catId);
  if (!c) return;
  const sh = openSheet(html`${sheetHead("Budget " + c.name)}
    <p class="small muted">Monatliche Obergrenze für ${c.name}${childCats(c.id).length ? " inklusive aller Unterkategorien" : ""}.</p>
    <label class="field"><span>Betrag pro Monat</span><input class="input" id="bu-amt" inputmode="decimal" value="${toInput(c.budget_cents)}" placeholder="z. B. 400" autofocus></label>
    <div class="actions"><button class="btn primary" id="bu-save">Speichern</button>${c.budget_cents ? html`<button class="btn" id="bu-del">Budget entfernen</button>` : ""}
      <a class="btn" href="#/umsaetze?category=${c.id}&month=${todayIso().slice(0, 7)}" data-close>Buchungen ansehen</a></div>`.s);
  const save = async (cents) => { await api(`categories/${c.id}`, { method: "PATCH", body: { budget_cents: cents } }); sh.close(); toast(cents ? "Budget gespeichert" : "Budget entfernt"); rerender(); };
  $("#bu-save", sh.el).onclick = () => save(Math.abs(parseMoney($("#bu-amt", sh.el).value) || 0) || null);
  $("#bu-amt", sh.el).addEventListener("keydown", (e) => { if (e.key === "Enter") $("#bu-save", sh.el).click(); });
  if ($("#bu-del", sh.el)) $("#bu-del", sh.el).onclick = () => save(null);
}

/* ------------------------------------------------------------------ Konten & Bankzugänge */
async function renderAccounts(view, _params, seq) {
  const [conns, settings, eb, box, networth] = await Promise.all([api("connections"), api("settings"), api("eb"), api("inbox"), api("networth")]);
  if (seq !== renderSeq) return;
  const accounts = store.accounts;
  const source = (a) => {
    if (VALUE_KINDS.has(a.kind)) {
      const label = KIND_LABEL[a.kind] || a.kind;
      const due = MATURING_KINDS.has(a.kind) && a.matures_on ? `, ${a.kind === "kredit" ? "läuft bis" : "fällig am"} ${dFull(a.matures_on)}` : "";
      if (!a.balance_known) return `${label}, ${a.kind === "kredit" ? "Restschuld" : "Wert"} noch nicht eingetragen${due}`;
      const change = a.value_prev_cents !== null ? a.balance_now - a.value_prev_cents : null;
      return label + (change !== null ? `, ${money(change, { plus: true })} seit ${dShort(a.value_prev_date)}` : "") + due;
    }
    const range = a.last_date ? `Umsätze bis ${dShort(a.last_date)}` : "noch keine Umsätze";
    const sess = eb.sessions.find((s) => s.id === a.eb_session_id);
    if (sess) return `${sess.aspsp_name} per Open Banking, ${range}`;
    const conn = conns.find((c) => c.id === a.connection_id);
    return conn ? `${conn.name} per FinTS, ${range}` : `Datei-Import, ${range}`;
  };
  const ebRow = (s) => {
    const expired = s.status === "expired";
    const soon = !expired && s.days_left !== null && s.days_left <= 14;
    const chip = expired ? html` <span class="chip crit">abgelaufen</span>` : soon ? html` <span class="chip warn">noch ${Math.max(0, s.days_left)} Tage</span>` : "";
    const last = s.last_sync ? `, zuletzt ${dShort(s.last_sync.slice(0, 10))} ${s.last_sync.slice(11, 16)}` : "";
    return html`<li class="row static" style="grid-template-columns:1fr auto">
      <span class="title">${s.aspsp_name}${chip}</span>
      <span class="sub">${s.accounts.map((a) => a.name).join(", ") || "keine Konten"}. Freigabe bis ${s.valid_until ? dFull(s.valid_until.slice(0, 10)) : "–"}${last}${s.last_status && s.last_status !== "ok" && !expired ? html`<br><span style="color:var(--crit)">${s.last_status}</span>` : ""}</span>
      <span style="grid-row:1/span 2;grid-column:2;display:flex;gap:6px">
        ${expired || soon ? html`<button class="btn small primary" data-eb-renew="${s.id}">Erneuern</button>` : html`<button class="btn small primary" data-eb-sync="${s.id}">${raw(ICON.sync)}Abrufen</button>`}
        <button class="btn small" data-eb-edit="${s.id}" aria-label="Verbindung ${s.aspsp_name} bearbeiten">Mehr</button></span></li>`;
  };
  // Vermögen: alle aktiven Konten mit bekanntem Stand, aufgeteilt in Alltag, Rücklagen und Depots.
  const live = accounts.filter((a) => !a.archived && a.balance_known);
  const sum = (list) => list.reduce((t, a) => t + a.balance_now, 0);
  const groups = Object.keys(GROUP_LABEL).map((g) => [GROUP_LABEL[g], sum(live.filter((a) => a.group === g))]);
  const worth = { count: live.length, total: sum(live), parts: groups.filter(([, c], i) => i === 0 || c) };
  const points = (networth.history || []).map((h) => h.cents);
  const spark = points.length > 2 ? (() => {
    const lo = Math.min(...points), hi = Math.max(...points), span = hi - lo || 1;
    const xy = points.map((c, i) => `${(i / (points.length - 1) * 300).toFixed(1)},${(44 - (c - lo) / span * 40).toFixed(1)}`).join(" ");
    const first = networth.history[0];
    return html`<svg class="worth-spark" viewBox="0 0 300 48" preserveAspectRatio="none" role="img" aria-label="Verlauf des Vermögens"><polyline points="${xy}" /></svg>
      <p class="small muted">${money(points[points.length - 1] - points[0], { plus: true })} seit ${dFull(first.date)}</p>`;
  })() : "";
  const sambaPath = box.path && box.path.startsWith("/share/") ? "\\\\homeassistant.local\\share\\" + box.path.slice(7).replace(/\//g, "\\") : null;
  view.innerHTML = html`
    <div class="page-head"><h1>Konten</h1>
      <div class="actions" style="margin:0"><button class="btn small" id="a-import">${raw(ICON.file)}Datei importieren</button>
      <button class="btn small" id="a-bank">${raw(ICON.bank)}Bank verbinden</button></div></div>
    <div class="cols"><div>
      <section class="section" style="border-top:0">
        ${worth.count ? html`<div class="worth"><span class="label">Vermögen</span><div class="big-amount">${money(worth.total)}</div>
          <p class="small muted">${worth.parts.map(([l, c]) => `${l} ${money(c)}`).join(" · ")}</p>${spark}</div>` : ""}
        ${accounts.length ? html`<ul class="list">${accounts.map((a) => html`<li><button class="row" data-acc="${a.id}" style="${a.archived ? "opacity:.55" : ""}">
          <span class="title">${a.name}${a.archived ? " (archiviert)" : ""}${!a.in_forecast && !a.archived && !VALUE_KINDS.has(a.kind) ? html` <span class="chip neutral">nicht in Prognose</span>` : ""}${a.drift_cents ? html` <span class="chip warn">passt nicht</span>` : ""}</span>
          <span class="sub">${VALUE_KINDS.has(a.kind) ? source(a) : `${KIND_LABEL[a.kind] || a.kind}, ${source(a)}`}</span>
          <span class="amount">${a.balance_known ? money(a.balance_now) : html`<span class="chip warn">${VALUE_KINDS.has(a.kind) ? "Wert fehlt" : "Stand fehlt"}</span>`}<small>${VALUE_KINDS.has(a.kind) ? (a.balance_known ? `Stand ${dShort(a.balance_date)}` : "") : `${a.tx_count} Buchungen`}</small></span></button></li>`)}</ul>`
          : html`<p class="muted">Noch keine Konten. Verbinde eine Bank oder importiere eine Datei.</p>`}
        <div class="actions"><button class="btn small" id="a-new">Konto ohne Import anlegen</button></div>
      </section>
      <section class="section">
        <div class="section-head"><h2>Eingangsordner</h2>${box.path ? html`<button class="link-btn" id="ib-scan">Jetzt prüfen</button>` : ""}</div>
        ${!box.path ? html`<p class="small muted">Ausgeschaltet. In der Konfiguration der App lässt sich unter „Eingangsordner“ ein Pfad eintragen.</p>`
          : html`<p class="small">Kontoauszug-Dateien, die in <code>${box.path}</code> landen, importiert Kassensturz innerhalb einer Minute${sambaPath ? html` – per Samba unter <code>${sambaPath}</code>` : ""}.
              Das Konto erkennt es an der IBAN oder am Format; beim ersten Mal fragt es nach.</p>
            ${box.files.length ? html`<ul class="list">${box.files.map((f) => html`<li class="row static" style="grid-template-columns:1fr auto">
              <span class="title">${f.filename}</span><span class="sub">${f.format ? f.format + ", " : ""}${f.count ? f.count + " Buchungen. " : ""}${f.message}</span>
              <span style="grid-row:1/span 2;grid-column:2;display:flex;gap:6px">${f.status === "pending" ? html`<button class="btn small primary" data-ib-assign="${f.filename}">Zuordnen</button>` : ""}
              <button class="btn small" data-ib-del="${f.filename}">Löschen</button></span></li>`)}</ul>` : ""}
            ${box.recent.length ? html`<p class="small muted">Zuletzt automatisch: ${box.recent.map((r) => `${r.filename} → ${r.account || "?"} (${r.added} neu)`).join("; ")}.</p>` : ""}`}
      </section>
    </div><div>
      <section class="section" style="border-top:0">
        <div class="section-head"><h2>Open Banking</h2>${eb.configured ? html`<button class="link-btn" id="eb-setup">Zugang ändern</button>` : ""}</div>
        ${eb.configured ? html`
          ${eb.sessions.length ? html`<ul class="list">${eb.sessions.map(ebRow)}</ul>` : html`<p class="small muted">Eingerichtet, aber noch keine Bank verbunden.</p>`}
          <div class="actions"><button class="btn small" id="eb-connect">${raw(ICON.bank)}Bank verbinden</button></div>`
          : html`<p class="small muted">Umsätze automatisch über die offizielle EU-Schnittstelle abrufen – auch bei N26, Revolut und anderen Banken ohne FinTS. Über Enable Banking, für eigene Konten kostenlos.</p>
            <div class="actions"><button class="btn small primary" id="eb-setup">Open Banking einrichten</button></div>`}
      </section>
      <section class="section">
        <div class="section-head"><h2>Bankzugänge per FinTS</h2></div>
        ${!settings.product_id ? html`<p class="note">Für FinTS braucht Kassensturz eine Produkt-ID. Die Registrierung bei der Deutschen Kreditwirtschaft ist kostenlos:
          <a href="https://www.fints.org/de/hersteller/produktregistrierung" target="_blank" rel="noopener">fints.org</a>. Danach die ID in der Konfiguration der App eintragen.</p>` : ""}
        ${conns.length ? html`<ul class="list">${conns.map((c) => html`<li class="row static" style="grid-template-columns:1fr auto">
          <span class="title">${c.name}</span>
          <span class="sub">${c.last_sync ? `Zuletzt ${dFull(c.last_sync.slice(0, 10))} ${c.last_sync.slice(11, 16)}` : "Noch nicht abgerufen"}${c.has_pin ? ", täglich automatisch" : ""}${c.last_status && c.last_status !== "ok" ? html`<br><span style="color:var(--crit)">${c.last_status}</span>` : ""}</span>
          <span style="grid-row:1/span 2;grid-column:2;display:flex;gap:6px"><button class="btn small primary" data-sync="${c.id}">${raw(ICON.sync)}Abrufen</button>
          <button class="btn small" data-conn="${c.id}" aria-label="Bankzugang ${c.name} bearbeiten">Bearbeiten</button></span></li>`)}</ul>`
          : html`<p class="muted small">Noch kein FinTS-Zugang. Sparkassen, Volksbanken, ING, DKB, comdirect und viele andere unterstützen FinTS, Neobanken und PayPal nicht.</p>
            <div class="actions"><button class="btn small" id="fints-add">FinTS-Zugang hinzufügen</button></div>`}
      </section>
    </div></div>`.s;
  $("#a-import").onclick = () => pickImportFile();
  $("#a-bank").onclick = () => bankChooser(eb);
  $("#a-new").onclick = () => accountSheet(null);
  if ($("#fints-add")) $("#fints-add").onclick = () => connectionSheet(null);
  if ($("#eb-setup")) $("#eb-setup").onclick = () => ebSetupSheet();
  if ($("#eb-connect")) $("#eb-connect").onclick = () => ebConnectSheet(null);
  if ($("#ib-scan")) $("#ib-scan").onclick = async () => {
    const r = await api("inbox/scan", { method: "POST" });
    toast(r.imported.length ? `${r.imported.length} ${r.imported.length === 1 ? "Datei" : "Dateien"} importiert` : r.pending ? "Nichts Neues – Dateien warten auf Zuordnung" : "Keine neuen Dateien");
    rerender();
  };
  on(view, "[data-acc]", "click", (_e, el) => accountSheet(accounts.find((a) => a.id === Number(el.dataset.acc))));
  on(view, "[data-conn]", "click", (_e, el) => connectionSheet(conns.find((c) => c.id === Number(el.dataset.conn))));
  on(view, "[data-sync]", "click", (_e, el) => syncSheet(conns.find((c) => c.id === Number(el.dataset.sync))));
  on(view, "[data-eb-sync]", "click", (_e, el) => ebSyncSheet(eb.sessions.find((s) => s.id === Number(el.dataset.ebSync))));
  on(view, "[data-eb-renew]", "click", (_e, el) => ebConnectSheet(eb.sessions.find((s) => s.id === Number(el.dataset.ebRenew))));
  on(view, "[data-eb-edit]", "click", (_e, el) => ebEditSheet(eb.sessions.find((s) => s.id === Number(el.dataset.ebEdit))));
  on(view, "[data-ib-assign]", "click", async (_e, el) => {
    try { importSheet(await api("inbox/analyze", { method: "POST", body: { filename: el.dataset.ibAssign } })); } catch (e) { toast(e.message); }
  });
  on(view, "[data-ib-del]", "click", (_e, el) => {
    if (el.dataset.armed) { api(`inbox/${encodeURIComponent(el.dataset.ibDel)}`, { method: "DELETE" }).then(() => { toast("Datei gelöscht"); rerender(); }); return; }
    el.dataset.armed = "1"; el.textContent = "Wirklich löschen?";
  });
}

function bankChooser(eb) {
  const sh = openSheet(html`${sheetHead("Bank verbinden")}
    <div class="start-options" style="margin-top:8px">
      <button class="start-option" id="bc-eb">${raw(ICON.bank)}<div><strong>Open Banking</strong>
        <span>Offizielle EU-Schnittstelle über Enable Banking. Funktioniert auch mit N26, Revolut und anderen Banken ohne FinTS. Freigabe in der Banking-App, alle 90 bis 180 Tage erneuern.</span></div></button>
      <button class="start-option" id="bc-fints">${raw(ICON.sync)}<div><strong>FinTS</strong>
        <span>Direkt zur Bank, ohne Zwischendienst. Für Sparkassen, Volksbanken, ING, DKB, comdirect. Braucht eine kostenlose Produkt-ID.</span></div></button>
    </div>`.s);
  $("#bc-eb", sh.el).onclick = () => { sh.close(); eb.configured ? ebConnectSheet(null) : ebSetupSheet(); };
  $("#bc-fints", sh.el).onclick = () => { sh.close(); connectionSheet(null); };
}

async function ebSetupSheet() {
  const eb = await api("eb");
  let pem = null;
  const sh = openSheet(html`${sheetHead("Open Banking einrichten")}
    <p class="small muted">Kassensturz nutzt dafür Enable Banking, einen lizenzierten Kontoinformationsdienst. Für eigene Konten ist das kostenlos. Einmalig bei Enable Banking:</p>
    <ol class="steps">
      <li>Auf <a href="https://enablebanking.com/sign-in/" target="_blank" rel="noopener">enablebanking.com</a> registrieren und im Control Panel unter „API applications“ eine neue App anlegen:
        Umgebung <strong>Production</strong>, Redirect-URL <code>${eb.redirect_url}</code>, Schlüssel im Browser erzeugen lassen. Der Browser lädt dabei eine .pem-Datei herunter.</li>
      <li>Bei der neuen App „Activate by linking accounts“ wählen und deine Konten einmal verknüpfen.</li>
      <li>App-ID und .pem-Datei hier eintragen.</li>
    </ol>
    <label class="field"><span>App-ID</span><input class="input" id="eb-app" value="${eb.app_id}" placeholder="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" autocomplete="off" spellcheck="false"></label>
    <label class="field"><span>Privater Schlüssel (.pem-Datei)</span><input type="file" id="eb-pem" accept=".pem,.key,.txt"></label>
    ${eb.has_key ? html`<p class="small muted" style="margin-top:-6px">Ein Schlüssel ist gespeichert. Nur auswählen, wenn du ihn ersetzen willst.</p>` : ""}
    <details><summary class="link-btn">Redirect-URL ändern</summary>
      <label class="field"><span>Muss genau so in der App bei Enable Banking stehen</span><input class="input" id="eb-redir" value="${eb.redirect_url}"></label></details>
    <p class="small muted">Der Schlüssel bleibt auf dem Home-Assistant-Gerät und ist von Backups ausgenommen. Nach einer Wiederherstellung lädst du ihn einfach neu hoch.</p>
    <div class="actions"><button class="btn primary" id="eb-save">Speichern und prüfen</button>${eb.configured ? html`<button class="btn danger" id="eb-del">Zugang entfernen</button>` : ""}</div>`.s);
  $("#eb-pem", sh.el).onchange = async (e) => { const f = e.target.files[0]; pem = f ? await f.text() : null; };
  $("#eb-save", sh.el).onclick = async () => {
    const btn = $("#eb-save", sh.el);
    btn.disabled = true;
    try {
      await api("eb/config", { method: "PUT", body: { app_id: $("#eb-app", sh.el).value, private_key: pem, redirect_url: $("#eb-redir", sh.el).value } });
      sh.close(); toast("Open Banking ist eingerichtet"); rerender(); ebConnectSheet(null);
    } catch (e) { toast(e.message); btn.disabled = false; }
  };
  if ($("#eb-del", sh.el)) confirmButton($("#eb-del", sh.el), "Wirklich entfernen?", async () => { await api("eb/config", { method: "DELETE" }); sh.close(); rerender(); });
}

const EB_COUNTRIES = [["DE", "Deutschland"], ["AT", "Österreich"], ["LU", "Luxemburg"], ["NL", "Niederlande"], ["BE", "Belgien"], ["FR", "Frankreich"],
  ["LT", "Litauen"], ["SE", "Schweden"], ["FI", "Finnland"], ["IE", "Irland"], ["ES", "Spanien"], ["IT", "Italien"]];

function ebConnectSheet(renew) {
  const sh = openSheet("", { wide: true });
  let country = renew ? renew.aspsp_country : "DE";
  const busy = (title, text) => sh.set(html`${sheetHead(title)}<div class="progress"><div class="spinner"></div><span>${text}</span></div>`.s);
  const fail = (title, msg, retry) => {
    sh.set(html`${sheetHead(title)}<p>${msg}</p><div class="actions">${retry ? html`<button class="btn primary" id="eb-retry">Erneut versuchen</button>` : ""}<button class="btn" data-close>Schließen</button></div>`.s);
    if (retry) $("#eb-retry", sh.el).onclick = retry;
  };
  const pick = async () => {
    busy("Bank verbinden", "Lade Banken …");
    let banks;
    try { banks = await api("eb/aspsps?country=" + country); } catch (e) { fail("Bank verbinden", e.message, pick); return; }
    sh.set(html`${sheetHead("Bank verbinden")}
      <div class="filters"><select id="eb-country" aria-label="Land">${EB_COUNTRIES.map(([c, l]) => html`<option value="${c}" ${c === country ? raw("selected") : ""}>${l}</option>`)}</select>
        <label class="search">${raw(ICON.search)}<input id="eb-q" placeholder="Bank suchen" aria-label="Bank suchen" autofocus></label></div>
      <div class="cat-list" id="eb-banks" style="max-height:55vh">${banks.length ? banks.map((b) => html`<button data-bank="${b.name}">${b.name}${b.beta ? html` <span class="chip neutral">Beta</span>` : ""}</button>`) : html`<p class="muted small" style="padding:10px">Keine Banken für dieses Land.</p>`}</div>
      <p class="small muted">Nicht dabei? Manche Banken laufen unter dem Land, in dem sie ihren Sitz haben – PayPal und Advanzia etwa unter Luxemburg. Sonst bleibt der Eingangsordner.</p>`.s);
    $("#eb-country", sh.el).onchange = (e) => { country = e.target.value; pick(); };
    $("#eb-q", sh.el).addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase();
      $$("#eb-banks [data-bank]", sh.el).forEach((b) => { b.hidden = q && !b.textContent.toLowerCase().includes(q); });
    });
    on(sh.el, "[data-bank]", "click", (_e, el) => auth(el.dataset.bank));
  };
  const auth = async (name) => {
    busy(name, "Freigabe wird vorbereitet …");
    let a;
    try { a = await api("eb/auth", { method: "POST", body: { aspsp: name, country, renew_id: renew ? renew.id : null } }); }
    catch (e) { fail(name, e.message, () => auth(name)); return; }
    sh.set(html`${sheetHead(name + " freigeben")}
      <ol class="steps">
        <li>Bei der Bank anmelden und den Zugriff bestätigen.<div class="actions" style="margin-top:8px"><a class="btn primary" href="${a.url}" target="_blank" rel="noopener">Zur Bank</a></div></li>
        <li>Danach landest du auf der Seite von Enable Banking. Kopiere die komplette Adresse aus der Adresszeile des Browsers.</li>
        <li>Füge sie hier ein:
          <input class="input" id="eb-ret" placeholder="https://enablebanking.com/?code=…" style="width:100%;margin-top:6px" autocomplete="off" spellcheck="false">
          ${navigator.clipboard && navigator.clipboard.readText ? html`<button class="link-btn small" id="eb-paste" style="margin-top:6px">Aus der Zwischenablage einfügen</button>` : ""}</li>
      </ol>
      <p class="small muted">Die Freigabe gilt ${a.days} Tage. Rechtzeitig vorher erinnert Kassensturz dich ans Erneuern.</p>
      <div class="actions"><button class="btn primary" id="eb-done">Verbinden</button><button class="btn" data-close>Abbrechen</button></div>`.s);
    if ($("#eb-paste", sh.el)) $("#eb-paste", sh.el).onclick = async () => { try { $("#eb-ret", sh.el).value = await navigator.clipboard.readText(); } catch { toast("Zwischenablage nicht lesbar – bitte von Hand einfügen"); } };
    $("#eb-done", sh.el).onclick = () => complete(name, $("#eb-ret", sh.el).value);
  };
  const complete = async (name, text) => {
    busy(name, "Konten werden verknüpft …");
    let r;
    try { r = await api("eb/complete", { method: "POST", body: { text } }); }
    catch (e) { fail(name, e.message, () => auth(name)); return; }
    const intro = html`<p>${r.accounts.length ? `Verknüpft: ${r.accounts.map((a) => a.name + (a.new ? " (neu)" : "")).join(", ")}.` : "Die Bank hat keine Konten freigegeben."}</p>`;
    pollJob(sh, r.job, name, intro);
  };
  if (renew) auth(renew.aspsp_name); else pick();
}

function pollJob(sh, job, title, intro = "") {
  const step = async () => {
    if (!document.body.contains(sh.el)) return;
    try { job = await api(`jobs/${job.id}`); } catch (e) { sh.set(html`${sheetHead(title)}${intro}<p>${e.message}</p>`.s); return; }
    if (job.state === "running" || job.state === "waiting") {
      sh.set(html`${sheetHead(title)}${intro}<div class="progress"><div class="spinner"></div><span>${job.step}</span></div>`.s);
      setTimeout(step, 1000);
    } else if (job.state === "done") {
      const r = job.result || { accounts: [], added: 0 };
      sh.set(html`${sheetHead("Abruf fertig")}${intro}<p>${r.added ? `${r.added} neue Buchungen` : "Keine neuen Buchungen"}.</p>
        <ul class="list">${r.accounts.map((a) => html`<li class="row static"><span class="title">${a.name}</span><span class="amount">${a.added} neu</span></li>`)}</ul>
        <div class="actions"><button class="btn primary" data-close>Fertig</button></div>`.s);
      rerender();
    } else {
      sh.set(html`${sheetHead("Abruf fehlgeschlagen")}${intro}<p>${job.error || "Abgebrochen."}</p><div class="actions"><button class="btn" data-close>Schließen</button></div>`.s);
      rerender();
    }
  };
  step();
}

async function ebSyncSheet(s) {
  const sh = openSheet(html`${sheetHead(s.aspsp_name)}<div class="progress"><div class="spinner"></div><span>Verbinde …</span></div>`.s);
  try { pollJob(sh, await api(`eb/sessions/${s.id}/sync`, { method: "POST" }), s.aspsp_name); }
  catch (e) { sh.set(html`${sheetHead(s.aspsp_name)}<p>${e.message}</p><div class="actions"><button class="btn" data-close>Schließen</button></div>`.s); }
}

function ebEditSheet(s) {
  const sh = openSheet(html`${sheetHead(s.aspsp_name)}
    <dl class="facts">
      <dt>Konten</dt><dd>${s.accounts.map((a) => a.name).join(", ") || "keine"}</dd>
      <dt>Freigabe bis</dt><dd>${s.valid_until ? dFull(s.valid_until.slice(0, 10)) : "–"}${s.status === "expired" ? ", abgelaufen" : ""}</dd>
      <dt>Zuletzt abgerufen</dt><dd>${s.last_sync ? `${dFull(s.last_sync.slice(0, 10))} ${s.last_sync.slice(11, 16)}` : "noch nie"}</dd>
    </dl>
    <p class="small muted">Kassensturz ruft täglich zur eingestellten Uhrzeit automatisch ab. Banken erlauben ohne dich nur wenige Abrufe pro Tag.</p>
    <div class="actions"><button class="btn primary" id="ebe-sync">Jetzt abrufen</button><button class="btn" id="ebe-renew">Freigabe erneuern</button>
      <button class="btn danger" id="ebe-del">Verbindung trennen</button></div>`.s);
  $("#ebe-sync", sh.el).onclick = () => { sh.close(); ebSyncSheet(s); };
  $("#ebe-renew", sh.el).onclick = () => { sh.close(); ebConnectSheet(s); };
  confirmButton($("#ebe-del", sh.el), "Trennen? Konten und Buchungen bleiben", async () => {
    await api(`eb/sessions/${s.id}`, { method: "DELETE" }); sh.close(); toast("Verbindung getrennt"); rerender();
  });
}

function accountSheet(a) {
  const isNew = !a;
  a = a || { name: "", kind: "giro", iban: "", settlement_pattern: "", in_forecast: 1, archived: 0 };
  const sh = openSheet(html`${sheetHead(isNew ? "Konto anlegen" : a.name)}
    ${!isNew ? html`<div class="big-amount">${a.balance_known ? money(a.balance_now) : "Kontostand fehlt"}</div>
      <div class="actions" style="margin-top:0"><button class="btn small" id="ac-bal">${a.kind === "kredit" ? "Restschuld eintragen" : VALUE_KINDS.has(a.kind) ? "Wert eintragen" : "Kontostand eintragen"}</button>
      <a class="btn small" href="#/umsaetze?account=${a.id}" data-close>Buchungen ansehen</a></div>
      ${a.drift_cents ? html`<div class="alert warning" style="margin:10px 0"><div><strong>Kontostand passt nicht zu den Buchungen</strong>
        <p class="small">Die Bank zeigt seit ${dShort(a.drift_since)} ${money(Math.abs(a.drift_cents))} ${a.drift_cents > 0 ? "mehr" : "weniger"}, als die abgerufenen Buchungen erklären. Vermutlich fehlt eine Buchung oder ist doppelt. Der angezeigte Kontostand stammt von der Bank und stimmt; betroffen sind Auswertung und Budgets.</p>
        <button class="btn small" id="ac-drift">Geprüft, Hinweis ausblenden</button></div></div>` : ""}` : ""}
    <label class="field"><span>Name</span><input class="input" id="ac-name" value="${a.name}" ${isNew ? raw("autofocus") : ""}></label>
    <div class="field-row">
      <label class="field"><span>Art</span><select id="ac-kind">${Object.entries(KIND_LABEL).map(([k, l]) => html`<option value="${k}" ${k === a.kind ? raw("selected") : ""}>${l}</option>`)}</select></label>
      <label class="field"><span>IBAN</span><input class="input" id="ac-iban" value="${a.iban || ""}" autocomplete="off"></label>
    </div>
    <label class="field"><span>Abbuchungen auf anderen Konten, die dieses Konto ausgleichen</span>
      <input class="input" id="ac-settle" value="${a.settlement_pattern || ""}" placeholder="z. B. paypal oder american express"></label>
    <p class="small muted" style="margin-top:-6px">Solche Abbuchungen gelten als Umbuchung, damit Einkäufe nicht doppelt zählen. Mehrere Begriffe mit Komma trennen.</p>
    <label class="field" id="ac-due-field" ${MATURING_KINDS.has(a.kind) ? "" : raw("hidden")}><span id="ac-due-label">${a.kind === "kredit" ? "Läuft bis" : "Fällig am"}</span>
      <input class="input" type="date" id="ac-due" value="${a.matures_on || ""}"></label>
    <label class="check"><input type="checkbox" id="ac-fc" ${a.in_forecast ? raw("checked") : ""}><span>Zählt zum Kontostand und zur Prognose</span></label>
    ${!isNew ? html`<label class="check"><input type="checkbox" id="ac-arch" ${a.archived ? raw("checked") : ""}><span>Archivieren – Buchungen bleiben erhalten, fließen aber nicht mehr ein</span></label>` : ""}
    <div class="actions"><button class="btn primary" id="ac-save">${isNew ? "Anlegen" : "Speichern"}</button>
      ${!isNew ? html`<button class="btn danger" id="ac-del">Konto löschen</button>` : ""}</div>`.s);
  $("#ac-save", sh.el).onclick = async () => {
    const body = { name: $("#ac-name", sh.el).value.trim(), kind: $("#ac-kind", sh.el).value, iban: $("#ac-iban", sh.el).value.trim(),
      settlement_pattern: $("#ac-settle", sh.el).value.trim(), in_forecast: $("#ac-fc", sh.el).checked ? 1 : 0 };
    body.matures_on = MATURING_KINDS.has(body.kind) ? $("#ac-due", sh.el).value : "";
    if (!isNew) body.archived = $("#ac-arch", sh.el).checked ? 1 : 0;
    try {
      if (isNew) await api("accounts", { method: "POST", body }); else await api(`accounts/${a.id}`, { method: "PATCH", body });
      sh.close(); toast("Konto gespeichert"); rerender();
    } catch (e) { toast(e.message); }
  };
  $("#ac-kind", sh.el).onchange = (e) => {
    const kind = e.target.value;
    if (isNew) $("#ac-fc", sh.el).checked = !SAVINGS_KINDS.has(kind);
    $("#ac-due-field", sh.el).hidden = !MATURING_KINDS.has(kind);
    $("#ac-due-label", sh.el).textContent = kind === "kredit" ? "Läuft bis" : "Fällig am";
  };
  if ($("#ac-bal", sh.el)) $("#ac-bal", sh.el).onclick = () => { sh.close(); balanceSheet(a); };
  if ($("#ac-drift", sh.el)) $("#ac-drift", sh.el).onclick = async () => {
    await api(`accounts/${a.id}/balance-check/reset`, { method: "POST" }); sh.close(); toast("Hinweis ausgeblendet"); rerender();
  };
  if ($("#ac-del", sh.el)) confirmButton($("#ac-del", sh.el), `Wirklich ${a.tx_count} Buchungen löschen?`, async () => {
    await api(`accounts/${a.id}`, { method: "DELETE" }); sh.close(); toast("Konto gelöscht"); rerender();
  });
}

function balanceSheet(a) {
  const value = VALUE_KINDS.has(a.kind);
  const debt = a.kind === "kredit";
  const word = debt ? "Restschuld" : value ? "Wert" : "Kontostand";
  const sh = openSheet(html`${sheetHead(`${word} ${a.name}`)}
    <p class="small muted">${debt ? "Trag ein, wie viel du heute noch schuldest. Die Restschuld zählt im Vermögen als Minus. Jeder Eintrag bleibt erhalten, so siehst du, wie der Kredit schrumpft."
      : value ? "Trag den aktuellen Wert ein. Jeder Eintrag bleibt erhalten, so siehst du die Entwicklung."
      : "Trag den Stand ein, den deine Bank für heute anzeigt. Für Kreditkarten den offenen Betrag als Minus. Spätere Buchungen werden dazugerechnet."}</p>
    <div class="field-row">
      <label class="field"><span>${word}</span><input class="input" id="bal-amt" inputmode="decimal" value="${a.balance_known ? toInput(debt ? Math.abs(a.balance_now) : a.balance_now) : ""}" autofocus></label>
      <label class="field"><span>Stand vom</span><input class="input" type="date" id="bal-date" value="${todayIso()}"></label>
    </div>
    <div class="actions"><button class="btn primary" id="bal-save">Speichern</button></div>`.s);
  $("#bal-save", sh.el).onclick = async () => {
    const cents = parseMoney($("#bal-amt", sh.el).value);
    if (cents === null) { toast("Bitte einen Betrag eintragen"); return; }
    await api(`accounts/${a.id}/balance`, { method: "POST", body: { balance_cents: cents, date: $("#bal-date", sh.el).value } });
    sh.close(); toast(`${word} gespeichert`); rerender();
  };
}

/* --- Datei-Import ----------------------------------------------------------------------- */
function pickImportFile() {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".csv,.txt,.xml,.zip,.sta,.mt940,.940";
  input.onchange = async () => {
    const f = input.files[0];
    if (!f) return;
    const form = new FormData();
    form.append("file", f);
    const sh = openSheet(html`${sheetHead("Datei wird gelesen")}<div class="progress"><div class="spinner"></div><span>${f.name}</span></div>`.s);
    try {
      const res = await api("import/analyze", { method: "POST", form });
      sh.close();
      importSheet(res);
    } catch (e) {
      sh.set(html`${sheetHead("Datei nicht lesbar")}<p>${e.message}</p><div class="actions"><button class="btn" data-close>Schließen</button></div>`.s);
    }
  };
  input.click();
}

function importSheet(res) {
  let mapping = res.mapping ? { ...res.mapping } : null;
  const sh = openSheet("", { wide: true });
  const draw = () => {
    const accs = store.accounts.filter((a) => !a.archived);
    const target = res.account_id || "";
    const skipped = Object.entries(res.skipped || {}).map(([k, v]) => `${v} ${k}`).join(", ");
    const cols = (res.headers || []).map((h, i) => ({ i, h: h || `Spalte ${i + 1}` }));
    const fields = ["date", "amount", "debit", "credit", "counterparty", "purpose", "iban", "booking_text", "balance", "status", "value_date"];
    sh.set(html`${sheetHead("Import prüfen")}
      ${res.error ? html`<p class="note">${res.error}</p>` : html`
      <p><strong>${res.format}</strong>: ${res.count} Buchungen${res.first ? ` vom ${dFull(res.first)} bis ${dFull(res.last)}` : ""}.${skipped ? html` <span class="muted">Übersprungen: ${skipped}.</span>` : ""}</p>
      ${res.invert_suggested ? html`<p class="note">Fast alle Beträge sind positiv. Bei Kreditkarten-Exporten sind Ausgaben oft ohne Minus – dann unten „Vorzeichen umkehren“ wählen.</p>` : ""}`}
      <label class="field"><span>In welches Konto?</span><select id="im-acc">
        <option value="">Neues Konto anlegen</option>
        ${accs.map((a) => html`<option value="${a.id}" ${a.id === target ? raw("selected") : ""}>${a.name}</option>`)}</select></label>
      <div id="im-new" ${target ? raw("hidden") : ""}>
        <div class="field-row">
          <label class="field"><span>Name</span><input class="input" id="im-name" value="${res.suggest.name}"></label>
          <label class="field"><span>Art</span><select id="im-kind">${Object.entries(KIND_LABEL).map(([k, l]) => html`<option value="${k}" ${k === res.suggest.kind ? raw("selected") : ""}>${l}</option>`)}</select></label>
        </div>
      </div>
      ${mapping ? html`<details ${res.error ? raw("open") : ""}><summary class="link-btn">Spaltenzuordnung prüfen</summary>
        <table class="map-table">${fields.map((f) => html`<tr><td>${res.field_labels[f]}</td><td><select data-map="${f}"><option value="">nicht vorhanden</option>
          ${cols.map((c) => html`<option value="${c.i}" ${(f === "purpose" ? (mapping.purpose || [])[0] === c.i : mapping[f] === c.i) ? raw("selected") : ""}>${c.h}</option>`)}</select></td></tr>`)}</table>
        <label class="check"><input type="checkbox" id="im-inv" ${mapping.invert ? raw("checked") : ""}><span>Vorzeichen umkehren (Ausgaben stehen in der Datei ohne Minus)</span></label>
      </details>` : ""}
      ${res.preview && res.preview.length ? html`<h3 style="margin-top:16px">Neueste Buchungen in der Datei</h3><ul class="list preview">${res.preview.map((r) => html`<li class="row static"><span class="title">${r.counterparty || r.purpose || r.booking_text || "–"}</span>
        <span class="sub">${dFull(r.booking_date)}${r.purpose && r.counterparty ? ", " + r.purpose : ""}</span><span class="amount ${r.amount_cents > 0 ? "pos" : ""}">${money(r.amount_cents, { plus: true })}</span></li>`)}</ul>` : ""}
      <p class="small muted">Bereits vorhandene Buchungen werden erkannt und nicht doppelt übernommen.</p>
      <div class="actions"><button class="btn primary" id="im-go" ${!res.count ? raw("disabled") : ""}>${res.count} Buchungen importieren</button><button class="btn" data-close>Abbrechen</button></div>`.s);
    $("#im-acc", sh.el).onchange = (e) => { res.account_id = e.target.value ? Number(e.target.value) : null; $("#im-new", sh.el).hidden = !!e.target.value; };
    const remap = async () => {
      $$("[data-map]", sh.el).forEach((s) => {
        const v = s.value === "" ? null : Number(s.value);
        if (s.dataset.map === "purpose") mapping.purpose = v === null ? [] : [v, ...(mapping.purpose || []).filter((x) => x !== v).slice(1)];
        else mapping[s.dataset.map] = v;
      });
      mapping.invert = $("#im-inv", sh.el).checked;
      const keep = res.account_id;
      const r2 = await api("import/remap", { method: "POST", body: { token: res.token, mapping } });
      res = { ...res, ...r2, account_id: keep };
      mapping = { ...r2.mapping };
      draw();
      $("details", sh.el).open = true;
    };
    on(sh.el, "[data-map]", "change", remap);
    if ($("#im-inv", sh.el)) $("#im-inv", sh.el).onchange = remap;
    $("#im-go", sh.el).onclick = async () => {
      $("#im-go", sh.el).disabled = true;
      const body = { token: res.token, mapping };
      if (res.account_id) body.account_id = res.account_id;
      else body.new_account = { name: $("#im-name", sh.el).value, kind: $("#im-kind", sh.el).value, settlement_pattern: res.suggest.settlement };
      try {
        const r = await api("import/commit", { method: "POST", body });
        sh.close();
        toast(`${r.added} Buchungen importiert${r.skipped ? `, ${r.skipped} waren schon da` : ""}`);
        await loadBase();
        if (!r.balance_known) {
          const acc = store.accounts.find((a) => a.id === r.account_id);
          if (acc && acc.in_forecast) balanceSheet(acc);
        }
        rerender();
      } catch (e) { toast(e.message); $("#im-go", sh.el).disabled = false; }
    };
  };
  draw();
}

/* --- FinTS ------------------------------------------------------------------------------- */
async function connectionSheet(c) {
  const isNew = !c;
  const banks = await api("banks");
  c = c || { name: "", blz: "", login: "", customer_id: "", server: "", history_days: 365 };
  const sh = openSheet(html`${sheetHead(isNew ? "Bankzugang hinzufügen" : c.name)}
    ${isNew ? html`<label class="field"><span>Bank</span><select id="cn-preset"><option value="">Andere Bank</option>${banks.map((b, i) => html`<option value="${i}">${b.name}</option>`)}</select></label>` : ""}
    <label class="field"><span>Name</span><input class="input" id="cn-name" value="${c.name}" placeholder="z. B. Sparkasse"></label>
    <div class="field-row">
      <label class="field"><span>Bankleitzahl</span><input class="input" id="cn-blz" value="${c.blz}" inputmode="numeric" placeholder="Stelle 5–12 der IBAN"></label>
      <label class="field"><span>Abruf beim ersten Mal</span><select id="cn-days">${[[90, "90 Tage"], [365, "1 Jahr"], [730, "2 Jahre"]].map(([v, l]) => html`<option value="${v}" ${v === c.history_days ? raw("selected") : ""}>${l}</option>`)}</select></label>
    </div>
    <label class="field"><span>Anmeldename (wie im Online-Banking)</span><input class="input" id="cn-login" value="${c.login}" autocomplete="off"></label>
    <label class="field"><span>Kundennummer, falls abweichend</span><input class="input" id="cn-cust" value="${c.customer_id || ""}" autocomplete="off"></label>
    <label class="field"><span>FinTS-Serveradresse</span><input class="input" id="cn-server" value="${c.server}" placeholder="https://…"></label>
    <p class="small muted" id="cn-hint">Die Adresse steht meist auf der Website deiner Bank unter „HBCI“ oder „FinTS“. Bei Sparkassen hängt sie vom Bundesland ab.</p>
    <div class="actions"><button class="btn primary" id="cn-save">${isNew ? "Speichern und abrufen" : "Speichern"}</button>
      ${!isNew ? html`<button class="btn" id="cn-tan">TAN-Verfahren neu wählen</button>${c.has_pin ? html`<button class="btn" id="cn-pin">Gespeicherte PIN löschen</button>` : ""}<button class="btn danger" id="cn-del">Löschen</button>` : ""}</div>`.s);
  if ($("#cn-preset", sh.el)) $("#cn-preset", sh.el).onchange = (e) => {
    const b = banks[Number(e.target.value)];
    if (!b) return;
    $("#cn-name", sh.el).value = b.name.split(" ")[0];
    if (b.blz) $("#cn-blz", sh.el).value = b.blz;
    $("#cn-server", sh.el).value = b.server;
  };
  $("#cn-save", sh.el).onclick = async () => {
    const body = { name: $("#cn-name", sh.el).value, blz: $("#cn-blz", sh.el).value, login: $("#cn-login", sh.el).value, customer_id: $("#cn-cust", sh.el).value,
      server: $("#cn-server", sh.el).value, history_days: Number($("#cn-days", sh.el).value) };
    try {
      if (isNew) {
        const r = await api("connections", { method: "POST", body });
        sh.close();
        const conns = await api("connections");
        syncSheet(conns.find((x) => x.id === r.id));
      } else { await api(`connections/${c.id}`, { method: "PATCH", body }); sh.close(); toast("Gespeichert"); rerender(); }
    } catch (e) { toast(e.message); }
  };
  if (!isNew) {
    $("#cn-tan", sh.el).onclick = async () => { await api(`connections/${c.id}/reset-tan`, { method: "POST" }); toast("Beim nächsten Abruf wird das TAN-Verfahren neu abgefragt"); };
    if ($("#cn-pin", sh.el)) $("#cn-pin", sh.el).onclick = async () => { await api(`connections/${c.id}/pin`, { method: "DELETE" }); sh.close(); toast("PIN gelöscht, kein automatischer Abruf mehr"); rerender(); };
    confirmButton($("#cn-del", sh.el), "Wirklich löschen? Konten bleiben", async () => { await api(`connections/${c.id}`, { method: "DELETE" }); sh.close(); rerender(); });
  }
}

function syncSheet(conn) {
  const sh = openSheet("", { onClose: () => { stopped = true; clearInterval(flickerTimer); } });
  let stopped = false, flickerTimer = null, job = null, lastQid = null;
  const askPin = (msg) => {
    sh.set(html`${sheetHead("Umsätze abrufen: " + conn.name)}
      ${msg ? html`<p class="note">${msg}</p>` : ""}
      <label class="field"><span>Online-Banking-PIN</span><input class="input" type="password" id="sy-pin" autocomplete="off" autofocus></label>
      <label class="check"><input type="checkbox" id="sy-save"><span>PIN auf dem Home-Assistant-Gerät speichern und täglich automatisch abrufen.
        <span class="muted small">Sie liegt dann unverschlüsselt in den Daten der App, ist aber von Home-Assistant-Backups ausgenommen.</span></span></label>
      <div class="actions"><button class="btn primary" id="sy-go">Abrufen</button></div>`.s);
    const go_ = () => start({ pin: $("#sy-pin", sh.el).value, save_pin: $("#sy-save", sh.el).checked });
    $("#sy-go", sh.el).onclick = go_;
    $("#sy-pin", sh.el).addEventListener("keydown", (e) => { if (e.key === "Enter") go_(); });
  };
  const start = async (body) => {
    try { job = await api(`connections/${conn.id}/sync`, { method: "POST", body }); poll(); }
    catch (e) { askPin(e.message); }
  };
  const poll = async () => {
    if (stopped) return;
    try { job = await api(`jobs/${job.id}`); } catch (e) { draw({ state: "error", error: e.message }); return; }
    draw(job);
    if (["running", "waiting"].includes(job.state)) setTimeout(poll, 1000);
  };
  const cancelBtn = html`<button class="btn" id="sy-cancel">Abbrechen</button>`;
  const draw = (j) => {
    const q = j.question;
    if (j.state === "waiting" && q && q.qid === lastQid) return;
    clearInterval(flickerTimer);
    if (j.state === "running" || (j.state === "waiting" && !q)) {
      lastQid = null;
      sh.set(html`${sheetHead(conn.name)}<div class="progress"><div class="spinner"></div><span>${j.step}</span></div><div class="actions">${cancelBtn}</div>`.s);
    } else if (j.state === "waiting" && q.kind === "decoupled") {
      lastQid = q.qid;
      sh.set(html`${sheetHead("Freigabe in der App")}<p>${q.text}</p><div class="progress"><div class="spinner"></div><span>Warte auf deine Bestätigung …</span></div>
        <div class="actions"><button class="btn primary" id="sy-ok">Ich habe freigegeben</button>${cancelBtn}</div>`.s);
      $("#sy-ok", sh.el).onclick = () => api(`jobs/${j.id}/answer`, { method: "POST", body: { value: "ok" } });
    } else if (j.state === "waiting" && q.kind === "choice") {
      lastQid = q.qid;
      sh.set(html`${sheetHead(q.title)}<div class="list">${q.options.map((o, i) => html`<label class="check"><input type="radio" name="sy-choice" value="${o.value}" ${i === 0 ? raw("checked") : ""}><span>${o.label}${o.hint ? html` <span class="muted small">${o.hint}</span>` : ""}</span></label>`)}</div>
        <div class="actions"><button class="btn primary" id="sy-next">Weiter</button>${cancelBtn}</div>`.s);
      $("#sy-next", sh.el).onclick = () => { const v = $("input[name=sy-choice]:checked", sh.el).value; lastQid = null; api(`jobs/${j.id}/answer`, { method: "POST", body: { value: v } }); };
    } else if (j.state === "waiting" && q.kind === "tan") {
      lastQid = q.qid;
      sh.set(html`${sheetHead("TAN eingeben")}
        <div>${q.html ? raw(q.html) : q.text}</div>
        ${q.image ? html`<img class="tan-image" src="${q.image}" alt="TAN-Grafik">` : ""}
        ${q.flicker ? html`<div class="flicker" id="sy-flicker" aria-label="Flickercode">${[0, 1, 2, 3, 4].map(() => raw("<span></span>"))}</div>
          <div class="actions" style="justify-content:center;margin-top:0"><button class="btn small" id="fl-slow">Langsamer</button><button class="btn small" id="fl-fast">Schneller</button></div>` : ""}
        <label class="field"><span>TAN</span><input class="input" id="sy-tan" inputmode="numeric" autocomplete="one-time-code" autofocus></label>
        <div class="actions"><button class="btn primary" id="sy-send">Bestätigen</button>${cancelBtn}</div>`.s);
      const send = () => { lastQid = null; api(`jobs/${j.id}/answer`, { method: "POST", body: { value: $("#sy-tan", sh.el).value } }); };
      $("#sy-send", sh.el).onclick = send;
      $("#sy-tan", sh.el).addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
      if (q.flicker) {
        let i = 0, speed = 80;
        const bars = $$("#sy-flicker span", sh.el);
        const tick = () => { const f = q.flicker[i++ % q.flicker.length]; bars.forEach((b, k) => b.classList.toggle("on", f[k] === "1")); };
        const startF = () => { clearInterval(flickerTimer); flickerTimer = setInterval(tick, speed); };
        $("#fl-slow", sh.el).onclick = () => { speed = Math.min(200, speed + 15); startF(); };
        $("#fl-fast", sh.el).onclick = () => { speed = Math.max(30, speed - 15); startF(); };
        startF();
      }
    } else if (j.state === "done") {
      const r = j.result || { accounts: [], added: 0 };
      sh.set(html`${sheetHead("Abruf fertig")}<p>${r.added ? `${r.added} neue Buchungen` : "Keine neuen Buchungen"} auf ${r.accounts.length} ${r.accounts.length === 1 ? "Konto" : "Konten"}.</p>
        <ul class="list">${r.accounts.map((a) => html`<li class="row static"><span class="title">${a.name}</span><span class="amount">${a.added} neu</span></li>`)}</ul>
        <div class="actions"><button class="btn primary" data-close>Fertig</button></div>`.s);
      rerender();
    } else if (j.state === "error" && /PIN/.test(j.error || "") && !/gesperrt/.test(j.error || "")) {
      askPin(j.error);
    } else {
      sh.set(html`${sheetHead("Abruf fehlgeschlagen")}<p>${j.error || "Abgebrochen."}</p><div class="actions"><button class="btn primary" id="sy-retry">Erneut versuchen</button><button class="btn" data-close>Schließen</button></div>`.s);
      $("#sy-retry", sh.el).onclick = () => (conn.has_pin ? start({}) : askPin());
    }
    if ($("#sy-cancel", sh.el)) $("#sy-cancel", sh.el).onclick = async () => { await api(`jobs/${j.id}/cancel`, { method: "POST" }); sh.close(); };
  };
  if (conn.has_pin) start({}); else askPin();
}

/* ------------------------------------------------------------------ Einstellungen */
async function renderSettings(view, _params, seq) {
  const [s, rules, learned, devices] = await Promise.all([
    api("settings"),
    api("rules"),
    api("learned"),
    api("mobile/devices").catch(() => ({ items: [] })),
  ]);
  if (seq !== renderSeq) return;
  const p = s.profile || {};
  view.innerHTML = html`
    <div class="page-head"><h1>Einstellungen</h1></div>
    <div class="cols"><div>
      <section class="section" style="border-top:0">
        <div class="section-head"><h2>Deine Angaben für Kündigungen</h2></div>
        <label class="field"><span>Vor- und Nachname</span><input class="input" id="s-name" value="${p.name || ""}" autocomplete="name"></label>
        <label class="field"><span>Straße und Hausnummer</span><input class="input" id="s-street" value="${p.street || ""}" autocomplete="street-address"></label>
        <label class="field"><span>PLZ und Ort</span><input class="input" id="s-city" value="${p.city || ""}"></label>
        <label class="field"><span>E-Mail</span><input class="input" id="s-email" type="email" value="${p.email || ""}" autocomplete="email"></label>
        <div class="section-head" style="margin-top:22px"><h2>Sicherheitspuffer</h2></div>
        <label class="field"><span>So viel soll bei „frei verfügbar“ immer übrig bleiben</span><input class="input" id="s-buffer" inputmode="decimal" value="${toInput(s.buffer_cents)}" placeholder="0,00"></label>
        <label class="check"><input type="checkbox" id="s-reserve" ${s.deduct_reserve ? raw("checked") : ""}><span>Rücklage für viertel-, halb- und jährliche Kosten von „frei verfügbar“ abziehen
          <span class="muted small">Lass das aus, wenn du dafür schon Geld auf einem Tagesgeld- oder Sparkonto zurücklegst.</span></span></label>
        <div class="actions"><button class="btn primary" id="s-save">Speichern</button></div>
      </section>
      <section class="section">
        <div class="section-head"><h2>Home Assistant</h2></div>
        <p class="small">${s.ha ? "Verbunden. Kassensturz stellt diese Sensoren bereit:" : "Keine Verbindung zu Home Assistant – Sensoren und Benachrichtigungen sind aus."}</p>
        ${s.ha ? html`<p class="small muted">sensor.kassensturz_kontostand, _frei_verfuegbar, _prognose_monatsende, _tiefster_stand, _fixkosten_monat, _ausgaben_monat, _naechste_zahlung sowie je Konto und Budget einen Sensor.</p>` : ""}
        <p class="small muted">Warnschwelle ${s.options.warn_threshold} €, täglicher Abruf um ${s.options.sync_time} Uhr, Benachrichtigung über ${s.options.notify_service || "persistente Meldungen"}. Ändern lässt sich das in der Konfiguration der App.</p>
      </section>
      <section class="section">
        <div class="section-head">
          <h2>Mobile Geräte</h2>
          <button class="link-btn" id="mobile-pair">Gerät koppeln</button>
        </div>
        <p class="small muted">Hier verwaltest du die Geräte, die auf Kassensturz Mobile zugreifen dürfen. Ein Pairing-Code ist fünf Minuten gültig und kann nur einmal verwendet werden.</p>
        ${s.options.mobile_server_url ? html`<p class="small muted">Mobile-Adresse für QR-Pairing: <code>${s.options.mobile_server_url}</code></p>` : html`<p class="small muted">Für QR-Pairing muss in den Home-Assistant-App-Optionen die externe HTTPS-Adresse als <code>mobile_server_url</code> hinterlegt sein. Ohne diese Einstellung bleibt die manuelle Code-Eingabe verfügbar.</p>`}
        <div id="mobile-pair-result" aria-live="polite"></div>
        <div id="mobile-device-list">
          ${devices.items.length ? html`<ul class="list">${devices.items.map((d) => html`
            <li class="row static">
              <span class="title">${d.name}</span>
              <span class="sub">${d.revoked_at ? "Widerrufen" : "Aktiv"} · hinzugefügt ${d.created_at ? dFull(d.created_at.slice(0, 10)) : "–"}${d.last_used_at ? ` · zuletzt aktiv ${dFull(d.last_used_at.slice(0, 10))}` : ""}</span>
              <span class="amount">${!d.revoked_at ? html`<button class="btn small danger" data-mobile-revoke="${d.id}">Widerrufen</button>` : html`<span class="small muted">Gesperrt</span>`}</span>
            </li>` )}</ul>` : html`<p class="small muted">Noch keine gekoppelten Geräte.</p>`}
        </div>
      </section>
    </div><div>
      <section class="section" style="border-top:0">
        <div class="section-head"><h2>Regeln für Kategorien</h2><button class="link-btn" id="r-add">Regel hinzufügen</button></div>
        ${rules.length ? html`<ul class="list">${rules.map((r) => html`<li class="row static"><span class="title">„${r.pattern}“</span>
          <span class="sub">${r.mark_transfer ? "Umbuchung" : r.category_name || "–"}${r.sign === "in" ? ", nur Eingänge" : r.sign === "out" ? ", nur Ausgänge" : ""}</span>
          <span class="amount"><button class="btn small" data-rdel="${r.id}">Entfernen</button></span></li>`)}</ul>`
          : html`<p class="small muted">Noch keine eigenen Regeln. Ändere bei einer Buchung die Kategorie, dann bietet Kassensturz an, das für ähnliche Buchungen zu merken.</p>`}
      </section>
      <section class="section">
        <div class="section-head"><h2>Gelernt</h2></div>
        ${learned.length ? html`<ul class="list">${learned.map((l) => html`<li class="row static"><span class="title">${l.label}</span>
          <span class="sub">${l.category_name || "–"}${l.sign === "in" ? ", Eingänge" : ""}</span>
          <span class="amount"><button class="btn small" data-ldel="${l.id}">Vergessen</button></span></li>`)}</ul>`
          : html`<p class="small muted">Noch nichts gelernt. Ändere bei einer Buchung die Kategorie, dann merkt sich Kassensturz den Empfänger und ordnet ähnliche Buchungen genauso zu.</p>`}
      </section>
      <section class="section">
        <div class="section-head"><h2>Kategorien</h2><button class="link-btn" id="k-add">Unterkategorie hinzufügen</button></div>
        <p class="small muted">${topCats().map((c) => c.name).join(", ")}.</p>
      </section>
      <section class="section">
        <div class="section-head"><h2>Steuer</h2></div>
        <div id="tax-box"></div>
      </section>
      <section class="section">
        <div class="section-head"><h2>Garantien</h2></div>
        <div id="warranty-box"></div>
      </section>
      <section class="section">
        <div class="section-head"><h2>Daten</h2></div>
        <div class="actions" style="margin-top:0">
          <a class="btn small" href="api/export.csv" download>Alle Buchungen als CSV</a>
          <a class="btn small" href="api/umzug/export" download>Datenbank für Umzug</a>
          <button class="btn small" id="d-recat">Alles neu kategorisieren</button>
          ${store.state.demo ? html`<button class="btn small danger" id="d-demo-off">Beispieldaten entfernen</button>` : html`<button class="btn small" id="d-demo">Beispieldaten laden</button>`}
        </div>
        <p class="small muted" style="margin-top:14px">Kassensturz ${s.options ? store.state.version : ""}. Alle Daten liegen nur auf diesem Home-Assistant-Gerät.</p>
      </section>
    </div></div>`.s;
  drawTax($("#tax-box"));
  drawWarranties($("#warranty-box"));
  $("#mobile-pair").onclick = async () => {
    const button = $("#mobile-pair");
    button.disabled = true;
    try {
      const pairing = await api("mobile/pairings", { method: "POST" });
      $("#mobile-pair-result").innerHTML = html`
        <div class="note" style="margin:12px 0" role="status">
          <strong>Einmaliger Pairing-Code</strong>
          <p class="small muted">Gib diesen Code in Kassensturz Mobile ein. Er verfällt am ${new Date(pairing.expires_at).toLocaleString("de-DE")}. Er kann nur einmal verwendet werden.</p>
          ${pairing.qr_svg_base64 ? html`
            <div style="display:flex;justify-content:center;padding:12px 0">
              <img
                src="data:image/svg+xml;base64,${pairing.qr_svg_base64}"
                alt="Einmaliger Kassensturz-Pairing-QR-Code"
                width="240"
                height="240"
                style="max-width:100%;height:auto;background:white;padding:8px;border-radius:8px"
              >
            </div>
            <p class="small muted">Server: ${pairing.server_url}</p>
          ` : html`
            <p class="small muted">Kein QR-Code verfügbar. Trage Serveradresse und Code manuell in der App ein.</p>
          `}
          <code id="mobile-pair-secret" style="display:block;overflow-wrap:anywhere;padding:10px 0">${pairing.pairing_secret}</code>
          <button class="btn small" id="mobile-pair-copy">Code kopieren</button>
        </div>`.s;
      $("#mobile-pair-copy").onclick = async () => {
        const secret = $("#mobile-pair-secret").textContent;
        try {
          await navigator.clipboard.writeText(secret);
          toast("Pairing-Code kopiert");
        } catch {
          const field = document.createElement("textarea");
          field.value = secret;
          field.style.position = "fixed";
          field.style.opacity = "0";
          document.body.appendChild(field);
          field.select();
          const copied = document.execCommand("copy");
          field.remove();
          toast(copied ? "Pairing-Code kopiert" : "Code bitte manuell markieren und kopieren");
        }
      };
      button.textContent = "Neuen Code erzeugen";
    } catch (err) {
      toast(err.message);
    } finally {
      button.disabled = false;
    }
  };
  $$("[data-mobile-revoke]", view).forEach((button) => confirmButton(button, "Wirklich widerrufen?", async () => {
    try {
      await api(`mobile/devices/${encodeURIComponent(button.dataset.mobileRevoke)}`, { method: "DELETE" });
      toast("Gerät wurde widerrufen");
      rerender();
    } catch (err) {
      toast(err.message);
    }
  }));
  $("#s-save").onclick = async () => {
    await api("settings", { method: "PUT", body: { profile: { name: $("#s-name").value, street: $("#s-street").value, city: $("#s-city").value, email: $("#s-email").value },
      buffer_cents: Math.abs(parseMoney($("#s-buffer").value) || 0), deduct_reserve: $("#s-reserve").checked } });
    toast("Gespeichert");
  };
  on(view, "[data-rdel]", "click", async (_e, el) => { const r = await api(`rules/${el.dataset.rdel}`, { method: "DELETE" }); toast(`Regel entfernt, ${r.recategorized} Buchungen neu zugeordnet`); rerender(); });
  on(view, "[data-ldel]", "click", async (_e, el) => { const r = await api(`learned/${el.dataset.ldel}`, { method: "DELETE" }); toast(`Vergessen, ${r.recategorized} Buchungen neu zugeordnet`); rerender(); });
  $("#r-add").onclick = () => ruleSheet();
  $("#k-add").onclick = () => categorySheet();
  $("#d-recat").onclick = async () => { const r = await api("recategorize", { method: "POST" }); toast(`${r.recategorized} Buchungen neu zugeordnet`); };
  if ($("#d-demo")) $("#d-demo").onclick = async () => { await api("demo", { method: "POST" }); toast("Beispieldaten geladen"); go(""); };
  if ($("#d-demo-off")) confirmButton($("#d-demo-off"), "Wirklich entfernen?", async () => { await api("demo", { method: "DELETE" }); toast("Beispieldaten entfernt"); rerender(); });
}

function ruleSheet() {
  let cat = null;
  const sh = openSheet(html`${sheetHead("Regel hinzufügen")}
    <label class="field"><span>Wenn Name oder Zweck dieses Wort enthält</span><input class="input" id="ru-pat" autofocus placeholder="z. B. edeka"></label>
    <label class="field"><span>Für</span><select id="ru-sign"><option value="any">Ein- und Ausgänge</option><option value="out">nur Ausgänge</option><option value="in">nur Eingänge</option></select></label>
    <h3>Dann Kategorie</h3>${categoryPicker(null, -1)}
    <div class="actions"><button class="btn primary" id="ru-save">Regel anlegen</button></div>`.s);
  bindCategoryPicker(sh.el, (id) => { cat = id; });
  $("#ru-save", sh.el).onclick = async () => {
    if (!cat) { toast("Bitte eine Kategorie wählen"); return; }
    try { const r = await api("rules", { method: "POST", body: { pattern: $("#ru-pat", sh.el).value, sign: $("#ru-sign", sh.el).value, category_id: cat } }); sh.close(); toast(`Regel angelegt, ${r.recategorized} Buchungen neu zugeordnet`); rerender(); }
    catch (e) { toast(e.message); }
  };
}

function categorySheet() {
  const sh = openSheet(html`${sheetHead("Unterkategorie hinzufügen")}
    <label class="field"><span>Name</span><input class="input" id="ka-name" autofocus></label>
    <label class="field"><span>Gehört zu</span><select id="ka-parent">${topCats().filter((c) => c.kind !== "transfer").map((c) => html`<option value="${c.id}">${c.name}</option>`)}</select></label>
    <div class="actions"><button class="btn primary" id="ka-save">Hinzufügen</button></div>`.s);
  $("#ka-save", sh.el).onclick = async () => {
    try { await api("categories", { method: "POST", body: { name: $("#ka-name", sh.el).value, parent_id: Number($("#ka-parent", sh.el).value) } }); sh.close(); toast("Kategorie hinzugefügt"); rerender(); }
    catch (e) { toast(e.message); }
  };
}

/* ------------------------------------------------------------------ Start */
route();
