"""Änderungsprotokoll: wer im Haushalt wann was geändert hat.

Jede erfolgreiche Änderung über Home Assistant oder ein gekoppeltes Handy wird ein Eintrag: wann, wer,
was. Was im Hintergrund von selbst passiert (Bankabruf, Taschengeld, automatische Zuordnung), steht
nicht darin; das ist keine Änderung durch eine Person.

Wer: in Home Assistant der angemeldete Benutzer. Den Namen setzt der Supervisor nur bei Anfragen über
Ingress; nur dort wird er geglaubt. Am Handy die Person, der das Gerät gehört, sonst der Gerätename.

Was: ein Satz zur Route („Konto geändert“). Wo die Route mehr weiß, sagt sie es genauer
(„REWE, −23,40 € am 12.11.2026: Kategorie „Lebensmittel““). Was in Formularen steht, wird nie
mitgeschrieben: PINs, Schlüssel und TANs kommen so nie ins Protokoll.

Die Route legt ihre Einträge über ``note`` und ``subject`` ab; geschrieben wird erst, wenn die Anfrage
erfolgreich war (``finish``, aus der Middleware). Ohne laufende Anfrage, etwa in Hintergrundläufen,
tun ``note`` und ``subject`` nichts.
"""
from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import date, datetime, timedelta

from .db import Database, now_iso
from .util import euro

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
INGRESS_IP = "172.30.32.2"
KEEP_DAYS = 400
KEEP_ROWS = 20_000
MAX_TEXT = 300
MAX_NOTES = 20

