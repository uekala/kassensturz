// Kassensturz – Oberfläche, core. Aufgeteilt aus app.js; Exporte und Importe zwischen den Modulen.


/* ------------------------------------------------------------------ Grundlagen */
export class Raw { constructor(s) { this.s = s; } toString() { return this.s; } }
export const raw = (s) => new Raw(s);
export const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export function html(strings, ...vals) {
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
export const $ = (sel, el = document) => el.querySelector(sel);
export const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
export function on(root, sel, ev, fn) {
  $$(sel, root).forEach((el) => el.addEventListener(ev, (e) => fn(e, el)));
}

export async function api(path, { method = "GET", body, form } = {}) {
  const opts = { method, headers: {} };
  if (form) opts.body = form;
  else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers["Content-Type"] = "application/json"; }
  let res;
  try {
    res = await fetch("api/" + path, opts);
  } catch {
    // fetch wirft nur ohne Antwort: Netz weg, Add-on neu gestartet oder Home Assistant nicht erreichbar.
    throw new Error("Keine Verbindung zu Kassensturz. Bitte Netz prüfen und gleich noch einmal versuchen.");
  }
  let data = null;
  try { data = await res.json(); } catch { /* leer */ }
  if (!res.ok) {
    const msg = data?.error?.message || (data && data.detail ? (typeof data.detail === "string" ? data.detail : "Eingabe ungültig.") : `Fehler ${res.status}`);
    throw new Error(msg);
  }
  return data;
}

export const NF = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const NF0 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });
export function money(cents, { plus = false } = {}) {
  if (cents === null || cents === undefined) return "–";
  const s = NF.format(Math.abs(cents) / 100) + " €";
  if (cents < 0) return "−" + s;
  return (plus && cents > 0 ? "+" : "") + s;
}
export function moneyRound(cents) {
  if (cents === null || cents === undefined) return "–";
  return (cents < 0 ? "−" : "") + NF0.format(Math.abs(cents) / 100) + " €";
}
export function parseMoney(text) {
  let s = String(text || "").trim().replace(/[€\s]/g, "").replace("−", "-");
  if (!s) return null;
  if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
  const v = Number(s);
  return Number.isFinite(v) ? Math.round(v * 100) : null;
}
export const toInput = (cents) => (cents === null || cents === undefined ? "" : NF.format(cents / 100).replace(/\./g, ""));
export const D = (iso) => new Date(iso + "T12:00:00");
export const fmtShort = new Intl.DateTimeFormat("de-DE", { day: "numeric", month: "short" });
export const fmtDay = new Intl.DateTimeFormat("de-DE", { weekday: "long", day: "numeric", month: "long" });
export const fmtFull = new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
export const fmtMonth = new Intl.DateTimeFormat("de-DE", { month: "long", year: "numeric" });
export const dShort = (iso) => (iso ? fmtShort.format(D(iso)) : "–");
export const dFull = (iso) => (iso ? fmtFull.format(D(iso)) : "–");
export const todayIso = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
export function relDay(iso) {
  const days = Math.round((D(iso) - D(todayIso())) / 86400000);
  if (days === 0) return "heute";
  if (days === 1) return "morgen";
  if (days === -1) return "gestern";
  if (days > 1 && days < 7) return `in ${days} Tagen`;
  return dShort(iso);
}
export const KIND_LABEL = { giro: "Girokonto", tagesgeld: "Tagesgeld", sparkonto: "Sparkonto", festgeld: "Festgeld", vl: "VL / Bausparen", depot: "Depot", immobilie: "Immobilie", kredit: "Kredit", kreditkarte: "Kreditkarte", paypal: "PayPal", bargeld: "Bargeld", taschengeld: "Taschengeld", sonstiges: "Sonstiges" };
// Konten, deren Wert man einträgt statt Buchungen abzurufen.
export const PCT = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 3 });
export const VALUE_KINDS = new Set(["depot", "festgeld", "vl", "immobilie", "kredit"]);
export const SAVINGS_KINDS = new Set(["tagesgeld", "sparkonto", ...VALUE_KINDS]);
export const MATURING_KINDS = new Set(["festgeld", "kredit"]);
export const GROUP_LABEL = { alltag: "Alltag", ruecklagen: "Rücklagen", depots: "Depots", immobilien: "Immobilien", kredite: "Kredite" };

