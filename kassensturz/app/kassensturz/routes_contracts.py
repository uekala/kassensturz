"""HTTP-Routen: Verträge und Kündigungen. Aus main.py ausgelagert; main.py bindet sie ein."""
from __future__ import annotations

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Body

from . import analytics, contracts, letters
from .db import get_db, now_iso
from .web import _changed, _err

log = logging.getLogger("kassensturz")
router = APIRouter()

# --- Verträge -------------------------------------------------------------------------------

CONTRACT_FIELDS = ("name", "status", "customer_no", "provider_address", "provider_email", "contract_end", "notice_months", "notes",
                   "cancel_effective", "cancelled_on", "category_id", "amount_cents", "interval", "next_due", "match_pattern")


@router.get("/api/contracts")
def list_contracts():
    db = get_db()
    cons = contracts.list_contracts(db)
    today = date.today()
    running = [c for c in cons if c["status"] != "ignored" and contracts.is_running(c, today)]
    pending_cancellations = db.query(
        "SELECT e.id, e.contract_key, e.mode, e.status, e.prepared_at, e.handed_off_at, "
        "e.user_confirmed_sent_at, c.name AS contract_name "
        "FROM cancellation_events e JOIN contracts c ON c.key = e.contract_key "
        "WHERE e.status IN ('prepared', 'handed_off', 'sent') "
        "AND c.status NOT IN ('cancelled', 'ignored') "
        "ORDER BY e.prepared_at ASC, e.id ASC"
    )
    return {
        "items": cons,
        "pending_cancellations": pending_cancellations,
        "fixed_monthly_cents": analytics.fixed_costs_monthly(running),
        "income_monthly_cents": sum(c["monthly_cents"] for c in running if c["kind"] == "income"),
        "intervals": [i[0] for i in contracts.INTERVALS],
    }


@router.patch("/api/contracts/{key:path}")
def update_contract(key: str, body: dict = Body(...)):
    db = get_db()
    c = db.one("SELECT * FROM contracts WHERE key = ?", (key,))
    if not c:
        _err(404, "Vertrag nicht gefunden.")
    data = {k: (body[k] if body[k] != "" else None) for k in CONTRACT_FIELDS if k in body}
    if body.get("price_change_ack"):
        data["price_change_ack"] = c["amount_cents"]
    if data.get("status") == "cancelled" and not c["cancelled_on"] and "cancelled_on" not in data:
        data["cancelled_on"] = date.today().isoformat()
    data["updated"] = now_iso()
    db.update("contracts", "key", key, data)
    _changed()
    return contracts.enrich(db.one("SELECT * FROM contracts WHERE key = ?", (key,)))


@router.post("/api/contracts")
def create_contract(body: dict = Body(...)):
    db = get_db()
    name = (body.get("name") or "").strip()
    if not name or not body.get("amount_cents") or body.get("interval") not in contracts.INTERVAL_BY_NAME:
        _err(400, "Name, Betrag und Rhythmus sind nötig.")
    kind = "income" if int(body["amount_cents"]) > 0 else "expense"
    key = "manual:" + uuid.uuid4().hex[:10]
    db.insert("contracts", {
        "key": key, "name": name[:60], "counterparty": name[:60], "kind": kind, "interval": body["interval"],
        "amount_cents": int(body["amount_cents"]), "next_due": body.get("next_due") or date.today().isoformat(),
        "category_id": body.get("category_id"), "account_id": body.get("account_id"), "status": "confirmed", "active": 1,
        "manual": 1, "match_pattern": (body.get("match_pattern") or "").strip() or None, "count": 0, "updated": now_iso(),
    })
    _changed()
    return {"key": key}


