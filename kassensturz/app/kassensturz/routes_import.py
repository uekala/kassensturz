"""HTTP-Routen: Datei-Import, Finanzguru, Eingangsordner. Aus main.py ausgelagert; main.py bindet sie ein."""
from __future__ import annotations

import logging
import time
import uuid
from fastapi import APIRouter, Body, File, UploadFile

from . import audit, categorize, charging, contracts, finanzguru, importers, inbox, ledger, services
from .db import get_db, now_iso
from .web import _err, _imports

log = logging.getLogger("kassensturz")
router = APIRouter()

# --- Datei-Import ------------------------------------------------------------------------

def _analysis_public(res: dict) -> dict:
    out = {k: v for k, v in res.items() if k not in ("rows", "finanzguru")}
    out["preview"] = res["rows"][-8:][::-1]
    out["field_labels"] = importers.FIELD_LABELS
    return out


def _match_account(db, res: dict, signature: str | None) -> int | None:
    iban = (res.get("meta") or {}).get("iban")
    if iban:
        acc = db.one("SELECT id FROM accounts WHERE iban = ? AND archived = 0", (iban,))
        if acc:
            return acc["id"]
    if signature:
        prof = db.one("SELECT account_id FROM csv_profiles WHERE signature = ?", (signature,))
        if prof and db.one("SELECT id FROM accounts WHERE id = ?", (prof["account_id"],)):
            return prof["account_id"]
    return None


@router.get("/api/charging")
def charging_summary():
    """Ladevorgänge aus Ladecockpit je Monat und was noch keiner Abbuchung zugeordnet ist."""
    return charging.summary(get_db())


@router.post("/api/charging/import")
async def charging_import(file: UploadFile = File(...)):
    """Liest den CSV-Export von Ladecockpit. Legt keine Buchungen an, ordnet nur zu."""
    data = await file.read(importers.MAX_IMPORT_BYTES + 1)
    if len(data) > importers.MAX_IMPORT_BYTES:
        _err(400, "Die Datei ist größer als 25 MB.")
    try:
        res = charging.import_csv(get_db(), data)
    except charging.ImportError_ as exc:
        _err(400, str(exc))
    audit.subject(f"{res['added']} neu")
    services.schedule_refresh()
    return res


@router.post("/api/import/analyze")
async def import_analyze(file: UploadFile = File(...)):
    # Stop reading as soon as the upload limit is exceeded instead of first
    # allocating the complete untrusted upload in memory.
    data = await file.read(importers.MAX_IMPORT_BYTES + 1)
    if len(data) > importers.MAX_IMPORT_BYTES:
        _err(400, "Die Datei ist größer als 25 MB.")
    head = data[:200].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if head.startswith((b"<!doctype", b"<html", b"{\"detail\"", b"{\"error\"")):
        _err(400, "Das ist keine Exportdatei, sondern eine Webseite oder Fehlermeldung. Beim Herunterladen wurde wohl "
                  "die Anmeldeseite gespeichert. Lade die Datei noch einmal in einem Browser herunter, nicht in der "
                  "Home-Assistant-App, und importiere sie dann.")
    if charging.looks_like_export(data):
        # Der Export von Ladecockpit enthält Ladevorgänge, keine Buchungen; die Oberfläche schickt ihn weiter.
        return {"kind": "ladecockpit"}
    db = get_db()
    for tok in [t for t, v in _imports.items() if time.time() - v["created"] > 1800]:
        _imports.pop(tok, None)
    profile = None
    try:
        res = importers.analyze(data, file.filename or "")
        if res.get("signature"):
            prof = db.one("SELECT mapping FROM csv_profiles WHERE signature = ?", (res["signature"],))
            if prof:
                import json
                profile = json.loads(prof["mapping"])
                res = importers.analyze(data, file.filename or "", profile)
    except Exception as exc:  # noqa: BLE001
        log.exception("Import-Analyse fehlgeschlagen")
        _err(400, f"Die Datei ließ sich nicht lesen: {exc}")
    token = uuid.uuid4().hex
    _imports[token] = {"data": data, "filename": file.filename, "created": time.time()}
    if res.get("kind") == "finanzguru":
        return _finanzguru_start(db, token, res)
    out = _analysis_public(res)
    out.update({"token": token, "account_id": _match_account(db, res, res.get("signature")), "profile_used": bool(profile)})
    return out


