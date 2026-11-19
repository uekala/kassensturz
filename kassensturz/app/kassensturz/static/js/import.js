// Kassensturz – Oberfläche, import. Aufgeteilt aus app.js; Exporte und Importe zwischen den Modulen.

import { $, $$, KIND_LABEL, VALUE_KINDS, api, childCats, dFull, html, loadBase, money, on, openSheet, raw, sheetHead, store, toast, topCats } from "./core.js";
import { balanceSheet } from "./konten.js";
import { go, rerender } from "./router.js";

/* --- Datei-Import ----------------------------------------------------------------------- */
export function pickImportFile() {
  const input = document.createElement("input");
  input.type = "file";
  // Neben den Endungen auch die Dateiarten: Android führt CSV oft als text/comma-separated-values
  // und blendet sie sonst in der Dateiauswahl aus.
  input.accept = ".csv,.txt,.xml,.zip,.sta,.mt940,.940,.xlsx,text/csv,text/comma-separated-values,application/csv,"
    + "text/plain,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/zip,text/xml,application/xml";
  input.onchange = async () => {
    const f = input.files[0];
    if (!f) return;
    const form = new FormData();
    form.append("file", f);
    // Der Export von Ladecockpit enthält Ladevorgänge, keine Buchungen; er geht einen eigenen Weg.
    const head = (await f.slice(0, 300).text()).replace(/^\uFEFF/, "");
    if (/^(Datum;Start;Ende;Standort;kWh|Date,Start,End,Site,kWh)/.test(head)) { chargingImport(form); return; }
    const sh = openSheet(html`${sheetHead("Datei wird gelesen")}<div class="progress"><div class="spinner"></div><span>${f.name}</span></div>`.s);
    try {
      const res = await api("import/analyze", { method: "POST", form });
      sh.close();
      if (res.kind === "ladecockpit") chargingImport(form);
      else if (res.kind === "finanzguru") finanzguruSheet(res); else importSheet(res);
    } catch (e) {
      sh.set(html`${sheetHead("Datei nicht lesbar")}<p>${e.message}</p><div class="actions"><button class="btn" data-close>Schließen</button></div>`.s);
    }
  };
  input.click();
}

async function chargingImport(form) {
  const sh = openSheet(html`${sheetHead("Ladevorgänge werden gelesen")}<div class="progress"><div class="spinner"></div></div>`.s);
  try {
    const r = await api("charging/import", { method: "POST", form });
    sh.set(html`${sheetHead("Ladevorgänge aus Ladecockpit")}
      <p><b>${r.added} neu</b>${r.known ? `, ${r.known} schon bekannt` : ""}${r.skipped ? `, ${r.skipped} übersprungen` : ""}.
        ${r.linked} ${r.linked === 1 ? "Ladevorgang ist" : "Ladevorgänge sind"} jetzt einer Abbuchung zugeordnet.</p>
      <p class="small muted">Buchungen legt das nicht an: Die Abbuchung kommt von deiner Bank. Kassensturz hängt kWh, Preis und Ort an die Buchung mit genau diesem Betrag.</p>
      <div class="actions"><button class="btn primary" data-close>Fertig</button></div>`.s);
    rerender();
  } catch (e) {
    sh.set(html`${sheetHead("Datei nicht lesbar")}<p>${e.message}</p><div class="actions"><button class="btn" data-close>Schließen</button></div>`.s);
  }
}