# Was eine Route ändert, in einem Satz. Schlüssel: Methode und Pfad, wie die Route ihn deklariert.
LABELS: dict[tuple[str, str], str] = {
    ("POST", "/api/expected"): "Erwarteten Eingang angelegt",
    ("POST", "/api/expected/{item_id}/received"): "Erwarteten Eingang abgehakt",
    ("POST", "/api/expected/{item_id}/drop"): "Erwarteten Eingang abgelegt",
    ("POST", "/api/expected/{item_id}/reopen"): "Erwarteten Eingang wieder geöffnet",
    ("POST", "/api/projects"): "Projekt angelegt",
    ("POST", "/api/projects/unassign"): "Buchungen aus ihrem Projekt genommen",
    ("POST", "/api/projects/{project_id}"): "Projekt geändert",
    ("DELETE", "/api/projects/{project_id}"): "Projekt gelöscht",
    ("POST", "/api/projects/{project_id}/assign"): "Buchungen einem Projekt zugeordnet",
    ("POST", "/api/planned"): "Geplante Ausgabe angelegt",
    ("POST", "/api/planned/{item_id}"): "Geplante Ausgabe geändert",
    ("POST", "/api/planned/{item_id}/paid"): "Geplante Ausgabe abgehakt",
    ("POST", "/api/planned/{item_id}/drop"): "Geplante Ausgabe gestrichen",
    ("POST", "/api/planned/{item_id}/reopen"): "Geplante Ausgabe wieder geöffnet",
    ("POST", "/api/anomalies/ack"): "Auffälligkeit als geprüft ausgeblendet",
    ("PATCH", "/api/transactions/{tx_id}"): "Buchung geändert",
    ("POST", "/api/transactions/{tx_id}/receipts"): "Beleg hinzugefügt",
    ("DELETE", "/api/receipts/{receipt_id}"): "Beleg gelöscht",
    ("POST", "/api/transactions/{tx_id}/reset"): "Buchung wieder automatisch zugeordnet",
    ("PUT", "/api/transactions/{tx_id}/splits"): "Aufteilung einer Buchung geändert",
    ("POST", "/api/categories"): "Kategorie angelegt",
    ("PATCH", "/api/categories/{cid}"): "Kategorie geändert",
    ("DELETE", "/api/categories/{cid}"): "Kategorie gelöscht",
    ("DELETE", "/api/learned/{lid}"): "Gelernte Zuordnung gelöscht",
    ("POST", "/api/rules"): "Regel angelegt",
    ("PATCH", "/api/rules/{rid}"): "Regel geändert",
    ("DELETE", "/api/rules/{rid}"): "Regel gelöscht",
    ("POST", "/api/recategorize"): "Alle Buchungen neu zugeordnet",
    ("POST", "/api/persons"): "Person angelegt",
    ("PATCH", "/api/persons/{pid}"): "Person geändert",
    ("DELETE", "/api/persons/{pid}"): "Person entfernt",
    ("PUT", "/api/persons/{pid}/budgets/{cid}"): "Eigenes Budget geändert",
    ("PUT", "/api/transactions/{tx_id}/share"): "Ausgabe mit dem Haushalt geteilt",
    ("DELETE", "/api/transactions/{tx_id}/share"): "Teilen einer Ausgabe aufgehoben",
    ("POST", "/api/household/settlements"): "Ausgleichszahlung eingetragen",
    ("DELETE", "/api/household/settlements/{sid}"): "Ausgleichszahlung entfernt",
    ("POST", "/api/accounts"): "Konto angelegt",
    ("POST", "/api/accounts/{aid}/balance-check/reset"): "Hinweis zum Kontostand ausgeblendet",
    ("PATCH", "/api/accounts/{aid}"): "Konto geändert",
    ("POST", "/api/accounts/{aid}/balance"): "Kontostand eingetragen",
    ("DELETE", "/api/accounts/{aid}"): "Konto gelöscht",
    ("POST", "/api/import/commit"): "Datei importiert",
    ("POST", "/api/import/finanzguru/commit"): "Finanzguru-Export übernommen",
    ("POST", "/api/connections"): "Bankzugang angelegt",
    ("PATCH", "/api/connections/{cid}"): "Bankzugang geändert",
    ("POST", "/api/connections/{cid}/reset-tan"): "TAN-Verfahren eines Bankzugangs zurückgesetzt",
    ("DELETE", "/api/connections/{cid}"): "Bankzugang gelöscht",
    ("DELETE", "/api/connections/{cid}/pin"): "Gespeicherte PIN gelöscht",
    ("POST", "/api/connections/{cid}/sync"): "Bankabruf gestartet",
    ("PATCH", "/api/contracts/{key:path}"): "Vertrag geändert",
    ("POST", "/api/contracts"): "Vertrag angelegt",
    ("DELETE", "/api/contracts/{key:path}"): "Vertrag gelöscht",
    ("PUT", "/api/contracts/{key:path}/cancellation-contact"): "Kündigungsweg eines Vertrags eingetragen",
    ("POST", "/api/contracts/{key:path}/cancellation-contact/confirm"): "Kündigungsweg eines Vertrags bestätigt",
    ("POST", "/api/contracts/{key:path}/cancellation-page-evidence"): "Kündigungsseite eines Vertrags festgehalten",
    ("POST", "/api/contracts/{key:path}/cancellation-events"): "Kündigung begonnen",
    ("POST", "/api/contracts/{key:path}/cancellation-events/{event_id}/handoff"): "Kündigung übergeben",
    ("POST", "/api/contracts/{key:path}/cancellation-events/{event_id}/confirm-sent"): "Kündigung als verschickt markiert",
    ("POST", "/api/contracts/{key:path}/cancellation-events/{event_id}/abort"): "Kündigung abgebrochen",
    ("POST", "/api/contracts/{key:path}/cancellation-events/{event_id}/confirm-received"): "Kündigungsbestätigung eingetragen",
    ("POST", "/api/goals"): "Sparziel angelegt",
    ("PATCH", "/api/goals/{gid}"): "Sparziel geändert",
    ("DELETE", "/api/goals/{gid}"): "Sparziel gelöscht",
    ("PUT", "/api/settings"): "Einstellungen geändert",
    ("POST", "/api/demo"): "Beispieldaten geladen",
    ("DELETE", "/api/demo"): "Beispieldaten entfernt",
    ("POST", "/api/refresh"): "Aktualisieren angestoßen",
    ("PUT", "/api/eb/config"): "Open-Banking-Zugang eingerichtet",
    ("DELETE", "/api/eb/config"): "Open-Banking-Zugang entfernt",
    ("POST", "/api/eb/complete"): "Bank über Open Banking verbunden",
    ("POST", "/api/eb/sessions/{eb_id}/sync"): "Bankabruf gestartet",
    ("PATCH", "/api/eb/sessions/{eb_id}"): "Open-Banking-Verbindung geändert",
    ("DELETE", "/api/eb/sessions/{eb_id}"): "Open-Banking-Verbindung getrennt",
    ("DELETE", "/api/inbox/{filename}"): "Datei aus dem Eingangsordner gelöscht",
    ("POST", "/api/calendar"): "Zahlungskalender",
    ("POST", "/api/mobile/pairings"): "Kopplungscode für ein Handy erstellt",
    ("DELETE", "/api/mobile/devices/{device_id}"): "Handy widerrufen",
    ("PATCH", "/api/mobile/devices/{device_id}"): "Handy einer Person zugeordnet",
    # Vom Handy
    ("POST", "/api/v1/sync"): "Bankabruf gestartet",
    ("POST", "/api/v1/banks/renew/complete"): "Bankfreigabe erneuert",
    ("POST", "/api/v1/accounts"): "Bargeld-Konto angelegt",
    ("PUT", "/api/v1/accounts/{account_id}/value"): "Wert eingetragen",
    ("POST", "/api/v1/transactions"): "Buchung angelegt",
    ("PATCH", "/api/v1/transactions/{tx_id}"): "Buchung geändert",
    ("DELETE", "/api/v1/transactions/{tx_id}"): "Buchung gelöscht",
    ("POST", "/api/v1/transactions/{tx_id}/receipts"): "Beleg hinzugefügt",
    ("DELETE", "/api/v1/receipts/{receipt_id}"): "Beleg gelöscht",
    ("PUT", "/api/v1/transactions/{tx_id}/share"): "Ausgabe mit dem Haushalt geteilt",
    ("DELETE", "/api/v1/transactions/{tx_id}/share"): "Teilen einer Ausgabe aufgehoben",
    ("POST", "/api/v1/household/settlements"): "Ausgleichszahlung eingetragen",
    ("PUT", "/api/v1/budgets/{category_id}"): "Budget geändert",
    ("PUT", "/api/v1/budgets/own/{category_id}"): "Eigenes Budget geändert",
    ("PATCH", "/api/v1/contracts/{key:path}"): "Vertrag geändert",
    ("POST", "/api/v1/alerts/ack"): "Auffälligkeit als geprüft ausgeblendet",
    ("PUT", "/api/v1/transactions/{tx_id}/project"): "Projekt einer Buchung geändert",
    ("POST", "/api/v1/planned"): "Geplante Ausgabe angelegt",
    ("POST", "/api/v1/planned/{item_id}/{action}"): "Geplante Ausgabe abgehakt oder gestrichen",
    ("POST", "/api/v1/expected"): "Erwarteten Eingang angelegt",
    ("POST", "/api/v1/expected/{item_id}/{action}"): "Erwarteten Eingang abgehakt oder abgelegt",
}

