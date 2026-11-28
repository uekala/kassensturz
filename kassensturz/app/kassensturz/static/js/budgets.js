// Kassensturz – Oberfläche, budgets. Aufgeteilt aus app.js; Exporte und Importe zwischen den Modulen.

import { $, $$, D, api, childCats, confirmButton, dFull, dShort, esc, fmtMonth, html, money, moneyRound, on, openSheet, parseMoney, personName, raw, sheetHead, store, toInput, toast, todayIso } from "./core.js";
import { projectEditSheet, projectSheet } from "./projekte.js";
import { go, renderSeq, rerender } from "./router.js";
import { bindBudgetRows, budgetRow, niceStep } from "./uebersicht.js";

/* ------------------------------------------------------------------ Budgets & Auswertung */
export function affordHtml(r, canPlan) {
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
    <p class="small">${lines.join(" ")}</p>
    ${canPlan ? html`<button class="link-btn" data-plan-cents="${r.amount_cents}">Als geplante Ausgabe vormerken</button>` : ""}</div></div>`.s;
}

export function reviewHtml(r) {
  if (!r || !r.has_data || !r.complete) return "";
  const lines = [];
  if (r.saved_cents > 0 && r.savings_rate !== null) lines.push(`Gespart ${money(r.saved_cents)}, Sparquote ${Math.round(r.savings_rate * 100)} %.`);
  else if (r.saved_cents < 0) lines.push(`${money(-r.saved_cents)} mehr ausgegeben als eingenommen.`);
  if (r.expense_change_cents !== null && Math.abs(r.expense_change_cents) >= 5000) lines.push(`Ausgaben ${money(Math.abs(r.expense_change_cents))} ${r.expense_change_cents > 0 ? "höher" : "niedriger"} als ${r.compared_months === 1 ? "im Vormonat" : `im Schnitt der letzten ${r.compared_months} Monate`}.`);
  if (r.notable.length) lines.push(`Auffällig: ${r.notable.join(", ")}.`);
  if (r.biggest_expense) lines.push(`Größte Einzelausgabe: ${r.biggest_expense.name}, ${money(-r.biggest_expense.amount_cents)}.`);
  return lines.length ? html`<p class="review">${lines.join(" ")}</p>`.s : "";
}

export async function renderBudgets(view, params, seq) {
  const month = params.month || todayIso().slice(0, 7);
  // Haushalt (gemeinsame Konten) oder die eigenen Budgets einer Person auf ihren eigenen Konten
  const person = store.persons.find((p) => String(p.id) === params.person) || null;
  const split = store.accounts.some((a) => a.owner_person_id);
  const [data, stats, plan, projects] = await Promise.all([api("budgets?month=" + month + (person ? "&person=" + person.id : "")), api("stats?month=" + month), api("goals"), api("projects")]);
  if (seq !== renderSeq) return;
  const here = (extra) => ({ month, ...(person ? { person: String(person.id) } : {}), ...extra });
  const [y, m] = month.split("-").map(Number);
  const prev = new Date(y, m - 2, 1), next = new Date(y, m, 1);
  const key = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  const isCurrent = month === todayIso().slice(0, 7);
  const st = data.stats;
  const maxCat = Math.max(1, ...st.breakdown.map((b) => b.cents));
  const withBudget = new Set(data.budgets.map((b) => b.category_id));
  // Vorschläge nur für die Budgets des Haushalts und nur im laufenden Monat
  const suggest = !person && isCurrent && data.suggestions ? data.suggestions.items : [];
  const takeSuggestions = async (items) => {
    try { for (const s of items) await api(`categories/${s.category_id}`, { method: "PATCH", body: { budget_cents: s.suggested_cents } }); }
    catch (e) { toast(e.message, { error: true }); rerender(); return; }
    toast(items.length === 1 ? "Budget gespeichert" : `${items.length} Budgets gespeichert`); rerender();
  };
  view.innerHTML = html`
    <div class="page-head"><h1>${fmtMonth.format(new Date(y, m - 1, 1))}</h1>
      <div class="segmented"><button id="b-prev"><span aria-hidden="true">‹ </span>${fmtMonth.format(prev).split(" ")[0]}<span class="sr-only"> (Vormonat)</span></button>
      ${!isCurrent ? html`<button id="b-next">${fmtMonth.format(next).split(" ")[0]}<span class="sr-only"> (Folgemonat)</span><span aria-hidden="true"> ›</span></button>` : ""}</div>
      <span><button class="link-btn" id="b-year">Jahresrückblick ${y}</button>
      <a class="link-btn" href="api/report/month.pdf?month=${month}" download style="margin-left:12px">Monatsbericht als PDF</a></span></div>
    <ul class="tally-lines" style="max-width:420px;font-size:1rem">
      <li><span class="op"></span><span>Einnahmen</span><span class="amount pos">${money(st.income_cents, { plus: true })}</span></li>
      <li><span class="op">−</span><span>Ausgaben</span><span class="amount">${money(st.expense_cents)}</span></li>
      <li class="tally-sum" style="font-weight:650"><span class="op">=</span><span>${st.saldo_cents >= 0 ? "Überschuss" : "Fehlbetrag"}</span><span class="amount">${money(st.saldo_cents)}</span></li>
    </ul>
    ${raw(reviewHtml(stats.review))}
    ${store.persons.length && (split || person) ? html`<div class="segmented" style="margin:14px 0 0"><button data-bperson="" ${person ? "" : raw('aria-pressed="true"')}>Haushalt</button>${store.persons.map((p) => html`<button data-bperson="${p.id}" ${person && person.id === p.id ? raw('aria-pressed="true"') : ""}>${p.name}</button>`)}</div>
      <p class="small muted" style="margin-top:6px">${person ? `Eigene Budgets von ${person.name}. Zahlen und Budgets zählen nur die eigenen Konten.` : "Budgets des Haushalts zählen die gemeinsamen Konten. Die Zahlen oben umfassen alle Konten."}</p>` : ""}
    <div class="cols"><div>
      <section class="section"><div class="section-head"><h2>${person ? `Budgets von ${person.name}` : "Budgets"}</h2><span class="small muted">Strich: so viel wäre bis heute im Plan</span></div>
        ${data.budgets.length ? html`<div>${data.budgets.map(budgetRow)}</div>` : html`<p class="muted">Tipp auf eine Kategorie rechts oder unten, um ein Monatsbudget festzulegen.</p>`}
      </section>
      ${suggest.length ? html`<section class="section"><div class="section-head"><h2>Vorschläge</h2>${suggest.length > 1 ? html`<button class="link-btn" id="bs-all">Alle übernehmen</button>` : ""}</div>
        <p class="small muted">Aus deinen Ausgaben ${data.suggestions.months === 1 ? "des letzten vollen Monats" : `der letzten ${data.suggestions.months} vollen Monate`}, je Monat und aufgerundet.</p>
        <ul class="list">${suggest.map((s) => html`<li class="row static"><span class="title">${s.name}</span>
          <span class="sub">Schnitt ${money(s.average_cents)}${s.current_cents ? `, bisher ${moneyRound(s.current_cents)}` : ""}</span>
          <span class="amount">${money(s.suggested_cents)}<small><button class="link-btn tiny" data-suggest="${s.category_id}">Übernehmen</button></small></span></li>`)}</ul>
      </section>` : ""}
      <section class="section"><div class="section-head"><h2>Sparziele</h2><button class="link-btn" id="g-add">Ziel hinzufügen</button></div>
        ${plan.goals.length ? html`<div>${plan.goals.map((g) => html`<button class="goal" data-goal="${g.id}">
          <span class="goal-head"><strong>${g.name}${g.owner_person_id ? html` <span class="chip neutral">${personName(g.owner_person_id)}</span>` : ""}</strong><span class="num">${money(g.saved_cents)} von ${money(g.target_cents)}</span></span>
          <span class="meter"><i style="width:${Math.round(g.progress * 100)}%"></i></span>
          <span class="small muted">${g.status === "done" ? "Erreicht" : g.status === "late" ? `Ziel war ${dFull(g.due_date)}, es fehlen ${money(g.rest_cents)}`
            : g.monthly_cents ? `${money(g.monthly_cents)} im Monat bis ${dFull(g.due_date)}` : `Es fehlen ${money(g.rest_cents)}`}${g.account_name ? ` · ${g.account_name}` : ""}</span></button>`)}</div>`
          : html`<p class="small muted">Noch keine Ziele. Lege fest, wofür du sparst, etwa einen Notgroschen oder einen Urlaub, und bis wann.</p>`}
      </section>
      <section class="section" id="sec-projekte" tabindex="-1"><div class="section-head"><h2>Projekte</h2><button class="link-btn" id="pr-add">Projekt anlegen</button></div>
        ${projects.items.length ? html`<ul class="list">${projects.items.map((p) => html`<li><button class="row" data-project="${p.id}">
          <span class="title">${p.name}${p.archived ? html` <span class="chip neutral">abgeschlossen</span>` : ""}</span>
          <span class="sub">${p.count ? `${p.count} ${p.count === 1 ? "Buchung" : "Buchungen"}, ${p.first === p.last ? dFull(p.first) : `${dShort(p.first)} bis ${dFull(p.last)}`}` : "Noch keine Buchungen"}${p.budget_cents ? (p.left_cents >= 0 ? `. Noch ${money(p.left_cents)} im Rahmen` : `. ${money(-p.left_cents)} über dem Rahmen`) : ""}</span>
          <span class="amount">${money(p.cost_cents)}</span></button></li>`)}</ul>`
          : html`<p class="small muted">Was hat der Urlaub, das Auto oder die Renovierung insgesamt gekostet? Ein Projekt sammelt Buchungen aus allen Kategorien und Monaten.</p>`}
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
  // Sprung von der Übersicht direkt zu den Projekten.
  if (params.focus === "projekte") { const sec = $("#sec-projekte", view); if (sec) { sec.scrollIntoView({ block: "start" }); sec.focus({ preventScroll: true }); } }
  $("#b-prev").onclick = () => go("budgets", here({ month: key(prev) }));
  on(view, "[data-bperson]", "click", (_e, el) => go("budgets", el.dataset.bperson ? { month, person: el.dataset.bperson } : { month }));
  $("#b-year").onclick = () => yearSheet(y);
  $("#g-add").onclick = () => goalSheet(null);
  $("#pr-add").onclick = () => projectEditSheet(null);
  on(view, "[data-project]", "click", (_e, el) => projectSheet(Number(el.dataset.project)));
  on(view, "[data-goal]", "click", (_e, el) => goalSheet(plan.goals.find((g) => String(g.id) === el.dataset.goal)));
  if ($("#b-next")) $("#b-next").onclick = () => go("budgets", here({ month: key(next) }));
  bindBudgetRows(view, person, data.limits);
  on(view, "[data-suggest]", "click", (_e, el) => takeSuggestions(suggest.filter((s) => String(s.category_id) === el.dataset.suggest)));
  if ($("#bs-all")) $("#bs-all").onclick = () => takeSuggestions(suggest);
  on(view, "[data-setbudget]", "click", (e, el) => { e.stopPropagation(); budgetSheet(Number(el.dataset.setbudget), person, data.limits); });
  on(view, ".bar-row[data-cat]", "click", (_e, el) => { if (el.dataset.cat) go("umsaetze", { category: el.dataset.cat, month, kind: "out" }); });
  historyChart($("#hist-chart"), stats.history);
}

