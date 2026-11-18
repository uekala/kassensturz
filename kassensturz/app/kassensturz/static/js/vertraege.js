// Kassensturz – Oberfläche, vertraege. Aufgeteilt aus app.js; Exporte und Importe zwischen den Modulen.

import { $, ICON, NF0, api, dFull, dShort, html, money, on, openSheet, parseMoney, raw, relDay, sheetHead, store, toast, todayIso } from "./core.js";
import { renderSeq, rerender } from "./router.js";

/* ------------------------------------------------------------------ Verträge */
export async function renderContracts(view, _params, seq) {
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

export function contractSheet(c) {
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

export async function letterSheet(c, mode) {
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

export function manualContractSheet(intervals) {
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