# Anfragen, die nichts ändern, was jemand nachlesen muss: Anmeldung, Vorschauen, Prüfungen, TAN-Antworten.
SKIP: frozenset[tuple[str, str]] = frozenset({
    ("POST", "/api/v1/pair"), ("POST", "/api/v1/auth/refresh"), ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/news/seen"), ("POST", "/api/v1/contracts/{key:path}/letter"),
    ("POST", "/api/jobs/{job_id}/answer"), ("POST", "/api/jobs/{job_id}/cancel"),
    ("POST", "/api/import/analyze"), ("POST", "/api/import/remap"), ("POST", "/api/import/finanzguru/preview"),
    ("POST", "/api/inbox/analyze"), ("POST", "/api/inbox/scan"), ("POST", "/api/health/backup-check"),
    ("POST", "/api/contracts/{key:path}/cancellation-research"),
    ("POST", "/api/contracts/{key:path}/cancellation-source-check"),
    ("POST", "/api/letter"), ("POST", "/api/eb/auth"), ("POST", "/api/v1/banks/renew"),
})

_REQUEST: ContextVar[dict | None] = ContextVar("kassensturz_audit", default=None)


def _header(request, name: str) -> str:
    """Kopfzeile als Text. Der Supervisor schickt Namen als UTF-8; Starlette liest sie als Latin-1."""
    value = (request.headers.get(name) or "").strip()
    try:
        value = value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return " ".join(value.split())[:60]


def begin(request) -> tuple[dict, Token]:
    """Beginnt eine Anfrage. Wer sie stellt, steht vorerst nach der Herkunft fest; ein Handy meldet sich
    erst mit seinem Schlüssel an und trägt sich dann über ``set_device`` ein."""
    peer = request.client.host if request.client else ""
    if request.url.path.startswith("/api/v1/"):
        actor, kind = "Handy", "phone"
    elif peer == INGRESS_IP:
        actor = (_header(request, "x-remote-user-display-name") or _header(request, "x-remote-user-name")
                 or "Home Assistant")
        kind = "ha"
    else:
        actor, kind = "Lokal", "local"
    holder = {"actor": actor, "kind": kind, "person_id": None, "notes": [], "subject": None, "skip": False}
    return holder, _REQUEST.set(holder)