export function importSheet(res) {
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

/* --- Umstieg von Finanzguru -------------------------------------------------------------- */
export function finanzguruSheet(res) {
  // Die Auswahl bleibt erhalten, wenn die Vorschau nach einer Änderung neu kommt.
  const accChoice = new Map(res.accounts.map((a) => [a.ref, { target: a.target, name: a.suggest.name, kind: a.suggest.kind }]));
  const catChoice = res.categories.map((c) => (c.suggest === null || c.suggest === undefined ? "" : String(c.suggest)));
  const NEW_KINDS = ["giro", "tagesgeld", "sparkonto", "kreditkarte", "paypal", "bargeld", "sonstiges"];
  let learn = true;
  const sh = openSheet("", { wide: true });
  const choices = () => res.accounts.map((a) => ({ ref: a.ref, ...accChoice.get(a.ref) }));
  const catOptions = (selected) => html`<option value="" ${selected === "" ? raw("selected") : ""}>Kassensturz ordnet zu</option>
    <option value="new" ${selected === "new" ? raw("selected") : ""}>Neu anlegen</option>
    ${topCats().map((c) => html`<option value="${c.id}" ${String(c.id) === selected ? raw("selected") : ""}>${c.name}</option>${childCats(c.id).map((ch) => html`<option value="${ch.id}" ${String(ch.id) === selected ? raw("selected") : ""}>\u00a0\u00a0${ch.name}</option>`)}`)}`;
  const draw = () => {
    const accs = store.accounts.filter((a) => !a.archived && !VALUE_KINDS.has(a.kind) && a.kind !== "taschengeld");
    const skipped = Object.entries(res.skipped || {}).map(([k, v]) => `${v} ${k}`).join(", ");
    const total = res.accounts.reduce((sum, a) => sum + a.will_add, 0);
    sh.set(html`${sheetHead("Von Finanzguru umziehen")}
      <p><strong>${res.count} Buchungen</strong> auf ${res.accounts.length} ${res.accounts.length === 1 ? "Konto" : "Konten"}${res.first ? `, vom ${dFull(res.first)} bis ${dFull(res.last)}` : ""}.${skipped ? html` <span class="muted">Übersprungen: ${skipped}.</span>` : ""}</p>
      ${res.splits && res.splits.plain ? html`<p class="note">Bei ${res.splits.plain} aufgeteilten ${res.splits.plain === 1 ? "Buchung ergeben" : "Buchungen ergeben"} die Teile nicht den Betrag. Sie ${res.splits.plain === 1 ? "kommt" : "kommen"} ohne Aufteilung.</p>` : ""}
      ${res.splits && res.splits.unclear ? html`<p class="note">${res.splits.unclear} ${res.splits.unclear === 1 ? "Teilbuchung steht" : "Teilbuchungen stehen"} ohne die zugehörige Buchung im Export und ${res.splits.unclear === 1 ? "wird" : "werden"} einzeln übernommen. Prüf danach, ob dort etwas doppelt zählt.</p>` : ""}
      <h3>Konten</h3>
      <p class="small muted">Hat ein Konto schon Buchungen aus Bankabruf oder Datei, füllt der Export nur die Zeit davor auf. So entsteht nichts doppelt.</p>
      ${res.accounts.map((a, i) => { const ch = accChoice.get(a.ref); return html`<div class="fg-acc">
        <div><strong>${a.name}</strong>${a.label ? html` <span class="muted small">${a.label}</span>` : ""}<br>
          <span class="small muted">${a.count} Buchungen, ${dFull(a.first)} bis ${dFull(a.last)}</span></div>
        <select data-fg-acc="${i}" aria-label="Ziel für ${a.name}">
          <option value="new" ${ch.target === "new" ? raw("selected") : ""}>Neues Konto anlegen</option>
          ${accs.map((x) => html`<option value="${x.id}" ${ch.target === x.id ? raw("selected") : ""}>${x.name}</option>`)}
          <option value="skip" ${ch.target === "skip" ? raw("selected") : ""}>Nicht übernehmen</option></select>
        ${ch.target === "new" ? html`<div class="field-row">
          <label class="field"><span>Name</span><input class="input" data-fg-name="${i}" value="${ch.name}"></label>
          <label class="field"><span>Art</span><select data-fg-kind="${i}">${NEW_KINDS.map((k) => html`<option value="${k}" ${k === ch.kind ? raw("selected") : ""}>${KIND_LABEL[k]}</option>`)}</select></label></div>` : ""}
        ${typeof ch.target === "number" && a.cutoff ? html`<p class="small muted">Dieses Konto hat Buchungen ab dem ${dFull(a.cutoff)}. Übernommen wird, was davor liegt: ${a.will_add} von ${a.count}.</p>` : ""}
      </div>`; })}
      ${res.categories.length ? html`<h3 style="margin-top:20px">Kategorien</h3>
      <p class="small muted">Was du hier zuordnest, behält seine Kategorie. Bei „Kassensturz ordnet zu“ entscheidet Kassensturz selbst.${res.transfers ? ` ${res.transfers} Umbuchungen bleiben Umbuchungen.` : ""}${res.splits && res.splits.taken ? ` ${res.splits.taken} aufgeteilte ${res.splits.taken === 1 ? "Buchung bleibt" : "Buchungen bleiben"} aufgeteilt.` : ""}</p>
      <table class="map-table">${res.categories.map((c, i) => html`<tr><td>${c.main}${c.main && c.sub ? " › " : ""}${c.sub} <span class="muted">(${c.count})</span></td>
        <td><select data-fg-cat="${i}" aria-label="Kategorie für ${c.sub || c.main}">${catOptions(catChoice[i])}</select></td></tr>`)}</table>
      <label class="check"><input type="checkbox" id="fg-learn" ${learn ? raw("checked") : ""}><span>Daraus lernen: Was in Finanzguru verlässlich gleich zugeordnet war, gilt auch für künftige Buchungen.</span></label>` : ""}
      <div class="actions"><button class="btn primary" id="fg-go" ${!total ? raw("disabled") : ""}>${total} Buchungen übernehmen</button><button class="btn" data-close>Abbrechen</button></div>`.s);
    on(sh.el, "[data-fg-acc]", "change", async (_e, el) => {
      const a = res.accounts[Number(el.dataset.fgAcc)];
      accChoice.get(a.ref).target = /^\d+$/.test(el.value) ? Number(el.value) : el.value;
      try {
        const next = await api("import/finanzguru/preview", { method: "POST", body: { token: res.token, accounts: choices() } });
        res = { ...res, accounts: next.accounts };
        draw();
      } catch (e) { toast(e.message); }
    });
    on(sh.el, "[data-fg-name]", "input", (_e, el) => { accChoice.get(res.accounts[Number(el.dataset.fgName)].ref).name = el.value; });
    on(sh.el, "[data-fg-kind]", "change", (_e, el) => { accChoice.get(res.accounts[Number(el.dataset.fgKind)].ref).kind = el.value; });
    on(sh.el, "[data-fg-cat]", "change", (_e, el) => { catChoice[Number(el.dataset.fgCat)] = el.value; });
    if ($("#fg-learn", sh.el)) $("#fg-learn", sh.el).onchange = (e) => { learn = e.target.checked; };
    $("#fg-go", sh.el).onclick = async () => {
      $("#fg-go", sh.el).disabled = true;
      const body = { token: res.token, learn, accounts: choices(),
        categories: res.categories.map((c, i) => ({ main: c.main, sub: c.sub, target: catChoice[i] === "" ? null : catChoice[i] })) };
      try {
        const r = await api("import/finanzguru/commit", { method: "POST", body });
        const extras = [r.learned ? `${r.learned} ${r.learned === 1 ? "Zuordnung" : "Zuordnungen"} gelernt` : "",
          r.categories_created ? `${r.categories_created} ${r.categories_created === 1 ? "Kategorie" : "Kategorien"} angelegt` : ""].filter(Boolean).join(", ");
        sh.set(html`${sheetHead("Umzug abgeschlossen")}
          <p><strong>${r.added} Buchungen übernommen</strong>.${extras ? ` ${extras}.` : ""}</p>
          ${r.accounts.map((a) => html`<div class="fg-acc"><div><strong>${a.name}</strong>${a.created ? " (neu)" : ""}${a.balance_known ? "" : html` <span class="chip warn">Stand fehlt</span>`}<br>
            <span class="small muted">${a.added} übernommen${a.skipped ? `, ${a.skipped} waren schon da` : ""}${a.held_back ? `. ${a.held_back} ab dem ${dFull(a.cutoff)} liefert die Bank` : ""}</span></div></div>`)}
          ${r.accounts.some((a) => !a.balance_known) ? html`<p class="small muted">Wo der Stand fehlt: Konto unter „Konten“ öffnen und den aktuellen Kontostand eintragen.</p>` : ""}
          <div class="actions"><button class="btn primary" data-close>Fertig</button></div>`.s);
        await loadBase();
        rerender();
      } catch (e) { toast(e.message); $("#fg-go", sh.el).disabled = false; }
    };
  };
  draw();
}