@router.post("/api/import/remap")
def import_remap(body: dict = Body(...)):
    item = _imports.get(body.get("token") or "")
    if not item:
        _err(400, "Die Datei ist nicht mehr im Zwischenspeicher. Bitte erneut hochladen.")
    res = importers.analyze(item["data"], item["filename"] or "", body.get("mapping") or {})
    out = _analysis_public(res)
    out["token"] = body["token"]
    return out


@router.post("/api/import/commit")
def import_commit(body: dict = Body(...)):
    import json

    db = get_db()
    item = _imports.get(body.get("token") or "")
    if not item:
        _err(400, "Die Datei ist nicht mehr im Zwischenspeicher. Bitte erneut hochladen.")
    res = importers.analyze(item["data"], item["filename"] or "", body.get("mapping") or None)
    if not res.get("rows"):
        _err(400, res.get("error") or "Keine Buchungen in der Datei gefunden.")
    account_id = body.get("account_id")
    if not account_id:
        new = body.get("new_account") or {}
        name = (new.get("name") or res["suggest"]["name"]).strip()
        kind = new.get("kind") or res["suggest"]["kind"]
        account_id = db.insert("accounts", {
            "name": name[:60], "kind": kind, "iban": (new.get("iban") or res["meta"].get("iban") or None),
            "settlement_pattern": new.get("settlement_pattern", res["suggest"]["settlement"]) or None,
            "in_forecast": 0 if kind == "tagesgeld" else 1, "created": now_iso(),
        })
        categorize.recategorize(db)
    elif not db.one("SELECT id FROM accounts WHERE id = ?", (account_id,)):
        _err(400, "Konto nicht gefunden.")
    result = ledger.import_rows(db, int(account_id), res["rows"], "ordner" if item.get("inbox_file") else "datei", item["filename"],
                                res.get("meta"))
    if res.get("signature"):
        db.execute("INSERT INTO csv_profiles(signature, mapping, account_id, updated) VALUES(?, ?, ?, ?) "
                   "ON CONFLICT(signature) DO UPDATE SET mapping = excluded.mapping, account_id = excluded.account_id, updated = excluded.updated",
                   (res["signature"], json.dumps(res["mapping"]), int(account_id), now_iso()))
    _imports.pop(body["token"], None)
    if item.get("inbox_file"):
        try:
            _, path = inbox.read_file(item["inbox_file"])
            inbox.move_done(path)
        except FileNotFoundError:
            pass
        db.execute("DELETE FROM inbox WHERE filename = ?", (item["inbox_file"],))
    contracts.detect(db)
    services.schedule_refresh()
    acc = db.one("SELECT * FROM accounts WHERE id = ?", (account_id,))
    audit.note(f"Datei „{(item['filename'] or 'ohne Namen')[:60]}“ importiert: {result['added']} neue Buchungen auf „{acc['name']}“",
               int(account_id))
    return {"added": result["added"], "skipped": result["skipped"], "account_id": account_id, "balance_known": acc["balance_date"] is not None}


# --- Umstieg von Finanzguru ----------------------------------------------------------------

def _finanzguru_start(db, token: str, res: dict) -> dict:
    """Erste Antwort auf einen Finanzguru-Export: die Vorschau für den Dialog."""
    _imports[token]["parsed"] = res["finanzguru"]
    return {"kind": "finanzguru", "token": token, **finanzguru.preview(db, res["finanzguru"])}


