// Kassensturz – Oberfläche, einstellungen. Aufgeteilt aus app.js; Exporte und Importe zwischen den Modulen.

import { $, $$, api, confirmButton, dFull, dShort, html, money, on, openSheet, parseMoney, personName, raw, relDay, sheetHead, store, toInput, toast, topCats } from "./core.js";
import { go, renderSeq, rerender } from "./router.js";
import { bindCategoryPicker, categoryPicker, drawHealth, drawTax, drawWarranties } from "./umsaetze.js";

/* ------------------------------------------------------------------ Einstellungen */
// Änderungsprotokoll: jüngste zuerst, mit Uhrzeit und wer es war.
export const fmtStamp = new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
export function changeList(items) {
  return html`<ul class="list changes">${items.map((c) => html`<li class="row static"><span class="title">${c.text}</span>
    <span class="sub">${c.actor}${c.actor_kind === "phone" ? " (Handy)" : ""}, ${fmtStamp.format(new Date(c.at))}</span></li>`)}</ul>`;
}
export async function changesSheet() {
  const state = { offset: 0, actor: "", items: [] };
  const sh = openSheet(html`${sheetHead("Änderungen")}
    <label class="field"><span>Von</span><select class="input" id="chg-actor"><option value="">Allen</option></select></label>
    <p class="small muted" id="chg-count"></p><div id="chg-list"></div>
    <div class="actions"><button class="btn" id="chg-more" style="display:none">Weitere laden</button></div>`.s);
  const load = async (reset) => {
    if (reset) { state.offset = 0; state.items = []; }
    const q = new URLSearchParams({ offset: state.offset, limit: 100 });
    if (state.actor) q.set("actor", state.actor);
    let r;
    try { r = await api("changes?" + q); } catch (err) { toast(err.message, { error: true }); return; }
    state.items.push(...r.items);
    state.offset += r.items.length;
    const sel = $("#chg-actor", sh.el);
    if (sel.options.length === 1) r.actors.forEach((a) => sel.add(new Option(a, a)));
    $("#chg-count", sh.el).textContent = `${r.total} ${r.total === 1 ? "Eintrag" : "Einträge"}`;
    $("#chg-list", sh.el).innerHTML = state.items.length ? changeList(state.items).s : '<p class="muted">Keine Einträge.</p>';
    $("#chg-more", sh.el).style.display = state.offset >= r.total ? "none" : "";
  };
  $("#chg-actor", sh.el).onchange = (e) => { state.actor = e.target.value; load(true); };
  $("#chg-more", sh.el).onclick = () => load(false);
  await load(true);
}

// Zahlungskalender: Adresse für „Remote Calendar“ in Home Assistant, ein- und ausschalten.
export function calendarBox(cal) {
  if (!cal.enabled) {
    return html`<p class="small muted">Kommende Abbuchungen, Eingänge, geplante Ausgaben und letzte Tage zum Kündigen als Kalender in Home Assistant, ein Jahr im Voraus. Gut für Automationen, etwa eine Erinnerung am Tag vor einer großen Abbuchung.</p>
      <div class="actions" style="margin-top:8px"><button class="btn" id="cal-on">Kalender-Adresse erstellen</button></div>`.s;
  }
  return html`<p class="small">Diese Adresse in Home Assistant unter <em>Einstellungen → Geräte & Dienste → Integration hinzufügen → Remote Calendar</em> eintragen:</p>
    <p class="small"><code class="cal-url" id="cal-url">${cal.url}</code></p>
    <p class="small muted">Erreichbar nur im internen Netz von Home Assistant, nicht übers Handy. Wer die Adresse kennt, sieht die Termine mit Beträgen; eine neue Adresse macht die alte ungültig.</p>
    ${cal.next.length ? html`<ul class="list">${cal.next.map((e) => html`<li class="row static"><span class="title">${e.summary}</span><span class="sub">${relDay(e.date)}</span></li>`)}</ul>
      <p class="small muted">${cal.count} Termine im nächsten Jahr.</p>` : html`<p class="small muted">Im nächsten Jahr steht noch nichts an.</p>`}
    <div class="actions" style="margin-top:8px"><button class="btn" id="cal-copy">Adresse kopieren</button><button class="btn" id="cal-renew">Neue Adresse</button><button class="btn" id="cal-off">Ausschalten</button></div>`.s;
}
export function bindCalendar(box) {
  const act = async (action, text) => {
    try { box.innerHTML = calendarBox(await api("calendar", { method: "POST", body: { action } })); bindCalendar(box); toast(text); }
    catch (err) { toast(err.message, { error: true }); }
  };
  if ($("#cal-on", box)) $("#cal-on", box).onclick = () => act("on", "Kalender-Adresse erstellt");
  if ($("#cal-renew", box)) $("#cal-renew", box).onclick = () => act("renew", "Neue Adresse. Trag sie in Home Assistant neu ein");
  if ($("#cal-off", box)) $("#cal-off", box).onclick = () => act("off", "Kalender ausgeschaltet");
  if ($("#cal-copy", box)) $("#cal-copy", box).onclick = async () => {
    try { await navigator.clipboard.writeText($("#cal-url", box).textContent); toast("Adresse kopiert"); }
    catch { toast("Kopieren ging nicht. Bitte die Adresse markieren und kopieren", { error: true }); }
  };
}

