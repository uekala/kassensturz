// Kassensturz – Oberfläche, fints. Aufgeteilt aus app.js; Exporte und Importe zwischen den Modulen.

import { $, $$, api, confirmButton, html, on, openSheet, raw, sheetHead, toast } from "./core.js";
import { go, rerender } from "./router.js";

/* --- FinTS ------------------------------------------------------------------------------- */
export async function connectionSheet(c) {
  const isNew = !c;
  const banks = await api("banks");
  c = c || { name: "", blz: "", login: "", customer_id: "", server: "", history_days: 365 };
  const sh = openSheet(html`${sheetHead(isNew ? "Bankzugang hinzufügen" : c.name)}
    ${isNew ? html`<label class="field"><span>Bank</span><select id="cn-preset"><option value="">Andere Bank</option>${banks.map((b, i) => html`<option value="${i}">${b.name}</option>`)}</select></label>` : ""}
    <label class="field"><span>Name</span><input class="input" id="cn-name" value="${c.name}" placeholder="z. B. Sparkasse"></label>
    <div class="field-row">
      <label class="field"><span>Bankleitzahl</span><input class="input" id="cn-blz" value="${c.blz}" inputmode="numeric" placeholder="meist Stelle 5–12 der IBAN"></label>
      <label class="field"><span>Abruf beim ersten Mal</span><select id="cn-days">${[[90, "90 Tage"], [365, "1 Jahr"], [730, "2 Jahre"]].map(([v, l]) => html`<option value="${v}" ${v === c.history_days ? raw("selected") : ""}>${l}</option>`)}</select></label>
    </div>
    <label class="field"><span>Anmeldename (wie im Online-Banking)</span><input class="input" id="cn-login" value="${c.login}" autocomplete="off"></label>
    <label class="field"><span>Kunden-ID (fast immer leer lassen)</span><input class="input" id="cn-cust" value="${c.customer_id || ""}" autocomplete="off"></label>
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
    } catch (e) { toast(e.message, { error: true }); }
  };
  if (!isNew) {
    $("#cn-tan", sh.el).onclick = async () => { await api(`connections/${c.id}/reset-tan`, { method: "POST" }); toast("Beim nächsten Abruf wird das TAN-Verfahren neu abgefragt"); };
    if ($("#cn-pin", sh.el)) $("#cn-pin", sh.el).onclick = async () => { await api(`connections/${c.id}/pin`, { method: "DELETE" }); sh.close(); toast("PIN gelöscht, kein automatischer Abruf mehr"); rerender(); };
    confirmButton($("#cn-del", sh.el), "Wirklich löschen? Konten bleiben", async () => { await api(`connections/${c.id}`, { method: "DELETE" }); sh.close(); rerender(); });
  }
}

export function syncSheet(conn) {
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
      // Hat die Bank die Anmeldung abgelehnt, nie mit der gespeicherten PIN wiederholen.
      if (/Anmeldung abgelehnt/.test(j.error || "")) conn.login_rejected = true;
      $("#sy-retry", sh.el).onclick = () => (conn.has_pin && !conn.login_rejected ? start({}) : askPin());
    }
    if ($("#sy-cancel", sh.el)) $("#sy-cancel", sh.el).onclick = async () => { await api(`jobs/${j.id}/cancel`, { method: "POST" }); sh.close(); };
  };
  if (conn.has_pin && !conn.login_rejected) start({});
  else askPin(conn.login_rejected ? "Die Bank hat die letzte Anmeldung abgelehnt. Prüfe Anmeldename und PIN zuerst auf der Webseite der Bank. Stimmt die PIN, setz den Haken, damit sie die gespeicherte ersetzt." : "");
}