def _finanzguru_item(body: dict) -> dict:
    item = _imports.get(body.get("token") or "")
    if not item:
        _err(400, "Die Datei ist nicht mehr im Zwischenspeicher. Bitte erneut hochladen.")
    if "parsed" not in item:
        _err(400, "Das ist kein Export aus Finanzguru.")
    return item


def _finanzguru_choices(body: dict) -> list[dict]:
    """Die Auswahl je Konto aus dem Dialog: ein vorhandenes Konto, ein neues oder keines."""
    out = []
    for entry in body.get("accounts") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("ref"), str):
            continue
        target = entry.get("target")
        if isinstance(target, str) and target.isdigit():
            target = int(target)
        if isinstance(target, bool) or not (target in ("new", "skip") or isinstance(target, int)):
            continue
        out.append({"ref": entry["ref"], "target": target, "name": entry.get("name"), "kind": entry.get("kind")})
    return out


@router.post("/api/import/finanzguru/preview")
def finanzguru_preview(body: dict = Body(...)):
    item = _finanzguru_item(body)
    choices = {c["ref"]: c["target"] for c in _finanzguru_choices(body)}
    return {"kind": "finanzguru", "token": body["token"], **finanzguru.preview(get_db(), item["parsed"], choices)}


@router.post("/api/import/finanzguru/commit")
def finanzguru_commit(body: dict = Body(...)):
    db = get_db()
    item = _finanzguru_item(body)
    categories = [c for c in body.get("categories") or [] if isinstance(c, dict)]
    for entry in categories:
        if isinstance(entry.get("target"), str) and entry["target"].isdigit():
            entry["target"] = int(entry["target"])
    try:
        result = finanzguru.commit(db, item["parsed"], _finanzguru_choices(body), categories,
                                   learn=bool(body.get("learn", True)), filename=item["filename"])
    except ValueError as exc:
        _err(400, str(exc))
    added = result.get("added") if isinstance(result, dict) else None
    audit.subject(f"{added} Buchungen" if isinstance(added, int) else None)
    _imports.pop(body["token"], None)
    if item.get("inbox_file"):
        try:
            _, path = inbox.read_file(item["inbox_file"])
            inbox.move_done(path)
        except FileNotFoundError:
            pass
        db.execute("DELETE FROM inbox WHERE filename = ?", (item["inbox_file"],))
    contracts.detect(db)
    services.schedule_refresh()
    return result


# --- Eingangsordner -------------------------------------------------------------------------------

@router.get("/api/inbox")
def inbox_status():
    return inbox.status(get_db())


@router.post("/api/inbox/scan")
def inbox_scan():
    res = inbox.scan(get_db())
    if res["imported"]:
        contracts.detect(get_db())
        services.schedule_refresh()
    return res


@router.post("/api/inbox/analyze")
def inbox_analyze(body: dict = Body(...)):
    import json

    db = get_db()
    name = body.get("filename") or ""
    try:
        data, _ = inbox.read_file(name)
    except FileNotFoundError:
        _err(404, "Die Datei liegt nicht mehr im Eingangsordner.")
    res = importers.analyze(data, name)
    profile = None
    if res.get("signature"):
        prof = db.one("SELECT mapping FROM csv_profiles WHERE signature = ?", (res["signature"],))
        if prof:
            profile = json.loads(prof["mapping"])
            res = importers.analyze(data, name, profile)
    token = uuid.uuid4().hex
    _imports[token] = {"data": data, "filename": name, "created": time.time(), "inbox_file": name}
    if res.get("kind") == "finanzguru":
        return _finanzguru_start(db, token, res)
    out = _analysis_public(res)
    out.update({"token": token, "account_id": inbox.match_account(db, res, name), "profile_used": bool(profile)})
    return out


@router.delete("/api/inbox/{filename}")
def inbox_delete(filename: str):
    try:
        inbox.delete_file(get_db(), filename)
    except FileNotFoundError:
        _err(404, "Datei nicht gefunden.")
    return {"ok": True}