function changeText(cents, prev) {
  if (prev === null || prev === undefined) return "";
  if (!prev) return cents ? "neu" : "";
  const pct = Math.round(((cents - prev) / prev) * 100);
  return pct === 0 ? "wie im Vorjahr" : `${pct > 0 ? "+" : "−"}${Math.abs(pct)} % zum Vorjahr`;
}

export async function yearSheet(year) {
  let r;
  try { r = await api("year?year=" + year); } catch (e) { toast(e.message, { error: true }); return; }
  const p = r.previous;
  const until = r.running ? ` bis ${dFull(r.until)}` : "";
  const lines = [];
  if (r.saved_cents > 0 && r.savings_rate !== null) lines.push(`Gespart ${money(r.saved_cents)}, Sparquote ${Math.round(r.savings_rate * 100)} %.`);
  else if (r.saved_cents < 0) lines.push(`${money(-r.saved_cents)} mehr ausgegeben als eingenommen.`);
  if (p) {
    const d = r.expense_cents - p.expense_cents;
    lines.push(Math.abs(d) < 5000 ? `Ausgaben etwa wie im Vorjahr${r.running ? " bis zum selben Tag" : ""}.`
      : `Ausgaben ${money(Math.abs(d))} ${d > 0 ? "höher" : "niedriger"} als im Vorjahr${r.running ? " bis zum selben Tag" : ""}.`);
  }
  if (r.expense_cents && r.fixed_cents) lines.push(`${Math.round((r.fixed_cents / r.expense_cents) * 100)} % der Ausgaben waren feste Zahlungen aus Verträgen.`);
  if (r.best_month && r.worst_month && r.best_month.month !== r.worst_month.month) lines.push(`Bester Monat: ${r.best_month.label} (${money(r.best_month.saldo_cents)}), schwächster: ${r.worst_month.label} (${money(r.worst_month.saldo_cents)}).`);
  const sh = openSheet(html`${sheetHead(`Jahresrückblick ${r.year}`)}
    ${r.years.length > 1 ? html`<div class="segmented" style="margin-bottom:12px">${r.years.map((yy) => html`<button data-year="${yy}" ${yy === r.year ? raw('aria-pressed="true"') : ""}>${yy}</button>`)}</div>` : ""}
    ${!r.has_data ? html`<p class="muted">Für ${r.year} gibt es keine Buchungen.</p>` : html`
    <ul class="tally-lines" style="max-width:460px">
      <li><span class="op"></span><span>Einnahmen${until}</span><span class="amount pos">${money(r.income_cents, { plus: true })}${p ? html`<small> Vorjahr ${moneyRound(p.income_cents)}</small>` : ""}</span></li>
      <li><span class="op">−</span><span>Ausgaben</span><span class="amount">${money(r.expense_cents)}${p ? html`<small> Vorjahr ${moneyRound(p.expense_cents)}</small>` : ""}</span></li>
      <li class="tally-sum" style="font-weight:650"><span class="op">=</span><span>${r.saved_cents >= 0 ? "Überschuss" : "Fehlbetrag"}</span><span class="amount">${money(r.saved_cents)}${p ? html`<small> Vorjahr ${moneyRound(p.saved_cents)}</small>` : ""}</span></li>
    </ul>
    ${lines.length ? html`<p class="review">${lines.join(" ")}</p>` : ""}
    <section class="section"><div class="section-head"><h2>Überschuss je Monat</h2></div><div class="chart" id="y-chart"></div></section>
    <section class="section"><div class="section-head"><h2>Wofür das Geld ging</h2>${p ? html`<span class="small muted">Vergleich mit dem Vorjahr${r.running ? " bis zum selben Tag" : ""}</span>` : ""}</div>
      <ul class="list">${r.categories.map((c) => html`<li class="row static"><span class="title">${c.name}</span>
        <span class="sub">${c.share < 0.005 ? "unter 1 %" : `${Math.round(c.share * 100)} %`} der Ausgaben${c.previous_cents !== null ? ` · ${changeText(c.cents, c.previous_cents)}` : ""}</span>
        <span class="amount">${money(c.cents)}</span></li>`)}</ul></section>
    ${r.moved.length ? html`<section class="section"><div class="section-head"><h2>Größte Veränderungen</h2></div>
      <ul class="list">${r.moved.map((c) => html`<li class="row static"><span class="title">${c.name}</span>
        <span class="sub">${money(c.previous_cents)} im Vorjahr</span>
        <span class="amount">${c.change_cents > 0 ? "+" : "−"}${money(Math.abs(c.change_cents))}</span></li>`)}</ul></section>` : ""}
    ${r.biggest.length ? html`<section class="section"><div class="section-head"><h2>Größte Einzelausgaben</h2><span class="small muted">ohne Verträge</span></div>
      <ul class="list">${r.biggest.map((b) => html`<li class="row static"><span class="title">${b.name}</span><span class="sub">${dFull(b.date)}</span><span class="amount">${money(-b.amount_cents)}</span></li>`)}</ul></section>` : ""}
    <p class="small muted">${r.count} Buchungen, ohne Umbuchungen zwischen eigenen Konten.</p>
    <a class="btn small" href="api/report/year.pdf?year=${r.year}" download>Als PDF</a>`}`.s, { wide: true });
  on(sh.el, "[data-year]", "click", (_e, el) => { sh.close(); yearSheet(Number(el.dataset.year)); });
  if (r.has_data) historyChart($("#y-chart", sh.el), r.months.filter((m) => !m.future));
}