export const ICON = {
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

export let toastTimer;
export function toast(text, { error = false } = {}) {
  const el = $("#toast");
  el.textContent = text;
  el.classList.toggle("error", error);
  // Fehler sofort vorlesen, sonst höflich warten.
  el.setAttribute("aria-live", error ? "assertive" : "polite");
  el.classList.add("show");
  clearTimeout(toastTimer);
  // Längere Meldungen bleiben länger stehen, damit man sie zu Ende lesen kann.
  const ms = Math.min(9000, Math.max(3200, String(text || "").length * 60));
  toastTimer = setTimeout(() => el.classList.remove("show"), ms);
}

/* ------------------------------------------------------------------ Zustand */
export const store = { cats: [], catById: new Map(), accounts: [], persons: [], state: {} };
export async function loadBase() {
  const [cats, accounts, state, persons] = await Promise.all([api("categories"), api("accounts"), api("state"), api("persons")]);
  store.persons = persons;
  store.cats = cats;
  store.catById = new Map(cats.map((c) => [c.id, c]));
  store.accounts = accounts;
  store.state = state;
}
export function personName(id) { return store.persons.find((p) => p.id === id)?.name || ""; }
export function catName(id) { return store.catById.get(id)?.name || "Ohne Kategorie"; }
export function topCats() { return store.cats.filter((c) => !c.parent_id); }
export function childCats(id) { return store.cats.filter((c) => c.parent_id === id); }

/* ------------------------------------------------------------------ Sheet */
export let sheetStack = [];
export function openSheet(content, { onClose, wide = false } = {}) {
  const root = $("#sheet-root");
  const back = document.createElement("div");
  back.className = "sheet-backdrop";
  back.innerHTML = `<div class="sheet" role="dialog" aria-modal="true" ${wide ? 'style="max-width:820px"' : ""}><div class="sheet-grip"></div>${content}</div>`;
  root.appendChild(back);
  document.documentElement.classList.add("sheet-open");
  const sheet = $(".sheet", back);
  const prevFocus = document.activeElement;
  const close = () => {
    back.remove();
    sheetStack = sheetStack.filter((s) => s !== api_);
    if (!sheetStack.length) document.documentElement.classList.remove("sheet-open");
    document.removeEventListener("keydown", onKey);
    if (onClose) onClose();
    if (prevFocus && prevFocus.focus) prevFocus.focus();
  };
  const onKey = (e) => {
    if (sheetStack[sheetStack.length - 1] !== api_) return;
    if (e.key === "Escape") { close(); return; }
    // Tab bleibt im offenen Fenster, statt hinter dem Fenster weiterzuspringen.
    if (e.key === "Tab") {
      const items = $$('a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])', sheet)
        .filter((el) => el.offsetParent !== null);
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && (document.activeElement === first || !sheet.contains(document.activeElement))) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  };
  document.addEventListener("keydown", onKey);
  back.addEventListener("mousedown", (e) => { if (e.target === back) close(); });
  on(sheet, "[data-close]", "click", close);
  const api_ = { el: sheet, close, set(content2) { sheet.innerHTML = `<div class="sheet-grip"></div>${content2}`; on(sheet, "[data-close]", "click", close); } };
  sheetStack.push(api_);
  setTimeout(() => { const f = $("[autofocus]", sheet) || $("h2", sheet); if (f) { f.setAttribute("tabindex", "-1"); f.focus(); } }, 30);
  return api_;
}
export const sheetHead = (title) => html`<div class="sheet-head"><h2>${title}</h2><button class="icon-btn" data-close aria-label="Schließen">${raw(ICON.close)}</button></div>`;

export function confirmButton(btn, label, fn) {
  let armed = false;
  btn.addEventListener("click", async () => {
    if (!armed) {
      armed = true; btn.dataset.label = btn.textContent; btn.textContent = label; btn.classList.add("armed");
      setTimeout(() => { armed = false; btn.textContent = btn.dataset.label; btn.classList.remove("armed"); }, 4000);
      return;
    }
    armed = false; btn.classList.remove("armed");
    btn.disabled = true;
    try { await fn(); } catch (err) { toast(err.message, { error: true }); } finally { btn.disabled = false; }
  });
}
