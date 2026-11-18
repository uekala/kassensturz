// Kassensturz – Oberfläche, umsaetze. Aufgeteilt aus app.js; Exporte und Importe zwischen den Modulen.

import { $, $$, D, ICON, NF, NF0, api, catName, childCats, dFull, fmtDay, fmtMonth, html, money, on, openSheet, parseMoney, raw, sheetHead, store, toInput, toast, topCats } from "./core.js";
import { pickImportFile } from "./import.js";
import { projectPickSheet } from "./projekte.js";
import { renderSeq, rerender } from "./router.js";
import { expectedNewSheet } from "./uebersicht.js";
import { contractSheet } from "./vertraege.js";

/* ------------------------------------------------------------------ Umsätze */
export const txState = { offset: 0, items: [] };
export const TX_FILTERS = ["q", "account", "category", "month", "kind", "contract", "project"];
export async function renderTransactions(view, params, seq) {
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
    ${params.project ? html`<p class="small" id="tx-project-note">Gefiltert nach Projekt. <a href="#/umsaetze">Filter entfernen</a></p>` : ""}
    <p class="small muted"><span id="tx-summary"></span> <button class="link-btn" id="tx-to-project" hidden>Alle Treffer einem Projekt zuordnen</button></p>
    <p class="small" id="tx-triage" hidden><button class="link-btn" id="tx-triage-go"></button></p>
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
  $("#tx-to-project").onclick = () => projectPickSheet(params);
  $("#tx-triage-go").onclick = () => triageSheet();
  api("triage?limit=1").then((d) => {
    if (seq !== undefined && seq !== renderSeq || !$("#tx-triage") || !d.total) return;
    $("#tx-triage-go").textContent = `${d.total} ${d.total === 1 ? "Buchung" : "Buchungen"} ohne Kategorie der Reihe nach zuordnen`;
    $("#tx-triage").hidden = false;
  }).catch(() => {});
  if (params.project) api("projects/" + params.project).then((p) => { const n = $("#tx-project-note"); if (n) n.firstChild.textContent = `Projekt „${p.name}“. `; }).catch(() => {});
  await loadTx(params, true, seq);
}
export async function loadTx(params, reset, seq) {
  if (reset) { txState.offset = 0; txState.items = []; }
  const q = new URLSearchParams({ offset: txState.offset, limit: 100 });
  TX_FILTERS.forEach((k) => { if (params[k]) q.set(k, params[k]); });
  const res = await api("transactions?" + q);
  if (seq && seq !== renderSeq) return;
  txState.items.push(...res.items);
  txState.offset += res.items.length;
  $("#tx-summary").textContent = `${res.total} Buchungen. Einnahmen ${money(res.sum_in, { plus: true })}, Ausgaben ${money(res.sum_out)}.`;
  $("#tx-more-wrap").hidden = txState.offset >= res.total;
  // Nur mit Suche oder Filter, sonst wären es alle Buchungen. Umbuchungen bleiben außen vor.
  $("#tx-to-project").hidden = !res.total || params.kind === "transfer" || !TX_FILTERS.some((k) => k !== "project" && params[k]);
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
// Zuordnen im Stapel: eine Buchung nach der anderen, die größten zuerst.
export async function triageSheet() {
  const skipped = new Set();
  let done = 0, sh = null, closed = false;
  const finish = () => { closed = true; if (done) rerender(); };
  const show = async () => {
    let data;
    try { data = await api("triage?limit=100"); } catch (e) { toast(e.message); return; }
    if (closed) return;
    const t = data.items.find((i) => !skipped.has(i.id));
    const body = !t
      ? html`<p>${data.total ? `Übersprungen: ${data.total}. Der Rest ist zugeordnet.` : "Alles zugeordnet."}</p>
          <div class="actions"><button class="btn primary" data-close>Fertig</button></div>`.s
      : html`<p class="small muted">Noch ${data.total} ${data.total === 1 ? "Buchung" : "Buchungen"} ohne Kategorie${data.expense_cents ? `, zusammen ${money(data.expense_cents)} Ausgaben` : ""}. Die größten zuerst.</p>
          <ul class="list"><li class="row static"><span class="title">${t.counterparty || t.purpose || "Ohne Bezeichnung"}</span>
            <span class="sub">${[dFull(t.booking_date), store.accounts.length > 1 ? t.account_name : null, t.counterparty ? t.purpose : null].filter(Boolean).join(", ")}</span>
            <span class="amount ${t.amount_cents > 0 ? "pos" : ""}">${money(t.amount_cents, { plus: true })}</span></li></ul>
          <div class="actions">${t.suggestion ? html`<button class="btn primary" id="tr-hint">${t.suggestion.name}</button>` : ""}<button class="btn" id="tr-skip">Überspringen</button></div>
          ${t.suggestion ? html`<p class="small muted">Vorschlag aus ähnlichen Buchungen. Oder wähle selbst:</p>` : ""}
          ${categoryPicker(null, t.amount_cents)}`.s;
    if (!sh) sh = openSheet(html`${sheetHead("Zuordnen")}<div id="tr-body"></div>`.s, { onClose: finish });
    const box = document.createElement("div");
    box.id = "tr-body";
    box.innerHTML = body;
    $("#tr-body", sh.el).replaceWith(box);
    on(box, "[data-close]", "click", () => sh.close());
    if (!t) return;
    const pick = async (id) => {
      let r;
      try { r = await api(`transactions/${t.id}`, { method: "PATCH", body: { category_id: id } }); } catch (e) { toast(e.message); return; }
      done += 1;
      if (r.recategorized) toast(`${r.recategorized} weitere Buchungen gleich mit zugeordnet`);
      show();
    };
    if ($("#tr-hint", box)) $("#tr-hint", box).onclick = () => pick(t.suggestion.id);
    $("#tr-skip", box).onclick = () => { skipped.add(t.id); show(); };
    bindCategoryPicker(box, pick);
  };
  await show();
}

export function txRow(t) {
  const name = t.counterparty || t.purpose || t.booking_text || "Ohne Bezeichnung";
  const cat = t.splits && t.splits.length ? "Aufgeteilt" : (t.is_transfer ? "Umbuchung" : t.category_name || "Ohne Kategorie");
  const sub = [cat, store.accounts.length > 1 ? t.account_name : null, t.note].filter(Boolean).join(", ");
  return html`<li><button class="row" data-tx="${t.id}"><span class="title">${name}</span><span class="sub">${sub}</span>
    <span class="amount ${t.amount_cents > 0 && !t.is_transfer ? "pos" : ""} ${t.is_transfer ? "muted" : ""}">${money(t.amount_cents, { plus: true })}</span></button></li>`;
}

export function categoryPicker(selectedId, amount) {
  const prefer = amount > 0 ? "income" : "expense";
  const tops = topCats().slice().sort((a, b) => (a.kind === prefer ? -1 : 0) - (b.kind === prefer ? -1 : 0));
  return html`<input class="input" id="cat-filter" placeholder="Kategorie suchen" style="width:100%;margin-top:8px" aria-label="Kategorie suchen">
    <div class="cat-list" id="cat-list">${tops.map((c) => html`
      <button class="parent" data-cat="${c.id}" aria-pressed="${c.id === selectedId}">${c.name}</button>
      ${childCats(c.id).map((ch) => html`<button class="child" data-cat="${ch.id}" aria-pressed="${ch.id === selectedId}">${ch.name}</button>`)}`)}</div>`;
}
export function bindCategoryPicker(root, onPick) {
  on(root, "#cat-list [data-cat]", "click", (_e, el) => {
    $$("#cat-list [data-cat]", root).forEach((b) => b.setAttribute("aria-pressed", b === el));
    onPick(Number(el.dataset.cat));
  });
  $("#cat-filter", root).addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    $$("#cat-list [data-cat]", root).forEach((b) => { b.hidden = q && !b.textContent.toLowerCase().includes(q); });
  });
}

