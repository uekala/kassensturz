// Kassensturz – Oberfläche, konten. Aufgeteilt aus app.js; Exporte und Importe zwischen den Modulen.

import { $, $$, D, GROUP_LABEL, ICON, KIND_LABEL, MATURING_KINDS, PCT, SAVINGS_KINDS, VALUE_KINDS, api, confirmButton, dFull, dShort, fmtMonth, html, money, on, openSheet, parseMoney, personName, raw, sheetHead, store, toInput, toast, todayIso } from "./core.js";
import { connectionSheet, syncSheet } from "./fints.js";
import { finanzguruSheet, importSheet, pickImportFile } from "./import.js";
import { renderSeq, rerender } from "./router.js";

/* ------------------------------------------------------------------ Konten & Bankzugänge */
export async function renderAccounts(view, _params, seq) {
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
    if (a.kind === "taschengeld") return a.allowance_cents ? `${money(a.allowance_cents)} ${a.allowance_interval === "week" ? "jede Woche" : "jeden Monat"}` : "ohne automatische Gutschrift";
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
  // Taschengeld ist eine Abmachung und liegt schon auf den Konten der Eltern; es zählt nicht zum Vermögen.
  const live = accounts.filter((a) => !a.archived && a.balance_known && a.group !== "taschengeld");
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
          <span class="title">${a.name}${a.archived ? " (archiviert)" : ""}${!a.in_forecast && !a.archived && !VALUE_KINDS.has(a.kind) && a.kind !== "taschengeld" ? html` <span class="chip neutral">nicht in Prognose</span>` : ""}${a.drift_cents ? html` <span class="chip warn">passt nicht</span>` : ""}${a.owner_person_id ? html` <span class="chip neutral">${personName(a.owner_person_id)}</span>` : ""}</span>
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
    try {
      const res = await api("inbox/analyze", { method: "POST", body: { filename: el.dataset.ibAssign } });
      if (res.kind === "finanzguru") finanzguruSheet(res); else importSheet(res);
    } catch (e) { toast(e.message); }
  });
  on(view, "[data-ib-del]", "click", (_e, el) => {
    if (el.dataset.armed) { api(`inbox/${encodeURIComponent(el.dataset.ibDel)}`, { method: "DELETE" }).then(() => { toast("Datei gelöscht"); rerender(); }); return; }
    el.dataset.armed = "1"; el.textContent = "Wirklich löschen?";
  });
}

