// Kassensturz – Oberfläche, uebersicht. Aufgeteilt aus app.js; Exporte und Importe zwischen den Modulen.

import { affordHtml, budgetSheet } from "./budgets.js";
import { $, D, ICON, NF0, VALUE_KINDS, api, dFull, dShort, esc, fmtMonth, fmtShort, html, money, moneyRound, on, openSheet, parseMoney, raw, relDay, sheetHead, store, toInput, toast, todayIso } from "./core.js";
import { balanceSheet, ebConnectSheet } from "./konten.js";
import { go, renderSeq, rerender } from "./router.js";
import { contractSheet } from "./vertraege.js";

/* ------------------------------------------------------------------ Übersicht */
const KWH1 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const perKwh = (cents) => (cents == null ? "–" : `${money(Math.round(cents))}/kWh`);

// Laden mit Ladecockpit: dieser Monat im Vergleich zum vorigen
function chargingSection(ch) {
  const now = todayIso().slice(0, 7);
  const cur = ch.months.find((m) => m.month === now);
  const prev = ch.months.find((m) => m.month < now);
  const line = (m) => `${m.sessions} ${m.sessions === 1 ? "Ladevorgang" : "Ladevorgänge"}, ${KWH1.format(m.kwh)} kWh, ${money(m.total_cents)}, ${perKwh(m.price_per_kwh_cents)}`;
  return html`<section class="section">
    <div class="section-head"><h2>Laden</h2><button class="link-btn" id="ch-all">Alle Monate</button></div>
    <p>${cur ? html`Diesen Monat: ${line(cur)}.` : "Diesen Monat noch nicht geladen."}</p>
    ${prev ? html`<p class="small muted">${fmtMonth.format(D(prev.month + "-01"))}: ${line(prev)}.</p>` : ""}
    ${ch.unlinked_count ? html`<p class="small muted">${ch.unlinked_count} ${ch.unlinked_count === 1 ? "Ladevorgang hat" : "Ladevorgänge haben"} noch keine passende Abbuchung.</p>` : ""}
  </section>`;
}

function chargingSheet(ch) {
  openSheet(html`${sheetHead("Laden mit Ladecockpit")}
    <ul class="list">${ch.months.map((m) => html`<li class="row static"><span class="title">${fmtMonth.format(D(m.month + "-01"))}</span>
      <span class="sub">${m.sessions} × geladen, ${KWH1.format(m.kwh)} kWh, ${perKwh(m.price_per_kwh_cents)}${m.idle_cents ? `, Blockiergebühr ${money(m.idle_cents)}` : ""}</span>
      <span class="amount">${money(-m.total_cents)}</span></li>`)}</ul>
    ${ch.unlinked.length ? html`<h3>Noch ohne Abbuchung</h3>
      <p class="small muted">Gesucht wird eine Buchung mit genau diesem Betrag, einen Tag vor bis sieben Tage nach dem Laden. Rechnet die Bank mehrere Ladevorgänge zusammen ab, passt keine.</p>
      <ul class="list">${ch.unlinked.map((c) => html`<li class="row static"><span class="title">${c.site || "Ladevorgang"}</span>
        <span class="sub">${dFull(c.started.slice(0, 10))}, ${KWH1.format(c.kwh)} kWh</span><span class="amount">${money(-c.total_cents)}</span></li>`)}</ul>` : ""}
    <p class="small muted">Neue Ladevorgänge liest Kassensturz aus dem Sensor von Ladecockpit. Ältere kommen über den Export „Ladevorgänge als CSV“ aus Ladecockpit, importiert unter <i>Konten → Datei importieren</i>.</p>
    <div class="actions"><button class="btn" data-close>Schließen</button></div>`.s);
}