export async function renderSettings(view, _params, seq) {
  const [s, rules, learned, devices, sharing, changes, cal] = await Promise.all([
    api("settings"),
    api("rules"),
    api("learned"),
    api("mobile/devices").catch(() => ({ items: [] })),
    api("household/sharing"),
    api("changes?limit=6"),
    api("calendar"),
  ]);
  if (seq !== renderSeq) return;
  const p = s.profile || {};
  // Handys ohne Person fallen erst auf, wenn es eigene Konten gibt: Dann sehen sie nur noch die gemeinsamen.
  const unassigned = store.accounts.some((a) => a.owner_person_id) ? devices.items.filter((d) => !d.revoked_at && !d.person_id).length : 0;
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
        <div class="section-head" style="margin-top:22px"><h2>Zahlungskalender</h2></div>
        <div id="cal-box">${raw(calendarBox(cal))}</div>
      </section>
      <section class="section">
        <div class="section-head"><h2>Haushalt</h2><button class="link-btn" id="p-add">Person hinzufügen</button></div>
        <p class="small muted">Für Paare und Familien: Lege an, wer mitmacht, und ordne Konten und Handys zu. Jede Person sieht in der App ihre eigenen Konten und die gemeinsamen. Diese Oberfläche in Home Assistant ist die Verwaltung und zeigt immer alles.</p>
        ${store.persons.length ? html`<ul class="list">${store.persons.map((p) => html`<li class="row static">
          <span class="title">${p.name}${p.is_child ? html` <span class="chip neutral">Kind</span>` : ""}</span>
          <span class="sub">${p.accounts === 1 ? "1 eigenes Konto" : `${p.accounts} eigene Konten`} · ${p.devices === 1 ? "1 Handy" : `${p.devices} Handys`}${store.persons.length > 1 ? ` · Anteil ${p.share_weight}` : ""}</span>
          <span class="amount"><button class="btn small" data-person="${p.id}">Bearbeiten</button></span></li>`)}</ul>`
          : html`<p class="small muted">Noch niemand angelegt. Solange kein Konto einer Person gehört, sieht jedes gekoppelte Handy alles.</p>`}
        ${unassigned ? html`<div class="alert warning" style="margin:10px 0"><div><strong>${unassigned === 1 ? "Ein Handy ist" : `${unassigned} Handys sind`} keiner Person zugeordnet</strong>
          <p class="small">Solche Handys sehen nur die gemeinsamen Konten. Ordne sie unten unter „Mobile Geräte“ zu.</p></div></div>` : ""}
        ${store.persons.length > 1 ? html`
          <div class="section-head" style="margin-top:22px"><h2>Ausgleich</h2><button class="link-btn" id="st-add">Zahlung eintragen</button></div>
          ${sharing.balances.length ? html`<ul class="list">${sharing.balances.map((b) => html`<li class="row static">
            <span class="title">${b.from} schuldet ${b.to}</span><span class="sub">aus geteilten Ausgaben, abzüglich eingetragener Zahlungen</span>
            <span class="amount">${money(b.cents)}</span></li>`)}</ul>`
            : html`<p class="small muted">${sharing.items.length ? "Alles ausgeglichen." : "Noch nichts geteilt. Öffne unter Umsätze eine Ausgabe von einem eigenen Konto und wähle „Mit dem Haushalt teilen“."}</p>`}
          ${sharing.items.length ? html`<p class="small muted" style="margin-top:10px">Zuletzt geteilt: ${sharing.items.slice(0, 5).map((i) => `${i.label} ${money(i.total_cents)} (${i.payer}, ${dShort(i.booking_date)})`).join("; ")}.</p>` : ""}
          ${sharing.settlements.length ? html`<ul class="list">${sharing.settlements.slice(0, 5).map((x) => html`<li class="row static">
            <span class="title">${x.from} an ${x.to}</span><span class="sub">${dFull(x.on_date)}${x.note ? ` · ${x.note}` : ""}</span>
            <span class="amount" style="display:flex;gap:6px;align-items:center">${money(x.cents)}<button class="btn small" data-st-del="${x.id}">Entfernen</button></span></li>`)}</ul>` : ""}` : ""}
      </section>
      <section class="section">
        <div class="section-head">
          <h2>Mobile Geräte</h2>
          <button class="link-btn" id="mobile-pair">Gerät koppeln</button>
        </div>
        ${store.persons.length ? html`<label class="field"><span>Das nächste Handy gehört</span><select id="mobile-pair-person"><option value="">Noch niemandem</option>${store.persons.map((p) => html`<option value="${p.id}">${p.name}</option>`)}</select></label>` : ""}
        <p class="small muted">Hier verwaltest du die Geräte, die auf Kassensturz Mobile zugreifen dürfen. Ein Pairing-Code ist fünf Minuten gültig und kann nur einmal verwendet werden.</p>
        ${s.options.mobile_server_url ? html`<p class="small muted">Mobile-Adresse für QR-Pairing: <code>${s.options.mobile_server_url}</code></p>` : html`<p class="small muted">Für QR-Pairing muss in den Home-Assistant-App-Optionen die externe HTTPS-Adresse als <code>mobile_server_url</code> hinterlegt sein. Ohne diese Einstellung bleibt die manuelle Code-Eingabe verfügbar.</p>`}
        <div id="mobile-pair-result" aria-live="polite"></div>
        <div id="mobile-device-list">
          ${devices.items.length ? html`<ul class="list">${devices.items.map((d) => html`
            <li class="row static">
              <span class="title">${d.name}</span>
              <span class="sub">${d.revoked_at ? "Widerrufen" : "Aktiv"} · hinzugefügt ${d.created_at ? dFull(d.created_at.slice(0, 10)) : "–"}${d.last_used_at ? ` · zuletzt aktiv ${dFull(d.last_used_at.slice(0, 10))}` : ""}</span>
              <span class="amount" style="display:flex;gap:6px;align-items:center">${!d.revoked_at && store.persons.length ? html`<select data-mobile-person="${d.id}" aria-label="Person für ${d.name}"><option value="">Niemand</option>${store.persons.map((p) => html`<option value="${p.id}" ${p.id === d.person_id ? raw("selected") : ""}>${p.name}</option>`)}</select>` : ""}${!d.revoked_at ? html`<button class="btn small danger" data-mobile-revoke="${d.id}">Widerrufen</button>` : html`<span class="small muted">Gesperrt</span>`}</span>
            </li>` )}</ul>` : html`<p class="small muted">Noch keine gekoppelten Geräte.</p>`}
        </div>
      </section>
      <section class="section">
        <div class="section-head"><h2>Änderungen</h2>${changes.total > changes.items.length ? html`<button class="link-btn" id="chg-all">Alle ${changes.total} ansehen</button>` : ""}</div>
        ${changes.items.length ? changeList(changes.items) : html`<p class="small muted">Noch nichts geändert.</p>`}
        <p class="small muted">Wer wann was geändert hat, in Home Assistant oder am Handy. Bankabrufe und was Kassensturz von selbst erledigt, stehen nicht darin. Einträge bleiben gut ein Jahr.</p>
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
        <div class="section-head"><h2>Zustand</h2></div>
        <div id="health-box"></div>
      </section>
      <section class="section">
        <div class="section-head"><h2>Daten</h2></div>
        <div class="actions" style="margin-top:0">
          <a class="btn small" href="api/export.csv" download>Alle Buchungen als CSV</a>
          <a class="btn small" href="api/umzug/archive" download>Vollständige Sicherung</a>
          <a class="btn small" href="api/umzug/export" download>Nur Datenbank</a>
          <button class="btn small" id="d-recat">Alles neu kategorisieren</button>
          ${store.state.demo ? html`<button class="btn small danger" id="d-demo-off">Beispieldaten entfernen</button>` : html`<button class="btn small" id="d-demo">Beispieldaten laden</button>`}
        </div>
        <p class="small muted" style="margin-top:14px">Kassensturz ${s.options ? store.state.version : ""}. Alle Daten liegen nur auf diesem Home-Assistant-Gerät.</p>
      </section>
    </div></div>`.s;
  drawTax($("#tax-box"));
  drawWarranties($("#warranty-box"));
  drawHealth($("#health-box"));
  $("#mobile-pair").onclick = async () => {
    const button = $("#mobile-pair");
    button.disabled = true;
    try {
      const owner = $("#mobile-pair-person");
      const pairing = await api("mobile/pairings", { method: "POST", body: owner ? { person_id: Number(owner.value) || null } : undefined });
      $("#mobile-pair-result").innerHTML = html`
        <div class="note" style="margin:12px 0" role="status">
          <strong>Einmaliger Pairing-Code${pairing.person_id ? ` für ${personName(pairing.person_id)}` : ""}</strong>
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
      toast(err.message, { error: true });
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
      toast(err.message, { error: true });
    }
  }));
  $("#p-add").onclick = () => personSheet();
  if ($("#chg-all")) $("#chg-all").onclick = () => changesSheet();
  bindCalendar($("#cal-box"));
  if ($("#st-add")) $("#st-add").onclick = () => settlementSheet(sharing.balances[0]);
  $$("[data-st-del]", view).forEach((button) => confirmButton(button, "Wirklich entfernen?", async () => {
    try { await api(`household/settlements/${button.dataset.stDel}`, { method: "DELETE" }); toast("Zahlung entfernt"); } catch (e) { toast(e.message, { error: true }); }
    rerender();
  }));
  on(view, "[data-person]", "click", (_e, el) => personSheet(store.persons.find((x) => x.id === Number(el.dataset.person))));
  on(view, "[data-mobile-person]", "change", async (_e, el) => {
    try {
      await api(`mobile/devices/${encodeURIComponent(el.dataset.mobilePerson)}`, { method: "PATCH", body: { person_id: Number(el.value) || null } });
      toast("Zuordnung gespeichert");
    } catch (err) { toast(err.message, { error: true }); }
    rerender();
  });
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