// Eine Ausgabe vom eigenen Konto mit dem Haushalt teilen: Die anderen schulden dem Zahler ihren Teil.
export async function drawShare(box, txId) {
  let share;
  try { share = await api(`transactions/${txId}/share`); } catch { return; }
  if (!box.isConnected || !share.shareable) return;
  box.innerHTML = html`<h3>Haushalt</h3>
    ${share.shared ? html`<p class="small">Geteilt, bezahlt von ${share.payer}: ${share.parts.map((p) => `${p.name} ${money(p.cents)}`).join(", ")}.</p>
      <div class="actions" style="margin-top:0"><button class="btn small" type="button" id="share-off">Nicht mehr teilen</button></div>`
      : html`<p class="small muted">${share.payer} hat das vom eigenen Konto bezahlt. Teilst du die Ausgabe, schulden die anderen ${share.payer} ihren Anteil.</p>
      <div class="actions" style="margin-top:0"><button class="btn small" type="button" id="share-on">Mit dem Haushalt teilen</button></div>`}`.s;
  const change = async (method) => {
    try { await api(`transactions/${txId}/share`, { method, body: method === "PUT" ? {} : undefined }); toast(method === "PUT" ? "Ausgabe geteilt" : "Teilen zurückgenommen"); }
    catch (e) { toast(e.message); }
    drawShare(box, txId);
  };
  if ($("#share-on", box)) $("#share-on", box).onclick = () => change("PUT");
  if ($("#share-off", box)) $("#share-off", box).onclick = () => change("DELETE");
}

