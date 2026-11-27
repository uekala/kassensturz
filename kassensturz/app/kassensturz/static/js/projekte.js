// Kassensturz – Oberfläche, projekte. Aufgeteilt aus app.js; Exporte und Importe zwischen den Modulen.

import { $, D, api, dFull, fmtMonth, html, money, on, openSheet, parseMoney, sheetHead, toInput, toast } from "./core.js";
import { go, rerender } from "./router.js";
import { TX_FILTERS } from "./umsaetze.js";

/* ------------------------------------------------------------------ Projekte */
// Ein Projekt: Gesamtkosten, Rahmen, Verteilung auf Kategorien und Monate, jüngste Buchungen.
export async function projectSheet(id) {
  let p;
  try { p = await api("projects/" + id); } catch (err) { toast(err.message, { error: true }); return; }
  const maxCat = Math.max(1, ...p.categories.map((c) => c.cents));
  const used = p.budget_cents ? Math.min(100, Math.round((Math.max(0, p.cost_cents) / p.budget_cents) * 100)) : 0;
  const sh = openSheet(html`${sheetHead(p.name)}
    <div class="big-amount">${money(p.cost_cents)}</div>
    <p class="small muted">${p.count ? `${p.count} ${p.count === 1 ? "Buchung" : "Buchungen"} von ${dFull(p.first)} bis ${dFull(p.last)}` : "Noch keine Buchungen. Ordne sie an der Buchung zu, oder such in den Umsätzen und nimm alle Treffer."}${p.back_cents ? `. Ausgegeben ${money(p.spent_cents)}, zurückbekommen ${money(p.back_cents)}` : ""}${p.note ? `. ${p.note}` : ""}</p>
    ${p.budget_cents ? html`<div class="meter"><div class="fill ${p.left_cents < 0 ? "over" : ""}" style="width:${used}%"></div></div>
      <p class="small ${p.left_cents < 0 ? "" : "muted"}">${p.left_cents >= 0 ? `Noch ${money(p.left_cents)} von ${money(p.budget_cents)} im Rahmen.` : `${money(-p.left_cents)} über dem Rahmen von ${money(p.budget_cents)}.`}</p>` : ""}
    ${p.categories.length ? html`<h3 style="margin-top:18px">Nach Kategorie</h3><ul class="bars">${p.categories.map((c) => html`
      <li class="bar-row" style="cursor:default"><span class="label">${c.name}</span><span class="val">${money(c.cents)}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${(c.cents / maxCat) * 100}%"></div></div></li>`)}</ul>` : ""}
    ${p.months.length > 1 ? html`<h3 style="margin-top:18px">Nach Monat</h3><ul class="list">${p.months.map((m) => html`<li class="row static"><span class="title">${fmtMonth.format(D(m.month + "-01"))}</span><span class="amount">${money(m.cents)}</span></li>`)}</ul>` : ""}
    ${p.transactions.length ? html`<h3 style="margin-top:18px">Buchungen</h3><ul class="list">${p.transactions.slice(0, 8).map((t) => html`<li class="row static"><span class="title">${t.counterparty || t.purpose || "Buchung"}</span>
      <span class="sub">${dFull(t.booking_date)}, ${t.is_transfer ? "Umbuchung, zählt nicht" : t.category_name || "Ohne Kategorie"}</span><span class="amount ${t.amount_cents > 0 ? "pos" : ""}">${money(t.amount_cents, { plus: true })}</span></li>`)}</ul>` : ""}
    <div class="actions">${p.count ? html`<button class="btn primary" id="pr-tx">Alle Buchungen ansehen</button>` : html`<button class="btn primary" id="pr-find">Buchungen suchen</button>`}
      <button class="btn" id="pr-edit">Ändern</button><button class="btn" id="pr-arch">${p.archived ? "Wieder öffnen" : "Abschließen"}</button><button class="btn danger" id="pr-del">Löschen</button></div>`.s);
  if ($("#pr-tx", sh.el)) $("#pr-tx", sh.el).onclick = () => { sh.close(); go("umsaetze", { project: String(p.id) }); };
  if ($("#pr-find", sh.el)) $("#pr-find", sh.el).onclick = () => { sh.close(); go("umsaetze"); };
  $("#pr-edit", sh.el).onclick = () => { sh.close(); projectEditSheet(p); };
  $("#pr-arch", sh.el).onclick = async () => {
    try { await api("projects/" + p.id, { method: "POST", body: { archived: !p.archived } }); sh.close(); toast(p.archived ? "Wieder geöffnet" : "Abgeschlossen"); rerender(); }
    catch (err) { toast(err.message, { error: true }); }
  };
  let sure = false;
  $("#pr-del", sh.el).onclick = async (e) => {
    if (!sure) { sure = true; e.target.textContent = "Wirklich löschen? Die Buchungen bleiben"; return; }
    try { await api("projects/" + p.id, { method: "DELETE" }); sh.close(); toast("Projekt gelöscht"); rerender(); } catch (err) { toast(err.message, { error: true }); }
  };
}