export function historyChart(el, hist) {
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

export function goalSheet(g) {
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
    ${store.persons.length ? html`<label class="field"><span>Gehört</span><select id="g-owner"><option value="">Allen gemeinsam</option>${store.persons.map((p) => html`<option value="${p.id}" ${p.id === g.owner_person_id ? raw("selected") : ""}>${p.name}</option>`)}</select></label>` : ""}
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
    if ($("#g-owner", sh.el)) body.owner_person_id = Number($("#g-owner", sh.el).value) || null;
    try {
      if (isNew) await api("goals", { method: "POST", body }); else await api(`goals/${g.id}`, { method: "PATCH", body });
      sh.close(); toast("Sparziel gespeichert"); rerender();
    } catch (e) { toast(e.message, { error: true }); }
  };
  if ($("#g-del", sh.el)) confirmButton($("#g-del", sh.el), "Wirklich löschen?", async () => {
    await api(`goals/${g.id}`, { method: "DELETE" }); sh.close(); toast("Sparziel gelöscht"); rerender();
  });
}

export function budgetSheet(catId, person, limits) {
  const c = store.catById.get(catId);
  if (!c) return;
  const current = person ? (limits || {})[catId] || null : c.budget_cents;
  const sh = openSheet(html`${sheetHead((person ? `Budget von ${person.name}: ` : "Budget ") + c.name)}
    <p class="small muted">Monatliche Obergrenze für ${c.name}${childCats(c.id).length ? " inklusive aller Unterkategorien" : ""}${person ? `. Zählt nur Ausgaben von den eigenen Konten von ${person.name}` : ""}.</p>
    <label class="field"><span>Betrag pro Monat</span><input class="input" id="bu-amt" inputmode="decimal" value="${toInput(current)}" placeholder="z. B. 400" autofocus></label>
    <div class="actions"><button class="btn primary" id="bu-save">Speichern</button>${current ? html`<button class="btn" id="bu-del">Budget entfernen</button>` : ""}
      <a class="btn" href="#/umsaetze?category=${c.id}&month=${todayIso().slice(0, 7)}" data-close>Buchungen ansehen</a></div>`.s);
  const save = async (cents) => {
    try {
      if (person) await api(`persons/${person.id}/budgets/${c.id}`, { method: "PUT", body: { budget_cents: cents } });
      else await api(`categories/${c.id}`, { method: "PATCH", body: { budget_cents: cents } });
    } catch (e) { toast(e.message, { error: true }); return; }
    sh.close(); toast(cents ? "Budget gespeichert" : "Budget entfernt"); rerender(); };
  $("#bu-save", sh.el).onclick = () => save(Math.abs(parseMoney($("#bu-amt", sh.el).value) || 0) || null);
  $("#bu-amt", sh.el).addEventListener("keydown", (e) => { if (e.key === "Enter") $("#bu-save", sh.el).click(); });
  if ($("#bu-del", sh.el)) $("#bu-del", sh.el).onclick = () => save(null);
}