export function bankChooser(eb) {
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

export async function ebSetupSheet() {
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

export const EB_COUNTRIES = [["DE", "Deutschland"], ["AT", "Österreich"], ["LU", "Luxemburg"], ["NL", "Niederlande"], ["BE", "Belgien"], ["FR", "Frankreich"],
  ["LT", "Litauen"], ["SE", "Schweden"], ["FI", "Finnland"], ["IE", "Irland"], ["ES", "Spanien"], ["IT", "Italien"]];

export function ebConnectSheet(renew) {
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
      <p class="small muted">Nicht dabei? Manche Banken laufen unter dem Land, in dem sie ihren Sitz haben – PayPal etwa unter Luxemburg. Fehlt die Bank auch dort, bleibt der Datei-Import oder der Eingangsordner.</p>`.s);
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

export function pollJob(sh, job, title, intro = "") {
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

export async function ebSyncSheet(s) {
  const sh = openSheet(html`${sheetHead(s.aspsp_name)}<div class="progress"><div class="spinner"></div><span>Verbinde …</span></div>`.s);
  try { pollJob(sh, await api(`eb/sessions/${s.id}/sync`, { method: "POST" }), s.aspsp_name); }
  catch (e) { sh.set(html`${sheetHead(s.aspsp_name)}<p>${e.message}</p><div class="actions"><button class="btn" data-close>Schließen</button></div>`.s); }
}

export function ebEditSheet(s) {
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

export function accountSheet(a) {
  const isNew = !a;
  a = a || { name: "", kind: "giro", iban: "", settlement_pattern: "", in_forecast: 1, archived: 0 };
  const sh = openSheet(html`${sheetHead(isNew ? "Konto anlegen" : a.name)}
    ${!isNew ? html`<div class="big-amount">${a.balance_known ? money(a.balance_now) : "Kontostand fehlt"}</div>
      <div class="actions" style="margin-top:0"><button class="btn small" id="ac-bal">${a.kind === "kredit" ? "Restschuld eintragen" : VALUE_KINDS.has(a.kind) ? "Wert eintragen" : "Kontostand eintragen"}</button>
      ${a.kind === "kredit" ? html`<button class="btn small" id="ac-loan">Tilgungsplan</button>` : html`<a class="btn small" href="#/umsaetze?account=${a.id}" data-close>Buchungen ansehen</a>`}</div>
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
    <div id="ac-loan-terms" ${a.kind === "kredit" ? "" : raw("hidden")}>
      <div class="field-row">
        <label class="field"><span>Sollzins in % pro Jahr</span><input class="input" id="ac-rate" inputmode="decimal" value="${a.loan_rate_milli === null || a.loan_rate_milli === undefined ? "" : PCT.format(a.loan_rate_milli / 1000)}" placeholder="z. B. 3,49"></label>
        <label class="field"><span>Monatsrate</span><input class="input" id="ac-pay" inputmode="decimal" value="${toInput(a.loan_payment_cents)}" placeholder="z. B. 350,00"></label>
      </div>
      <p class="small muted" style="margin-top:-6px">Mit Zins und Rate rechnet Kassensturz den Tilgungsplan: Restschuld, Enddatum, Zinsen und was eine Sondertilgung bringt.</p>
    </div>
    <div id="ac-pocket" ${a.kind === "taschengeld" ? "" : raw("hidden")}>
      <div class="field-row">
        <label class="field"><span>Taschengeld je Termin</span><input class="input" id="ac-allow" inputmode="decimal" value="${toInput(a.allowance_cents)}" placeholder="z. B. 5,00"></label>
        <label class="field"><span>Rhythmus</span><select id="ac-allow-int"><option value="week" ${a.allowance_interval === "week" ? raw("selected") : ""}>jede Woche</option><option value="month" ${a.allowance_interval !== "week" ? raw("selected") : ""}>jeden Monat</option></select></label>
      </div>
      <p class="small muted" style="margin-top:-6px">${a.allowance_next ? `Nächste Gutschrift am ${dFull(a.allowance_next)}. ` : "Die erste Gutschrift kommt sofort, danach im gewählten Rhythmus. "}Ausgaben trägst du von Hand ein. Das Konto zählt nicht zum Vermögen und nicht zur Prognose. Wähle unten unter „Gehört“ das Kind.</p>
    </div>
    <label class="check" id="ac-fc-row" style="${a.kind === "taschengeld" ? "display:none" : ""}"><input type="checkbox" id="ac-fc" ${a.in_forecast ? raw("checked") : ""}><span>Zählt zum Kontostand und zur Prognose</span></label>
    ${store.persons.length ? html`<label class="field"><span>Gehört</span><select id="ac-owner"><option value="">Allen gemeinsam</option>${store.persons.map((p) => html`<option value="${p.id}" ${p.id === a.owner_person_id ? raw("selected") : ""}>${p.name}</option>`)}</select></label>
    <p class="small muted" style="margin-top:-6px">Ein eigenes Konto sieht in der App nur diese Person, ein gemeinsames sehen alle. Hier in Home Assistant bleibt alles sichtbar.</p>` : ""}
    ${!isNew ? html`<label class="check"><input type="checkbox" id="ac-arch" ${a.archived ? raw("checked") : ""}><span>Archivieren – Buchungen bleiben erhalten, fließen aber nicht mehr ein</span></label>` : ""}
    <div class="actions"><button class="btn primary" id="ac-save">${isNew ? "Anlegen" : "Speichern"}</button>
      ${!isNew ? html`<button class="btn danger" id="ac-del">Konto löschen</button>` : ""}</div>`.s);
  $("#ac-save", sh.el).onclick = async () => {
    const body = { name: $("#ac-name", sh.el).value.trim(), kind: $("#ac-kind", sh.el).value, iban: $("#ac-iban", sh.el).value.trim(),
      settlement_pattern: $("#ac-settle", sh.el).value.trim(), in_forecast: $("#ac-fc", sh.el).checked ? 1 : 0 };
    body.matures_on = MATURING_KINDS.has(body.kind) ? $("#ac-due", sh.el).value : "";
    if ($("#ac-owner", sh.el)) body.owner_person_id = Number($("#ac-owner", sh.el).value) || null;
    if (body.kind === "taschengeld") {
      body.allowance_cents = Math.abs(parseMoney($("#ac-allow", sh.el).value) || 0) || null;
      body.allowance_interval = $("#ac-allow-int", sh.el).value;
    }
    if (!isNew) body.archived = $("#ac-arch", sh.el).checked ? 1 : 0;
    if (body.kind === "kredit") {
      const rate = $("#ac-rate", sh.el).value.trim().replace("%", "").trim();
      const pct = rate === "" ? null : Number(rate.replace(",", "."));
      if (pct !== null && !(pct >= 0 && pct <= 30)) { toast("Der Sollzins ist keine Zahl zwischen 0 und 30"); return; }
      body.loan_rate_milli = pct === null ? null : Math.round(pct * 1000);
      body.loan_payment_cents = Math.abs(parseMoney($("#ac-pay", sh.el).value) || 0) || null;
    }
    try {
      if (isNew) await api("accounts", { method: "POST", body }); else await api(`accounts/${a.id}`, { method: "PATCH", body });
      sh.close(); toast("Konto gespeichert"); rerender();
    } catch (e) { toast(e.message); }
  };
  $("#ac-kind", sh.el).onchange = (e) => {
    const kind = e.target.value;
    if (isNew) $("#ac-fc", sh.el).checked = !SAVINGS_KINDS.has(kind);
    $("#ac-due-field", sh.el).hidden = !MATURING_KINDS.has(kind);
    $("#ac-pocket", sh.el).hidden = kind !== "taschengeld";
    $("#ac-loan-terms", sh.el).hidden = kind !== "kredit";
    $("#ac-fc-row", sh.el).style.display = kind === "taschengeld" ? "none" : "";
    $("#ac-due-label", sh.el).textContent = kind === "kredit" ? "Läuft bis" : "Fällig am";
  };
  if ($("#ac-bal", sh.el)) $("#ac-bal", sh.el).onclick = () => { sh.close(); balanceSheet(a); };
  if ($("#ac-loan", sh.el)) $("#ac-loan", sh.el).onclick = () => { sh.close(); loanSheet(a); };
  if ($("#ac-drift", sh.el)) $("#ac-drift", sh.el).onclick = async () => {
    await api(`accounts/${a.id}/balance-check/reset`, { method: "POST" }); sh.close(); toast("Hinweis ausgeblendet"); rerender();
  };
  if ($("#ac-del", sh.el)) confirmButton($("#ac-del", sh.el), `Wirklich ${a.tx_count} Buchungen löschen?`, async () => {
    await api(`accounts/${a.id}`, { method: "DELETE" }); sh.close(); toast("Konto gelöscht"); rerender();
  });
}

// Tilgungsplan eines Kredits: Restschuld heute, Enddatum, Zinsen, Sondertilgung, Plan je Jahr.
export async function loanSheet(a) {
  let p;
  try { p = await api(`accounts/${a.id}/loan`); } catch (err) { toast(err.message); return; }
  const need = { rate: "den Sollzins", payment: "die Monatsrate", balance: "die Restschuld" };
  const span = (n) => (n >= 12 ? `${Math.floor(n / 12)} ${Math.floor(n / 12) === 1 ? "Jahr" : "Jahre"}${n % 12 ? ` und ${n % 12} ${n % 12 === 1 ? "Monat" : "Monate"}` : ""}` : `${n} ${n === 1 ? "Monat" : "Monate"}`);
  const body = !p.ready
    ? html`<p class="muted">Für den Tilgungsplan fehlt noch: ${p.missing.map((m) => need[m]).join(", ")}. ${p.missing.includes("balance") ? "Die Restschuld trägst du über „Restschuld eintragen“ ein, " : ""}Zins und Rate stehen in den Angaben des Kontos.</p>
      <div class="actions"><button class="btn primary" id="ln-edit">Angaben ergänzen</button></div>`
    : !p.covers_interest
      ? html`<div class="big-amount">${money(-p.today_cents)}</div>
        <div class="alert critical"><div><strong>Die Rate deckt die Zinsen nicht</strong><p class="small">Im Monat fallen ${money(p.first_interest_cents)} Zinsen an, die Rate beträgt ${money(p.payment_cents)}. So wächst die Schuld. Prüfe Zins und Rate.</p></div></div>
        <div class="actions"><button class="btn primary" id="ln-edit">Angaben ändern</button></div>`
      : html`<div class="big-amount">${money(-p.today_cents)}</div>
        <p class="small muted">${p.months_since_entry ? `Geschätzt. Eingetragen waren ${money(p.entered_cents)} am ${dFull(p.entered_on)}, seitdem ${p.months_since_entry} ${p.months_since_entry === 1 ? "Rate" : "Raten"}.` : `Restschuld, eingetragen am ${dFull(p.entered_on)}.`}</p>
        <dl class="facts">
          <dt>Sollzins</dt><dd>${PCT.format(p.rate_milli / 1000)} % pro Jahr</dd>
          <dt>Monatsrate</dt><dd>${money(p.payment_cents)}, davon zurzeit ${money(p.first_interest_cents)} Zinsen</dd>
          <dt>Fertig</dt><dd>${p.done ? `${fmtMonth.format(D(p.end_date))}, in ${span(p.months)}` : "in mehr als 60 Jahren"}</dd>
          <dt>Noch Zinsen</dt><dd>${money(p.interest_cents)}${p.done ? `, zusammen noch ${money(p.total_cents)}` : ""}</dd>
        </dl>
        ${p.end_differs ? html`<p class="small muted">Am Konto steht „läuft bis ${dFull(p.matures_on)}“. Nach Zins und Rate wäre der Kredit ${fmtMonth.format(D(p.end_date))} getilgt. Bleibt am Ende der Laufzeit eine Restschuld, ist das die Schlussrate oder die Anschlussfinanzierung.</p>` : ""}
        <h3 style="margin-top:18px">Sondertilgung</h3>
        <form class="afford" id="ln-extra-form"><input class="input" id="ln-extra" inputmode="decimal" placeholder="Betrag in Euro" aria-label="Sondertilgung in Euro"><button class="btn" type="submit">Rechnen</button></form>
        <div id="ln-extra-out" aria-live="polite"></div>
        ${p.years.length ? html`<h3 style="margin-top:18px">Plan je Jahr</h3>
          <table class="plan"><thead><tr><th>Jahr</th><th>Gezahlt</th><th>davon Zinsen</th><th>Rest am Ende</th></tr></thead>
          <tbody>${p.years.slice(0, 40).map((y) => html`<tr><td>${y.year}</td><td>${money(y.paid_cents)}</td><td>${money(y.interest_cents)}</td><td>${money(y.rest_cents)}</td></tr>`)}</tbody></table>` : ""}
        <p class="small muted">Gerechnet mit monatlicher Verrechnung und gleichbleibendem Zins. Die Bank rechnet taggenau; verbindlich ist ihr Auszug.</p>
        <div class="actions">${p.months_since_entry ? html`<button class="btn primary" id="ln-take">Geschätzte Restschuld übernehmen</button>` : ""}<button class="btn" id="ln-bal">Restschuld eintragen</button><button class="btn" id="ln-edit">Angaben ändern</button></div>`;
  const sh = openSheet(html`${sheetHead(`Tilgungsplan ${a.name}`)}${body}`.s);
  $("#ln-edit", sh.el).onclick = () => { sh.close(); accountSheet(a); };
  if ($("#ln-bal", sh.el)) $("#ln-bal", sh.el).onclick = () => { sh.close(); balanceSheet(a); };
  if ($("#ln-take", sh.el)) $("#ln-take", sh.el).onclick = async () => {
    try { await api(`accounts/${a.id}/balance`, { method: "POST", body: { balance_cents: p.today_cents, date: todayIso() } }); sh.close(); toast("Restschuld übernommen"); rerender(); }
    catch (err) { toast(err.message); }
  };
  if ($("#ln-extra-form", sh.el)) $("#ln-extra-form", sh.el).onsubmit = async (e) => {
    e.preventDefault();
    const cents = Math.abs(parseMoney($("#ln-extra", sh.el).value) || 0);
    if (!cents) { toast("Bitte einen Betrag eintragen"); return; }
    try {
      const x = (await api(`accounts/${a.id}/loan?extra_cents=${cents}`)).extra;
      $("#ln-extra-out", sh.el).innerHTML = html`<div class="alert" style="margin-top:10px;display:block;cursor:default"><strong>${money(x.cents)} heute getilgt</strong>
        <p class="small">${x.months ? `Fertig ${fmtMonth.format(D(x.end_date))}${x.months_saved ? `, ${span(x.months_saved)} früher` : ", zur selben Zeit"}.` : "Damit wäre der Kredit sofort getilgt."} Du sparst ${money(x.interest_saved_cents)} Zinsen. Ob und wie viel du ohne Gebühr sondertilgen darfst, steht im Vertrag.</p></div>`.s;
    } catch (err) { toast(err.message); }
  };
}

export function balanceSheet(a) {
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