export async function renderOverview(view, _params, seq) {
  const [o, ch] = await Promise.all([api("overview"), api("charging").catch(() => null)]);
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
            ${fc.planned_out_cents ? html`<li><span class="op">−</span><span>geplante Ausgaben bis ${dShort(fc.period_end)}</span><span class="amount">${money(Math.abs(fc.planned_out_cents))}</span></li>` : ""}
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
          <div class="section-head"><h2>Geplante Ausgaben</h2><button class="link-btn" id="plan-add">Hinzufügen</button></div>
          ${o.planned.open.length ? html`<ul class="list">${o.planned.open.map((p) => html`<li><button class="row" data-plan="${p.id}">
              <span class="title">${p.label}${p.overdue ? html` <span class="chip warn">noch offen</span>` : ""}</span>
              <span class="sub">${p.overdue ? `war für ${dShort(p.due_date)} geplant` : relDay(p.due_date)}, ${p.account}${p.in_forecast ? "" : ", zählt nicht in der Prognose"}${p.candidates.length ? ". Schon bezahlt?" : ""}</span>
              <span class="amount">${money(-p.cents)}</span></button></li>`)}</ul>
            ${o.planned.open.length > 1 ? html`<p class="small muted">Zusammen stehen ${money(o.planned.open_cents)} an.</p>` : ""}`
            : html`<p class="muted">Nichts geplant. Steht eine größere Ausgabe an, etwa eine Rechnung oder eine Anschaffung, trag sie ein: Sie zählt dann in der Prognose mit.</p>`}
        </section>
        <section class="section">
          <div class="section-head"><h2>Erwartete Eingänge</h2><button class="link-btn" id="exp-add">Hinzufügen</button></div>
          ${o.expected.open.length ? html`<ul class="list">${o.expected.open.map((e) => html`<li><button class="row" data-exp="${e.id}">
              <span class="title">${e.label}${e.overdue ? html` <span class="chip warn">steht aus</span>` : ""}</span>
              <span class="sub">seit ${dShort(e.since)}, ${e.account}${e.candidates.length ? ". Eingang gefunden?" : ""}</span>
              <span class="amount pos">${money(e.cents, { plus: true })}</span></button></li>`)}</ul>
            ${o.expected.open.length > 1 ? html`<p class="small muted">Zusammen stehen ${money(o.expected.open_cents)} aus.</p>` : ""}`
            : html`<p class="muted">Nichts offen. Kommt Geld zurück, etwa nach einer Retoure, merk es an der Ausgabe an.</p>`}
        </section>
        <section class="section">
          <div class="section-head"><h2>Budgets im ${fmtMonth.format(new Date()).split(" ")[0]}</h2><a href="#/budgets">Alle Budgets</a></div>
          ${o.budgets.length ? html`<div>${budgets}</div>` : html`<p class="muted">Noch keine Budgets. <a href="#/budgets">Budget festlegen</a></p>`}
        </section>
        ${ch && ch.count ? chargingSection(ch) : ""}
        <section class="section">
          <div class="section-head"><h2>Konten</h2><a href="#/konten">Verwalten</a></div>
          <div class="accounts-strip">${accounts}</div>
          <p class="small muted" style="margin-top:12px">Diesen Monat: Einnahmen <span class="num pos">${money(o.month.income_cents, { plus: true })}</span>,
            Ausgaben <span class="num">${money(-o.month.expense_cents)}</span>. Fixkosten insgesamt ${money(o.fixed_monthly_cents)} im Monat.</p>
        </section>
      </div>
    </div>`.s;
  forecastChart($("#fc-chart"), fc);
  if ($("#ch-all")) $("#ch-all").onclick = () => chargingSheet(ch);
  $("#afford-form").onsubmit = async (e) => {
    e.preventDefault();
    const cents = parseMoney($("#afford-amt").value);
    if (cents === null || cents === 0) { toast("Bitte einen Betrag eintragen"); return; }
    try { $("#afford-out").innerHTML = affordHtml(await api("afford?amount_cents=" + Math.abs(cents)), true); } catch (err) { toast(err.message); }
  };
  on(view, "[data-acc]", "click", (_e, el) => go("umsaetze", { account: el.dataset.acc }));
  on(view, "[data-alert]", "click", async (_e, el) => {
    const d = JSON.parse(el.dataset.alert);
    const found = o.alerts.find((x) => x.key === d.k);
    const waiting = found && found.expected ? o.expected.open.find((x) => x.id === found.expected) : null;
    const due = found && found.planned ? o.planned.open.find((x) => x.id === found.planned) : null;
    if (found && found.anomaly) anomalySheet(found);
    else if (due) plannedSheet(due);
    else if (waiting) expectedSheet(waiting);
    else if (d.c) { const list = await api("contracts"); const c = list.items.find((x) => x.key === d.c); if (c) contractSheet(c); }
    else if (d.a) { const acc = store.accounts.find((x) => x.id === d.a); if (acc) balanceSheet(acc); }
    else if (d.e) { const eb = await api("eb"); const s = eb.sessions.find((x) => x.id === d.e); if (s) ebConnectSheet(s); }
    else if (d.i) go("konten");
    else if (d.k.startsWith("budget")) go("budgets");
  });
  $("#plan-add").onclick = () => plannedEditSheet(null);
  on(view, "[data-plan]", "click", (_e, el) => plannedSheet(o.planned.open.find((x) => x.id === Number(el.dataset.plan))));
  // Der Knopf entsteht erst mit dem Ergebnis, darum hört der Rahmen zu.
  $("#afford-out").addEventListener("click", (e) => {
    const el = e.target.closest("[data-plan-cents]");
    if (el) plannedEditSheet(null, Number(el.dataset.planCents));
  });
  $("#exp-add").onclick = () => expectedNewSheet(null);
  on(view, "[data-exp]", "click", (_e, el) => expectedSheet(o.expected.open.find((x) => x.id === Number(el.dataset.exp))));
  bindBudgetRows(view);
}

// Ein erwarteter Eingang: was aussteht, welcher Eingang es sein könnte, und das Abhaken von Hand.
export function expectedSheet(e) {
  const sh = openSheet(html`${sheetHead(e.label)}
    <div class="big-amount pos">${money(e.cents, { plus: true })}</div>
    <dl class="facts">
      <dt>Offen seit</dt><dd>${dFull(e.since)}</dd>
      <dt>Konto</dt><dd>${e.account}</dd>
      ${e.due_date ? html`<dt>Erinnerung ab</dt><dd>${dFull(e.due_date)}</dd>` : ""}
      ${e.note ? html`<dt>Notiz</dt><dd>${e.note}</dd>` : ""}
    </dl>
    ${e.candidates.length ? html`<h3>Ist es einer dieser Eingänge?</h3>
      <ul class="list">${e.candidates.map((c) => html`<li><button class="row" data-exp-take="${c.tx_id}">
        <span class="title">${c.counterparty || "Eingang"}</span><span class="sub">${dFull(c.booking_date)}</span>
        <span class="amount pos">${money(c.amount_cents, { plus: true })}</span></button></li>`)}</ul>` : ""}
    <div class="actions"><button class="btn primary" id="exp-done">${e.candidates.length ? "Anders angekommen" : "Ist angekommen"}</button><button class="btn" id="exp-drop">Kommt nicht mehr</button></div>`.s);
  const act = async (path, body, text) => {
    try { await api(`expected/${e.id}/${path}`, { method: "POST", body: body || {} }); sh.close(); toast(text); rerender(); }
    catch (err) { toast(err.message); }
  };
  on(sh.el, "[data-exp-take]", "click", (_e, el) => act("received", { tx_id: Number(el.dataset.expTake) }, "Abgehakt"));
  $("#exp-done", sh.el).onclick = () => act("received", {}, "Abgehakt");
  $("#exp-drop", sh.el).onclick = () => act("drop", null, "Abgelegt");
}

// Legt einen erwarteten Eingang an: zu einer Ausgabe (t) oder für sich allein.
export function expectedNewSheet(t) {
  const accs = store.accounts.filter((a) => !a.archived && !VALUE_KINDS.has(a.kind) && a.kind !== "taschengeld");
  const due = new Date(Date.now() + 21 * 86400000 - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  const sh = openSheet(html`${sheetHead(t ? "Geld kommt zurück" : "Erwarteter Eingang")}
    ${t ? html`<p class="small muted">${t.counterparty || t.purpose || "Ausgabe"} vom ${dFull(t.booking_date)}, ${money(t.amount_cents)}. Geht derselbe Betrag vom selben Absender auf diesem Konto ein, hakt Kassensturz ihn von selbst ab.</p>`
      : html`<label class="field"><span>Wofür kommt das Geld?</span><input class="input" id="exp-label" maxlength="80" placeholder="z. B. Auslagen Dienstreise" autofocus></label>`}
    <div class="field-row">
      <label class="field"><span>Betrag in Euro</span><input class="input" id="exp-amt" inputmode="decimal" value="${t ? toInput(-t.amount_cents) : ""}"></label>
      <label class="field"><span>Erinnern ab</span><input class="input" id="exp-due" type="date" value="${due}"></label>
    </div>
    ${t ? "" : html`<label class="field"><span>Auf welchem Konto kommt es an?</span><select class="input" id="exp-acc">${accs.map((a) => html`<option value="${a.id}">${a.name}</option>`)}</select></label>`}
    <label class="field"><span>Notiz</span><input class="input" id="exp-note" maxlength="200"></label>
    <div class="actions"><button class="btn primary" id="exp-save">Merken</button><button class="btn" data-close>Abbrechen</button></div>`.s);
  $("#exp-save", sh.el).onclick = async () => {
    const cents = parseMoney($("#exp-amt", sh.el).value);
    if (!cents || cents < 0) { toast("Bitte einen Betrag eintragen"); return; }
    const body = { cents, due_date: $("#exp-due", sh.el).value || null, note: $("#exp-note", sh.el).value };
    if (t) body.tx_id = t.id;
    else { body.label = $("#exp-label", sh.el).value; body.account_id = Number($("#exp-acc", sh.el).value); }
    try { await api("expected", { method: "POST", body }); sh.close(); toast("Gemerkt. Bleibt offen, bis das Geld da ist"); rerender(); }
    catch (err) { toast(err.message); }
  };
}

// Eine geplante Ausgabe: wann sie ansteht, welche Abbuchung es sein könnte, und das Abhaken von Hand.
export function plannedSheet(p) {
  const sh = openSheet(html`${sheetHead(p.label)}
    <div class="big-amount">${money(-p.cents)}</div>
    <dl class="facts">
      <dt>Geplant für</dt><dd>${dFull(p.due_date)}${p.overdue ? ", noch offen" : ""}</dd>
      <dt>Konto</dt><dd>${p.account}</dd>
      ${p.note ? html`<dt>Notiz</dt><dd>${p.note}</dd>` : ""}
    </dl>
    <p class="small muted">${p.in_forecast ? "Zählt in der Prognose mit, bis sie bezahlt ist oder entfällt." : "Dieses Konto zählt nicht in der Prognose, die Ausgabe darum auch nicht."}</p>
    ${p.candidates.length ? html`<h3>Ist es eine dieser Abbuchungen?</h3>
      <ul class="list">${p.candidates.map((c) => html`<li><button class="row" data-plan-take="${c.tx_id}">
        <span class="title">${c.counterparty || "Abbuchung"}</span><span class="sub">${dFull(c.booking_date)}</span>
        <span class="amount">${money(c.amount_cents)}</span></button></li>`)}</ul>` : ""}
    <div class="actions"><button class="btn primary" id="plan-done">${p.candidates.length ? "Anders bezahlt" : "Ist bezahlt"}</button><button class="btn" id="plan-edit">Ändern</button><button class="btn" id="plan-drop">Entfällt</button></div>`.s);
  const act = async (path, body, text) => {
    try { await api(`planned/${p.id}/${path}`, { method: "POST", body: body || {} }); sh.close(); toast(text); rerender(); }
    catch (err) { toast(err.message); }
  };
  on(sh.el, "[data-plan-take]", "click", (_e, el) => act("paid", { tx_id: Number(el.dataset.planTake) }, "Abgehakt"));
  $("#plan-done", sh.el).onclick = () => act("paid", {}, "Abgehakt");
  $("#plan-drop", sh.el).onclick = () => act("drop", null, "Gestrichen");
  $("#plan-edit", sh.el).onclick = () => { sh.close(); plannedEditSheet(p); };
}

// Legt eine geplante Ausgabe an (p leer, Betrag optional vorbelegt) oder ändert eine offene.
export function plannedEditSheet(p, cents) {
  const accs = store.accounts.filter((a) => !a.archived && !VALUE_KINDS.has(a.kind) && a.kind !== "taschengeld");
  const first = (accs.find((a) => a.in_forecast) || accs[0] || {}).id;
  const sh = openSheet(html`${sheetHead(p ? "Geplante Ausgabe ändern" : "Geplante Ausgabe")}
    <label class="field"><span>Wofür?</span><input class="input" id="plan-label" maxlength="80" placeholder="z. B. Handwerkerrechnung" value="${p ? p.label : ""}" autofocus></label>
    <div class="field-row">
      <label class="field"><span>Betrag in Euro</span><input class="input" id="plan-amt" inputmode="decimal" value="${p ? toInput(p.cents) : cents ? toInput(cents) : ""}"></label>
      <label class="field"><span>Wann?</span><input class="input" id="plan-due" type="date" min="${todayIso()}" value="${p ? p.due_date : ""}"></label>
    </div>
    <label class="field"><span>Von welchem Konto?</span><select class="input" id="plan-acc">${accs.map((a) => html`<option value="${a.id}" ${(p ? p.account_id : first) === a.id ? "selected" : ""}>${a.name}</option>`)}</select></label>
    <label class="field"><span>Notiz</span><input class="input" id="plan-note" maxlength="200" value="${p && p.note ? p.note : ""}"></label>
    <div class="actions"><button class="btn primary" id="plan-save">${p ? "Speichern" : "Einplanen"}</button><button class="btn" data-close>Abbrechen</button></div>`.s);
  $("#plan-save", sh.el).onclick = async () => {
    const amount = parseMoney($("#plan-amt", sh.el).value);
    if (!amount || amount < 0) { toast("Bitte einen Betrag eintragen"); return; }
    if (!$("#plan-due", sh.el).value) { toast("Bitte den Tag eintragen"); return; }
    const body = { label: $("#plan-label", sh.el).value, cents: amount, due_date: $("#plan-due", sh.el).value,
      account_id: Number($("#plan-acc", sh.el).value), note: $("#plan-note", sh.el).value };
    try { await api(p ? `planned/${p.id}` : "planned", { method: "POST", body }); sh.close(); toast(p ? "Gespeichert" : "Eingeplant. Zählt jetzt in der Prognose mit"); rerender(); }
    catch (err) { toast(err.message); }
  };
}

// Eine Auffälligkeit: was aufgefallen ist, und die Wahl, sie als geprüft auszublenden.
export function anomalySheet(a) {
  const n = a.anomaly;
  const sh = openSheet(html`${sheetHead(a.title)}
    <p>${a.text}</p>
    <dl class="facts">
      <dt>Empfänger</dt><dd>${n.counterparty || "Unbekannt"}</dd>
      <dt>Betrag</dt><dd>${money(n.amount_cents)}</dd>
      <dt>Gebucht</dt><dd>${dFull(n.booking_date)}${n.other_date ? `, davor am ${dFull(n.other_date)}` : ""}</dd>
      <dt>Konto</dt><dd>${n.account}</dd>
      ${n.creditor_id ? html`<dt>Gläubiger-ID</dt><dd>${n.creditor_id}${n.mandate_ref ? `, Mandat ${n.mandate_ref}` : ""}</dd>` : ""}
      ${n.return_until ? html`<dt>Rückgabe bis</dt><dd>${dFull(n.return_until)}</dd>` : ""}
      ${n.usual_max_cents ? html`<dt>Bisher höchstens</dt><dd>${money(-n.usual_max_cents)}</dd>` : ""}
    </dl>
    <p class="small muted">Der Hinweis verschwindet nach zwei Wochen von selbst.</p>
    <div class="actions"><button class="btn primary" id="an-ok">Passt, ausblenden</button><button class="btn" id="an-show">Umsätze ansehen</button></div>`.s);
  $("#an-ok", sh.el).onclick = async () => {
    try { await api("anomalies/ack", { method: "POST", body: { key: a.key } }); sh.close(); toast("Hinweis ausgeblendet"); rerender(); }
    catch (e) { toast(e.message); }
  };
  $("#an-show", sh.el).onclick = () => { sh.close(); go("umsaetze", { q: n.counterparty || "" }); };
}

// Mit person sind es deren eigene Budgets; limits sind dann ihre Beträge je Kategorie.
export function bindBudgetRows(view, person, limits) {
  on(view, "[data-budget]", "click", (_e, el) => budgetSheet(Number(el.dataset.budget), person, limits));
  on(view, "[data-budget]", "keydown", (e, el) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); budgetSheet(Number(el.dataset.budget), person, limits); } });
}

export function budgetRow(b) {
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
export function forecastChart(el, fc) {
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
export function niceStep(raw_) {
  const mag = Math.pow(10, Math.floor(Math.log10(Math.max(1, raw_))));
  const n = raw_ / mag;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
}