@router.delete("/api/contracts/{key:path}")
def delete_contract(key: str):
    db = get_db()
    c = db.one("SELECT * FROM contracts WHERE key = ?", (key,))
    if not c:
        _err(404, "Vertrag nicht gefunden.")
    if c["manual"]:
        db.execute("UPDATE transactions SET contract_key = NULL WHERE contract_key = ?", (key,))
        db.execute("DELETE FROM contracts WHERE key = ?", (key,))
    else:
        db.update("contracts", "key", key, {"status": "ignored"})
    _changed()
    return {"ok": True}




def _provider_key(contract: dict) -> str:
    import hashlib
    import re
    name = (contract.get("counterparty") or contract.get("name") or "").strip().casefold()
    normalized = re.sub(r"[^a-z0-9]+", "-", name).strip("-") or "unknown"
    return normalized[:48] + "-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:10]


@router.get("/api/contracts/{key:path}/cancellation-contact")
def cancellation_contact_get(key: str):
    db = get_db()
    contract = db.one("SELECT * FROM contracts WHERE key = ?", (key,))
    if not contract:
        _err(404, "Vertrag nicht gefunden.")
    provider_key = _provider_key(contract)
    contact = db.one("SELECT * FROM provider_contacts WHERE provider_key = ?", (provider_key,))
    sources = db.query(
        "SELECT id, source_type, title, url, checked_at, excerpt FROM provider_contact_sources "
        "WHERE provider_key = ? ORDER BY checked_at DESC, id DESC", (provider_key,)
    )
    return {"provider_key": provider_key, "provider_name": contract.get("counterparty") or contract.get("name"),
            "contact": contact, "sources": sources}


@router.put("/api/contracts/{key:path}/cancellation-contact")
def cancellation_contact_put(key: str, body: dict = Body(...)):
    from urllib.parse import urlparse

    db = get_db()
    contract = db.one("SELECT * FROM contracts WHERE key = ?", (key,))
    if not contract:
        _err(404, "Vertrag nicht gefunden.")
    provider_key = _provider_key(contract)

    def clean(value, limit):
        value = (value or "").strip()
        return value[:limit] or None

    email = clean(body.get("email"), 254)
    if email and ("@" not in email or any(ch.isspace() for ch in email)):
        _err(400, "Die E-Mail-Adresse ist ungültig.")
    urls = {}
    for field in ("cancellation_url", "contact_url"):
        value = clean(body.get(field), 2048)
        if value:
            parsed = urlparse(value)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                _err(400, "Quellen und Kontaktseiten müssen gültige HTTPS-URLs ohne Zugangsdaten sein.")
        urls[field] = value
    checked_at = now_iso()
    # Nur der ausdrückliche Bestätigungs-Endpunkt darf status="verified" setzen.
    status = body.get("status") if body.get("status") in ("unverified", "partially_verified", "conflicting") else "unverified"
    sources = body.get("sources") or []
    if not isinstance(sources, list) or len(sources) > 20:
        _err(400, "Es sind höchstens 20 Quellen erlaubt.")
    with db.tx(immediate=True):
        db.execute(
            "INSERT INTO provider_contacts(provider_key, provider_name, email, postal_address, cancellation_url, contact_url, status, checked_at, notes, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(provider_key) DO UPDATE SET provider_name=excluded.provider_name, "
            "email=excluded.email, postal_address=excluded.postal_address, cancellation_url=excluded.cancellation_url, "
            "contact_url=excluded.contact_url, status=excluded.status, checked_at=excluded.checked_at, notes=excluded.notes, updated_at=excluded.updated_at",
            (provider_key, contract.get("counterparty") or contract.get("name") or "Unbekannt", email,
             clean(body.get("postal_address"), 1000), urls["cancellation_url"], urls["contact_url"], status,
             checked_at, clean(body.get("notes"), 2000), checked_at)
        )
        for source in sources:
            if not isinstance(source, dict):
                _err(400, "Eine Quellenangabe ist ungültig.")
            title = clean(source.get("title"), 200)
            url = clean(source.get("url"), 2048)
            parsed = urlparse(url or "")
            if not title or parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                _err(400, "Jede Quelle benötigt Titel und eine gültige HTTPS-URL.")
            db.execute(
                "INSERT INTO provider_contact_sources(provider_key, source_type, title, url, checked_at, excerpt) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(provider_key, url) DO UPDATE SET title=excluded.title, "
                "source_type=excluded.source_type, checked_at=excluded.checked_at, excerpt=excluded.excerpt",
                (provider_key, clean(source.get("source_type"), 30) or "official", title, url, checked_at,
                 clean(source.get("excerpt"), 500))
            )
    return cancellation_contact_get(key)