export function personSheet(person) {
  const sh = openSheet(html`${sheetHead(person ? person.name : "Person hinzufügen")}
    <label class="field"><span>Name</span><input class="input" id="pe-name" value="${person ? person.name : ""}" maxlength="40" ${person ? "" : raw("autofocus")}></label>
    <label class="check"><input type="checkbox" id="pe-child" ${person && person.is_child ? raw("checked") : ""}><span>Kind
      <span class="muted small">Ein Kind sieht in der App nur sein Taschengeld-Konto und kann nichts ändern.</span></span></label>
    ${person ? html`<label class="field"><span>Anteil an geteilten Ausgaben</span><input class="input" id="pe-weight" inputmode="numeric" value="${person.share_weight}"></label>
      <p class="small muted" style="margin-top:-6px">Gleiche Zahlen heißen: zu gleichen Teilen. 60 und 40 teilen im Verhältnis 60 zu 40. Mit 0 trägt die Person nichts mit, etwa ein Kind.</p>
      <label class="field"><span>Benachrichtigungsdienst</span><input class="input" id="pe-notify" value="${person.notify_service || ""}" placeholder="notify.mobile_app_handy" autocomplete="off" autocapitalize="off" spellcheck="false"></label>
      <p class="small muted" style="margin-top:-6px">Neue Buchungen auf eigenen Konten dieser Person gehen nur an diesen Dienst, Buchungen auf gemeinsamen Konten an alle. Bleibt das Feld leer, gilt der Dienst aus der Konfiguration der App.</p>`
      : html`<p class="small muted" style="margin-top:-6px">Danach ordnest du unter „Konten“ zu, welche Konten ihr gehören, und koppelst ihr Handy.</p>`}
    <div class="actions"><button class="btn primary" id="pe-save">${person ? "Speichern" : "Anlegen"}</button>
      ${person ? html`<button class="btn danger" id="pe-del">Person entfernen</button>` : ""}</div>`.s);
  $("#pe-save", sh.el).onclick = async () => {
    const body = { name: $("#pe-name", sh.el).value, is_child: $("#pe-child", sh.el).checked };
    if (person) {
      const weight = $("#pe-weight", sh.el).value.trim();
      if (!/^\d{1,4}$/.test(weight)) { toast("Der Anteil muss eine ganze Zahl sein."); return; }
      // Wird jemand zum Kind, trägt es von geteilten Ausgaben zunächst nichts.
      body.share_weight = body.is_child && !person.is_child ? 0 : Number(weight);
      body.notify_service = $("#pe-notify", sh.el).value.trim() || null;
    }
    try {
      if (person) await api(`persons/${person.id}`, { method: "PATCH", body }); else await api("persons", { method: "POST", body });
      sh.close(); toast("Gespeichert"); rerender();
    } catch (e) { toast(e.message, { error: true }); }
  };
  if (person) confirmButton($("#pe-del", sh.el), "Wirklich entfernen?", async () => {
    try { await api(`persons/${person.id}`, { method: "DELETE" }); sh.close(); toast("Person entfernt"); rerender(); } catch (e) { toast(e.message, { error: true }); }
  });
}