def end(token: Token) -> None:
    _REQUEST.reset(token)


def set_device(db: Database, device) -> None:
    """Das Handy hat sich angemeldet: seine Person, sonst sein Name."""
    holder = _REQUEST.get()
    if holder is None:
        return
    name = None
    if device.person_id is not None:
        name = db.scalar("SELECT name FROM persons WHERE id = ?", (device.person_id,))
    holder.update({"actor": (name or device.name or "Handy")[:60], "kind": "phone", "person_id": device.person_id})


def note(text: str, account_id: int | None = None) -> None:
    """Ein genauer Eintrag statt des Satzes zur Route. Mehrere Einträge je Anfrage sind möglich."""
    holder = _REQUEST.get()
    if holder is not None and text and len(holder["notes"]) < MAX_NOTES:
        holder["notes"].append((" ".join(str(text).split())[:MAX_TEXT], account_id))


def subject(name: str | None, account_id: int | None = None) -> None:
    """Worum es ging, angehängt an den Satz zur Route: „Projekt angelegt: Urlaub 2027“."""
    holder = _REQUEST.get()
    if holder is not None and name:
        holder["subject"] = (" ".join(str(name).split())[:80], account_id)


def skip() -> None:
    """Die Anfrage hat nichts geändert, etwa ein Speichern ohne neue Werte."""
    holder = _REQUEST.get()
    if holder is not None:
        holder["skip"] = True


def finish(db: Database, holder: dict, method: str, route_path: str) -> int:
    """Schreibt die Einträge einer erfolgreichen Anfrage. Gibt zurück, wie viele es waren."""
    key = (method.upper(), route_path)
    if key in SKIP or holder["skip"]:
        return 0
    rows = list(holder["notes"])
    if not rows:
        label = LABELS.get(key, "Sonstige Änderung")
        if holder["subject"]:
            rows = [(f"{label}: {holder['subject'][0]}", holder["subject"][1])]
        else:
            rows = [(label, None)]
    at = now_iso()
    for text, account_id in rows:
        db.insert("audit_log", {"at": at, "actor": holder["actor"], "actor_kind": holder["kind"],
                                "person_id": holder["person_id"], "text": text, "account_id": account_id,
                                "route": f"{key[0]} {key[1]}"[:120]})
    return len(rows)


def tx_label(tx: dict) -> str:
    """Eine Buchung in wenigen Worten: Gegenseite, Betrag, Tag."""
    name = " ".join(str(tx.get("counterparty") or tx.get("purpose") or "Buchung").split())[:40]
    try:
        day = date.fromisoformat(str(tx.get("booking_date"))[:10]).strftime("%d.%m.%Y")
    except ValueError:
        day = str(tx.get("booking_date") or "")
    return f"{name}, {euro(tx.get('amount_cents'))} am {day}"


def listing(db: Database, offset: int = 0, limit: int = 50, actor: str | None = None) -> dict:
    """Die jüngsten Einträge zuerst, auf Wunsch nur von einer Person oder einem Gerät."""
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    where, params = ("WHERE actor = ?", (actor,)) if actor else ("", ())
    items = db.query(f"SELECT id, at, actor, actor_kind, text FROM audit_log {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                     (*params, limit, offset))
    total = db.scalar(f"SELECT COUNT(*) FROM audit_log {where}", params)
    actors = [r["actor"] for r in db.query("SELECT actor, MAX(id) AS last FROM audit_log GROUP BY actor ORDER BY last DESC")]
    return {"items": items, "total": total, "actors": actors}


def prune(db: Database, today: date | None = None) -> None:
    """Hält das Protokoll klein: höchstens gut ein Jahr und 20.000 Einträge."""
    cutoff = datetime.combine((today or date.today()) - timedelta(days=KEEP_DAYS), datetime.min.time()).isoformat()
    db.execute("DELETE FROM audit_log WHERE at < ?", (cutoff,))
    db.execute("DELETE FROM audit_log WHERE id <= (SELECT id FROM audit_log ORDER BY id DESC LIMIT 1 OFFSET ?)", (KEEP_ROWS,))