@router.post("/api/contracts/{key:path}/cancellation-contact/confirm")
def cancellation_contact_confirm(key: str, body: dict = Body(...)):
    """Speichert einen vom Nutzer ausdrücklich geprüften Kontaktbeleg."""
    from urllib.parse import urlparse

    db = get_db()
    contract = db.one("SELECT * FROM contracts WHERE key = ?", (key,))
    if not contract:
        _err(404, "Vertrag nicht gefunden.")
    if body.get("user_confirmed") is not True:
        _err(400, "Bitte bestätige ausdrücklich, dass du die Angaben auf der Anbieterquelle selbst geprüft hast.")

    source_url = (body.get("source_url") or "").strip()
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        _err(400, "Die bestätigte Quelle muss eine gültige HTTPS-Adresse sein.")
    provider_key = _provider_key(contract)
    source = db.one(
        "SELECT id, title, url FROM provider_contact_sources WHERE provider_key = ? AND url = ?",
        (provider_key, source_url),
    )
    if not source:
        _err(400, "Die Quelle muss zuerst als Recherchequelle gespeichert werden.")

    email = (body.get("email") or "").strip()[:254] or None
    if email and ("@" not in email or any(ch.isspace() for ch in email)):
        _err(400, "Die E-Mail-Adresse ist ungültig.")
    address = (body.get("postal_address") or "").strip()[:1000] or None
    cancellation_url = (body.get("cancellation_url") or "").strip() or None
    if cancellation_url:
        cp = urlparse(cancellation_url)
        if cp.scheme != "https" or not cp.hostname or cp.username or cp.password or cp.port not in (None, 443):
            _err(400, "Der Kündigungslink muss eine gültige HTTPS-Adresse sein.")

    # Vorhandene Vertragsfelder nie stillschweigend überschreiben. Der Nutzer kann
    # Unterschiede im normalen Vertragseditor auflösen, nachdem er den Konflikt gesehen hat.
    if email and contract.get("provider_email") and contract["provider_email"].strip().lower() != email.lower():
        _err(409, "Im Vertrag ist bereits eine andere Anbieter-E-Mail hinterlegt. Bitte prüfe den Konflikt zuerst in den Vertragsdaten.")
    if address and contract.get("provider_address") and contract["provider_address"].strip() != address:
        _err(409, "Im Vertrag ist bereits eine andere Anbieteranschrift hinterlegt. Bitte prüfe den Konflikt zuerst in den Vertragsdaten.")

    checked_at = now_iso()
    with db.tx(immediate=True):
        db.execute(
            "INSERT INTO provider_contacts(provider_key, provider_name, email, postal_address, cancellation_url, contact_url, status, checked_at, notes, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(provider_key) DO UPDATE SET provider_name=excluded.provider_name, "
            "email=excluded.email, postal_address=excluded.postal_address, cancellation_url=excluded.cancellation_url, "
            "contact_url=excluded.contact_url, status=excluded.status, checked_at=excluded.checked_at, notes=excluded.notes, updated_at=excluded.updated_at",
            (provider_key, contract.get("counterparty") or contract.get("name") or "Unbekannt", email, address,
             cancellation_url, source_url, "verified", checked_at,
             "Vom Nutzer ausdrücklich auf der angegebenen Quelle geprüft und bestätigt.", checked_at)
        )
        db.execute(
            "UPDATE provider_contact_sources SET source_type = ?, checked_at = ?, excerpt = ? WHERE id = ?",
            ("user_confirmed", checked_at, "Nutzer hat diese Quelle und die übernommenen Kontaktangaben ausdrücklich geprüft.", source["id"])
        )
        updates = {}
        if email and not contract.get("provider_email"):
            updates["provider_email"] = email
        if address and not contract.get("provider_address"):
            updates["provider_address"] = address
        if updates:
            db.update("contracts", "key", key, updates)
    return {"ok": True, "contact": db.one("SELECT * FROM provider_contacts WHERE provider_key = ?", (provider_key,)),
            "contract_fields_updated": list(updates)}


