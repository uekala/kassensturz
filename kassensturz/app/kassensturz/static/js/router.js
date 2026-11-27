// Kassensturz – Oberfläche, router. Aufgeteilt aus app.js; Exporte und Importe zwischen den Modulen.

import { renderBudgets } from "./budgets.js";
import { $, $$, ICON, api, html, loadBase, raw, sheetStack, store, toast } from "./core.js";
import { renderSettings } from "./einstellungen.js";
import { pickImportFile } from "./import.js";
import { bankChooser, renderAccounts } from "./konten.js";
import { renderOverview } from "./uebersicht.js";
import { renderTransactions } from "./umsaetze.js";
import { renderContracts } from "./vertraege.js";

/* ------------------------------------------------------------------ Router */
export const routes = {
  "": renderOverview, umsaetze: renderTransactions, vertraege: renderContracts, budgets: renderBudgets,
  konten: renderAccounts, einstellungen: renderSettings,
};
export const TAB_FOR = { "": "uebersicht", umsaetze: "umsaetze", vertraege: "vertraege", budgets: "budgets", konten: "konten" };
export function parseHash() {
  const h = location.hash.replace(/^#\/?/, "");
  const [path, qs] = h.split("?");
  return { path: path || "", params: Object.fromEntries(new URLSearchParams(qs || "")) };
}
export function go(path, params) {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  location.hash = "#/" + path + qs;
}
export let renderSeq = 0;
export async function route() {
  const { path, params } = parseHash();
  const tab = TAB_FOR[path];
  $$(".tabs a").forEach((a) => { if (a.dataset.tab === tab) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
  $(".settings-link").classList.toggle("active", path === "einstellungen");
  const view = $("#view");
  const seq = ++renderSeq;
  try {
    await loadBase();
    if (seq !== renderSeq) return;
    if (!store.state.accounts && !["konten", "einstellungen"].includes(path)) {
      renderEmpty(view);
      return;
    }
    await (routes[path] || renderOverview)(view, params, seq);
  } catch (err) {
    if (seq !== renderSeq) return;
    view.innerHTML = html`<div class="empty"><h2>Das hat nicht geklappt</h2><p class="muted">${err.message}</p><button class="btn" id="retry">Neu laden</button></div>`.s;
    $("#retry").onclick = route;
  }
}
window.addEventListener("hashchange", () => {
  window.scrollTo(0, 0);
  // Ein offenes Fenster gehört zur alten Seite.
  [...sheetStack].forEach((s) => s.close());
  route();
});
export const rerender = () => route();

/* ------------------------------------------------------------------ Leerer Start */
export function renderEmpty(view) {
  view.innerHTML = html`
    <section class="empty">
      <h1>Noch keine Konten</h1>
      <p class="muted">Lade einen Kontoauszug als Datei hoch oder verbinde dein Girokonto direkt per FinTS. Alles bleibt auf deinem Home Assistant.</p>
      <div class="start-options">
        <button class="start-option" id="start-file">${raw(ICON.file)}<div><strong>Kontoauszug-Datei importieren</strong>
          <span>CSV, CAMT oder MT940 – von Sparkasse, Volksbank, ING, DKB, comdirect, N26, Revolut, PayPal, Amex und anderen.</span></div></button>
        <button class="start-option" id="start-bank">${raw(ICON.bank)}<div><strong>Bank verbinden</strong>
          <span>Umsätze automatisch abrufen – per Open Banking (auch N26, Revolut) oder FinTS, mit Freigabe in deiner Banking-App.</span></div></button>
        <button class="start-option" id="start-demo">${raw(ICON.play)}<div><strong>Mit Beispieldaten ausprobieren</strong>
          <span>Sieben Monate erfundene Buchungen. Mit einem Klick wieder entfernt.</span></div></button>
      </div>
    </section>`.s;
  $("#start-file").onclick = () => pickImportFile();
  $("#start-bank").onclick = async () => bankChooser(await api("eb"));
  $("#start-demo").onclick = async () => {
    const btn = $("#start-demo");
    btn.disabled = true;
    try {
      await api("demo", { method: "POST" });
      toast("Beispieldaten geladen");
      rerender();
    } catch (err) {
      btn.disabled = false;
      toast(err.message, { error: true });
    }
  };
}