export function settlementSheet(open) {
  const option = (selected) => store.persons.map((p) => html`<option value="${p.id}" ${p.id === selected ? raw("selected") : ""}>${p.name}</option>`);
  const sh = openSheet(html`${sheetHead("Zahlung eintragen")}
    <p class="small muted">Hat jemand seinen Anteil überwiesen oder bar gegeben, trägst du das hier ein. Kassensturz bucht dabei nichts um.</p>
    <div class="field-row">
      <label class="field"><span>Von</span><select id="st-from">${option(open ? open.from_id : store.persons[0].id)}</select></label>
      <label class="field"><span>An</span><select id="st-to">${option(open ? open.to_id : store.persons[1].id)}</select></label>
    </div>
    <label class="field"><span>Betrag</span><input class="input" id="st-cents" inputmode="decimal" value="${open ? toInput(open.cents) : ""}" placeholder="0,00"></label>
    <label class="field"><span>Notiz</span><input class="input" id="st-note" maxlength="120"></label>
    <div class="actions"><button class="btn primary" id="st-save">Eintragen</button></div>`.s);
  $("#st-save", sh.el).onclick = async () => {
    const body = { from_person_id: Number($("#st-from", sh.el).value), to_person_id: Number($("#st-to", sh.el).value),
      cents: Math.abs(parseMoney($("#st-cents", sh.el).value) || 0), note: $("#st-note", sh.el).value };
    try { await api("household/settlements", { method: "POST", body }); sh.close(); toast("Zahlung eingetragen"); rerender(); } catch (e) { toast(e.message, { error: true }); }
  };
}

export function ruleSheet() {
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
    catch (e) { toast(e.message, { error: true }); }
  };
}

export function categorySheet() {
  const sh = openSheet(html`${sheetHead("Unterkategorie hinzufügen")}
    <label class="field"><span>Name</span><input class="input" id="ka-name" autofocus></label>
    <label class="field"><span>Gehört zu</span><select id="ka-parent">${topCats().filter((c) => c.kind !== "transfer").map((c) => html`<option value="${c.id}">${c.name}</option>`)}</select></label>
    <div class="actions"><button class="btn primary" id="ka-save">Hinzufügen</button></div>`.s);
  $("#ka-save", sh.el).onclick = async () => {
    try { await api("categories", { method: "POST", body: { name: $("#ka-name", sh.el).value, parent_id: Number($("#ka-parent", sh.el).value) } }); sh.close(); toast("Kategorie hinzugefügt"); rerender(); }
    catch (e) { toast(e.message, { error: true }); }
  };
}