// Legt ein Projekt an oder ändert Name, Rahmen und Notiz. done(p) bekommt das gespeicherte Projekt.
export function projectEditSheet(p, done) {
  const sh = openSheet(html`${sheetHead(p ? "Projekt ändern" : "Projekt anlegen")}
    <label class="field"><span>Name</span><input class="input" id="pr-name" maxlength="60" placeholder="z. B. Urlaub 2027" value="${p ? p.name : ""}" autofocus></label>
    <label class="field"><span>Rahmen in Euro (optional)</span><input class="input" id="pr-budget" inputmode="decimal" value="${p && p.budget_cents ? toInput(p.budget_cents) : ""}"></label>
    <label class="field"><span>Notiz</span><input class="input" id="pr-note" maxlength="200" value="${p && p.note ? p.note : ""}"></label>
    <div class="actions"><button class="btn primary" id="pr-save">${p ? "Speichern" : "Anlegen"}</button><button class="btn" data-close>Abbrechen</button></div>`.s);
  $("#pr-save", sh.el).onclick = async () => {
    const raw$ = $("#pr-budget", sh.el).value.trim();
    const budget = raw$ ? parseMoney(raw$) : 0;
    if (raw$ && (budget === null || budget < 0)) { toast("Der Rahmen ist kein Betrag"); return; }
    const body = { name: $("#pr-name", sh.el).value, budget_cents: budget || null, note: $("#pr-note", sh.el).value };
    try {
      const saved = await api(p ? "projects/" + p.id : "projects", { method: "POST", body });
      sh.close();
      if (done) done(saved); else { toast(p ? "Gespeichert" : "Projekt angelegt"); rerender(); }
    } catch (err) { toast(err.message, { error: true }); }
  };
}

// Alle Treffer der Buchungsliste einem Projekt zuordnen: vorhandenes wählen oder neu anlegen.
export async function projectPickSheet(params) {
  const filter = {};
  TX_FILTERS.forEach((k) => { if (params[k]) filter[k] = params[k]; });
  const list = (await api("projects")).items.filter((p) => !p.archived);
  const sh = openSheet(html`${sheetHead("Treffer einem Projekt zuordnen")}
    <p class="small muted">Alle Buchungen, die zur Suche und den Filtern passen, kommen in das Projekt. Umbuchungen bleiben außen vor. Was schon in einem anderen Projekt liegt, wechselt.</p>
    ${list.length ? html`<ul class="list">${list.map((p) => html`<li><button class="row" data-pick="${p.id}"><span class="title">${p.name}</span><span class="sub">${p.count} ${p.count === 1 ? "Buchung" : "Buchungen"}</span><span class="amount">${money(p.cost_cents)}</span></button></li>`)}</ul>` : ""}
    <div class="actions"><button class="btn ${list.length ? "" : "primary"}" id="pick-new">Neues Projekt</button><button class="btn" data-close>Abbrechen</button></div>`.s);
  const take = async (id) => {
    try {
      const r = await api(`projects/${id}/assign`, { method: "POST", body: { filter } });
      sh.close(); toast(r.assigned ? `${r.assigned} ${r.assigned === 1 ? "Buchung" : "Buchungen"} zugeordnet` : "Alle Treffer waren schon im Projekt"); rerender();
    } catch (err) { toast(err.message, { error: true }); }
  };
  on(sh.el, "[data-pick]", "click", (_e, el) => take(Number(el.dataset.pick)));
  $("#pick-new", sh.el).onclick = () => { sh.close(); projectEditSheet(null, (saved) => take(saved.id)); };
}