export async function txSheet(t) {
  const name = t.counterparty || t.purpose || "Buchung";
  const projects = (await api("projects")).items.filter((p) => !p.archived || p.id === t.project_id);
  const rule = t.rule_ref || "";
  const how = rule === "finanzguru" ? "aus Finanzguru übernommen" : t.category_locked ? "von dir gesetzt" : rule.startsWith("user:") ? "durch deine Regel" : rule === "learned" ? "aus deiner Korrektur gelernt" : rule.startsWith("builtin") ? "automatisch erkannt"
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
    ${projects.length && !t.is_transfer ? html`<label class="field"><span>Projekt</span><select class="input" id="tx-project">
      <option value="">Keines</option>${projects.map((p) => html`<option value="${p.id}" ${p.id === t.project_id ? raw("selected") : ""}>${p.name}</option>`)}</select></label>` : ""}
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
    <div id="tx-share"></div>
    <div class="actions">
      <button class="btn primary" id="tx-save">Speichern</button>
      <button class="btn" id="tx-split">Aufteilen</button>
      ${t.amount_cents < 0 && !t.is_transfer ? html`<button class="btn" id="tx-expect">Geld kommt zurück</button>` : ""}
      ${t.category_locked ? html`<button class="btn" id="tx-reset">Automatisch zuordnen</button>` : ""}
    </div>`.s);
  let picked = null;
  if (store.persons.length > 1) drawShare($("#tx-share", sh.el), t.id);
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
    if ($("#tx-project", sh.el) && Number($("#tx-project", sh.el).value || 0) !== (t.project_id || 0)) body.project_id = Number($("#tx-project", sh.el).value) || null;
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
  if ($("#tx-expect", sh.el)) $("#tx-expect", sh.el).onclick = () => { sh.close(); expectedNewSheet(t); };
  if ($("#tx-reset", sh.el)) $("#tx-reset", sh.el).onclick = async () => { await api(`transactions/${t.id}/reset`, { method: "POST" }); sh.close(); toast("Wieder automatisch zugeordnet"); rerender(); };
  if ($("#tx-contract", sh.el)) $("#tx-contract", sh.el).onclick = async () => {
    const list = await api("contracts");
    const c = list.items.find((x) => x.key === t.contract_key);
    sh.close();
    if (c) contractSheet(c);
  };
}

export const TAX_KINDS = [["handwerker", "Handwerkerleistung"], ["haushaltsnah", "Haushaltsnahe Dienstleistung"],
  ["arbeitsmittel", "Arbeitsmittel und Werbungskosten"], ["spende", "Spende"], ["versicherung", "Versicherung und Vorsorge"],
  ["gesundheit", "Krankheitskosten"], ["kinder", "Kinderbetreuung"], ["sonstiges", "Sonstiges"]];

export function fileSize(bytes) {
  return bytes >= 1048576 ? NF.format(bytes / 1048576).replace(/\d$/, "") + " MB" : NF0.format(Math.max(1, bytes / 1024)) + " KB";
}

// Belege einer Buchung: anzeigen, hochladen, entfernen. Wirkt sofort, ohne „Speichern“.
export async function bindReceipts(box, txId) {
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

export async function drawHealth(box) {
  let h;
  try { h = await api("health"); } catch { return; }
  const b = h.backups;
  const age = b.newest == null ? "noch keine" : b.age_days === 0 ? "von heute" : b.age_days === 1 ? "von gestern" : `${b.age_days} Tage alt`;
  const line = (title, sub, value, warn) => html`<li class="row static">
    <span class="title">${title}</span><span class="sub">${sub}</span>
    <span class="amount ${warn ? "neg" : ""}">${value}</span></li>`;
  box.innerHTML = html`<ul class="list">
    ${line("Datenbank", `${NF0.format(h.transactions)} Buchungen auf ${h.accounts} ${h.accounts === 1 ? "Konto" : "Konten"}, ${fileSize(h.database_bytes)}`, h.integrity_ok ? "in Ordnung" : "beschädigt", !h.integrity_ok)}
    ${line("Sicherungskopien", `${b.count} auf diesem Gerät, die jüngste ${age}`, b.stale ? "veraltet" : "aktuell", b.stale)}
    ${h.receipts.count ? line("Belege", `${h.receipts.count} ${h.receipts.count === 1 ? "Datei" : "Dateien"}, ${fileSize(h.receipts.bytes)}`, h.receipts.missing ? `${h.receipts.missing} fehlen` : "vollständig", h.receipts.missing > 0) : ""}
    ${h.newer_schema ? line("Version der Daten", "stammen von einer neueren Version von Kassensturz", "App aktualisieren", true) : ""}
  </ul>
  <div class="actions"><button class="btn small" id="health-check">Jüngste Sicherung prüfen</button></div>
  <p class="small muted" id="health-result">Die Prüfung öffnet die jüngste Kopie und kontrolliert sie vollständig, ohne etwas zu ändern.</p>`.s;
  $("#health-check", box).onclick = async () => {
    const out = $("#health-result", box);
    out.textContent = "Wird geprüft …";
    let r;
    try { r = await api("health/backup-check", { method: "POST" }); } catch (e) { out.textContent = e.message; return; }
    if (!r.found) { out.textContent = "Es gibt noch keine Sicherungskopie. Die erste entsteht innerhalb eines Tages von selbst."; return; }
    out.textContent = r.ok
      ? `${r.name} ist in Ordnung: ${NF0.format(r.transactions)} Buchungen auf ${r.accounts} ${r.accounts === 1 ? "Konto" : "Konten"}${r.newest_booking ? `, jüngste Buchung vom ${dFull(r.newest_booking)}` : ""}. Aktuell sind es ${NF0.format(r.live_transactions)} Buchungen.`
      : `${r.name} ist nicht brauchbar: ${r.integrity}`;
  };
}

export async function drawWarranties(box) {
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

export async function drawTax(box, year) {
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

export function splitSheet(t) {
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