@router.post("/api/contracts/{key:path}/cancellation-research")
def cancellation_research(key: str):
    from . import provider_research

    db = get_db()
    contract = db.one("SELECT * FROM contracts WHERE key = ?", (key,))
    if not contract:
        _err(404, "Vertrag nicht gefunden.")
    provider_name = (contract.get("counterparty") or contract.get("name") or "").strip()
    try:
        result = provider_research.search_provider(provider_name)
    except ValueError as exc:
        _err(400, str(exc))
    except Exception as exc:
        log.warning("Anbietersuche fehlgeschlagen: %s", exc)
        _err(502, "Die Anbietersuche ist momentan nicht verfügbar. Bitte später erneut versuchen.")
    return result

@router.post("/api/contracts/{key:path}/cancellation-source-check")
def cancellation_source_check(key: str, body: dict = Body(...)):
    from . import provider_research

    db = get_db()
    if not db.one("SELECT key FROM contracts WHERE key = ?", (key,)):
        _err(404, "Vertrag nicht gefunden.")
    url = (body.get("url") or "").strip()
    if len(url) > 2048:
        _err(400, "Die Quellen-URL ist zu lang.")
    try:
        return provider_research.inspect_public_https_url(url)
    except ValueError as exc:
        _err(400, str(exc))


@router.post("/api/contracts/{key:path}/cancellation-page-evidence")
def cancellation_page_evidence(key: str, body: dict = Body(...)):
    from . import provider_research

    db = get_db()
    if not db.one("SELECT key FROM contracts WHERE key = ?", (key,)):
        _err(404, "Vertrag nicht gefunden.")
    url = (body.get("url") or "").strip()
    if len(url) > 2048:
        _err(400, "Die Quellen-URL ist zu lang.")
    try:
        return provider_research.fetch_public_page_evidence(url)
    except ValueError as exc:
        _err(400, str(exc))
    except RuntimeError as exc:
        _err(502, str(exc))


@router.get("/api/contracts/{key:path}/cancellation-events")
def cancellation_events_get(key: str):
    db = get_db()
    contract = db.one("SELECT key FROM contracts WHERE key = ?", (key,))
    if not contract:
        _err(404, "Vertrag nicht gefunden.")
    events = db.query(
        "SELECT id, mode, status, prepared_at, handed_off_at, user_confirmed_sent_at, provider_confirmed_at, aborted_at, notes "
        "FROM cancellation_events WHERE contract_key = ? ORDER BY prepared_at DESC, id DESC",
        (key,),
    )
    return {"items": events}

@router.post("/api/contracts/{key:path}/cancellation-events")
def cancellation_event_create(key: str, body: dict = Body(...)):
    db = get_db()
    contract = db.one("SELECT * FROM contracts WHERE key = ?", (key,))
    if not contract:
        _err(404, "Vertrag nicht gefunden.")
    provider_key = _provider_key(contract)
    mode = body.get("mode") if body.get("mode") in ("ordinary", "extraordinary", "withdrawal") else "ordinary"
    event_id = db.insert("cancellation_events", {
        "contract_key": key, "provider_key": provider_key, "mode": mode,
        "status": "prepared", "prepared_at": now_iso(),
        "notes": (body.get("notes") or "").strip()[:1000] or None,
    })
    return db.one("SELECT * FROM cancellation_events WHERE id = ?", (event_id,))


@router.post("/api/contracts/{key:path}/cancellation-events/{event_id}/handoff")
def cancellation_event_handoff(key: str, event_id: int):
    db = get_db()
    event = db.one("SELECT * FROM cancellation_events WHERE id = ? AND contract_key = ?", (event_id, key))
    if not event:
        _err(404, "Kündigungsvorgang nicht gefunden.")
    if event.get("status") != "prepared":
        _err(409, "Dieser Kündigungsvorgang wurde bereits übergeben oder weiterbearbeitet.")
    db.update("cancellation_events", "id", event_id, {"status": "handed_off", "handed_off_at": now_iso()})
    return db.one("SELECT * FROM cancellation_events WHERE id = ?", (event_id,))


@router.post("/api/contracts/{key:path}/cancellation-events/{event_id}/confirm-sent")
def cancellation_event_confirm_sent(key: str, event_id: int, body: dict = Body(...)):
    db = get_db()
    event = db.one("SELECT * FROM cancellation_events WHERE id = ? AND contract_key = ?", (event_id, key))
    if not event:
        _err(404, "Kündigungsvorgang nicht gefunden.")
    if body.get("user_confirmed_sent") is not True:
        _err(400, "Bitte bestätige ausdrücklich, dass du die Kündigung tatsächlich versendet hast.")
    if event.get("status") != "handed_off":
        _err(409, "Die Kündigung muss zuerst an die Mail-App übergeben worden sein.")
    db.update("cancellation_events", "id", event_id, {"status": "sent", "user_confirmed_sent_at": now_iso()})
    return db.one("SELECT * FROM cancellation_events WHERE id = ?", (event_id,))

@router.post("/api/contracts/{key:path}/cancellation-events/{event_id}/abort")
def cancellation_event_abort(key: str, event_id: int, body: dict = Body(...)):
    db = get_db()
    event = db.one("SELECT * FROM cancellation_events WHERE id = ? AND contract_key = ?", (event_id, key))
    if not event:
        _err(404, "Kündigungsvorgang nicht gefunden.")
    if body.get("user_confirmed_aborted") is not True:
        _err(400, "Bitte bestätige ausdrücklich, dass du diesen Kündigungsvorgang abbrechen möchtest.")
    if event.get("status") not in ("prepared", "handed_off"):
        _err(409, "Nur vorbereitete oder an die Mail-App übergebene Vorgänge können abgebrochen werden.")
    db.update("cancellation_events", "id", event_id, {"status": "aborted", "aborted_at": now_iso()})
    return db.one("SELECT * FROM cancellation_events WHERE id = ?", (event_id,))


@router.post("/api/contracts/{key:path}/cancellation-events/{event_id}/confirm-received")
def cancellation_event_confirm_received(key: str, event_id: int, body: dict = Body(...)):
    db = get_db()
    event = db.one("SELECT * FROM cancellation_events WHERE id = ? AND contract_key = ?", (event_id, key))
    if not event:
        _err(404, "Kündigungsvorgang nicht gefunden.")
    if body.get("user_confirmed_received") is not True:
        _err(400, "Bitte bestätige ausdrücklich den Erhalt einer Anbieterbestätigung.")
    if event.get("status") != "sent":
        _err(409, "Der Versand muss zuerst von dir bestätigt worden sein.")
    db.update("cancellation_events", "id", event_id, {"status": "provider_confirmed", "provider_confirmed_at": now_iso()})
    return db.one("SELECT * FROM cancellation_events WHERE id = ?", (event_id,))

@router.post("/api/letter")
def letter(body: dict = Body(...)):
    db = get_db()
    c = db.one("SELECT * FROM contracts WHERE key = ?", (body.get("key"),))
    if not c:
        _err(404, "Vertrag nicht gefunden.")
    return letters.build_letter(db, c, body.get("mode") or "ordentlich", body.get("date"))
