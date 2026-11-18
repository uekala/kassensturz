"""HTTP-Routen: Buchungen, Belege, Aufteilungen. Aus main.py ausgelagert; main.py bindet sie ein."""
from __future__ import annotations

from datetime import date
from fastapi import APIRouter, Body, File, UploadFile
from fastapi.responses import FileResponse, Response

from . import audit, categorize, papers, projects
from .db import get_db, now_iso
from .web import _changed, _err

router = APIRouter()

# --- Buchungen ---------------------------------------------------------------------

@router.get("/api/transactions")
def transactions(q: str = "", account: int | None = None, category: int | None = None, month: str = "", kind: str = "",
                 contract: str = "", project: int | None = None, offset: int = 0, limit: int = 100):
    db = get_db()
    sql_where, params = _tx_filter(q, account, category, month, kind, contract, project)
    base = (f"FROM transactions t JOIN accounts a ON a.id = t.account_id LEFT JOIN categories c ON c.id = t.category_id "
            f"WHERE {sql_where}")
    total = db.one(f"SELECT COUNT(*) AS n, COALESCE(SUM(CASE WHEN t.amount_cents > 0 AND t.is_transfer = 0 THEN t.amount_cents END), 0) AS sin, "
                   f"COALESCE(SUM(CASE WHEN t.amount_cents < 0 AND t.is_transfer = 0 THEN t.amount_cents END), 0) AS sout {base}", tuple(params))
    items = db.query(
        f"SELECT t.*, a.name AS account_name, a.kind AS account_kind, c.name AS category_name, c.kind AS category_kind, "
        f"(SELECT project_id FROM project_tx WHERE tx_id = t.id) AS project_id {base} "
        f"ORDER BY t.booking_date DESC, t.id DESC LIMIT ? OFFSET ?",
        (*params, max(1, min(limit, 500)), max(0, offset)),
    )
    return _tx_page(db, items, total)


def _tx_filter(q: str = "", account: int | None = None, category: int | None = None, month: str = "", kind: str = "",
               contract: str = "", project: int | None = None) -> tuple[str, list]:
    """Die Bedingung der Buchungsliste; „Alle Treffer zuordnen“ nutzt dieselbe."""
    where = ["a.archived = 0"]
    params: list = []
    if q:
        where.append("(t.counterparty LIKE ? OR t.purpose LIKE ? OR t.note LIKE ? OR CAST(t.amount_cents AS TEXT) LIKE ?)")
        like = f"%{q}%"
        cents_like = q.replace(",", "").replace(".", "").replace("€", "").strip()
        params += [like, like, like, f"%{cents_like}%"]
    if account:
        where.append("t.account_id = ?")
        params.append(account)
    if category:
        where.append("(t.category_id = ? OR c.parent_id = ? OR t.id IN (SELECT tx_id FROM splits WHERE category_id = ?))")
        params += [category, category, category]
    if month:
        where.append("substr(t.booking_date, 1, 7) = ?")
        params.append(month)
    if contract:
        where.append("t.contract_key = ?")
        params.append(contract)
    if kind == "in":
        where.append("t.amount_cents > 0 AND t.is_transfer = 0")
    elif kind == "out":
        where.append("t.amount_cents < 0 AND t.is_transfer = 0")
    elif kind == "transfer":
        where.append("t.is_transfer = 1")
    elif kind == "uncat":
        where.append("c.builtin_key IN ('sonstiges', 'sonstige_einnahmen') AND t.category_locked = 0")
    if project:
        where.append("t.id IN (SELECT tx_id FROM project_tx WHERE project_id = ?)")
        params.append(project)
    return " AND ".join(where), params


def _tx_page(db, items: list[dict], total: dict) -> dict:
    if items:
        ids = [i["id"] for i in items]
        splits = db.query(f"SELECT s.*, c.name AS category_name FROM splits s LEFT JOIN categories c ON c.id = s.category_id "
                          f"WHERE s.tx_id IN ({','.join('?' * len(ids))})", tuple(ids))
        by = {}
        for sp in splits:
            by.setdefault(sp["tx_id"], []).append(sp)
        counts = {r["tx_id"]: r["n"] for r in db.query(
            f"SELECT tx_id, COUNT(*) AS n FROM receipts WHERE tx_id IN ({','.join('?' * len(ids))}) GROUP BY tx_id", tuple(ids))}
        for i in items:
            i["splits"] = by.get(i["id"], [])
            i["receipt_count"] = counts.get(i["id"], 0)
            i.pop("hash", None)
    return {"items": items, "total": total["n"], "sum_in": total["sin"], "sum_out": total["sout"]}


@router.patch("/api/transactions/{tx_id}")
def update_transaction(tx_id: int, body: dict = Body(...)):
    db = get_db()
    tx = db.one("SELECT * FROM transactions WHERE id = ?", (tx_id,))
    if not tx:
        _err(404, "Buchung nicht gefunden.")
    data = {}
    if "note" in body:
        data["note"] = (body.get("note") or "").strip() or None
    if "tax_kind" in body:
        try:
            data["tax_kind"] = papers.clean_tax_kind(body.get("tax_kind"))
        except papers.PaperError as exc:
            _err(400, str(exc))
    if "warranty_until" in body:
        try:
            data["warranty_until"] = papers.clean_warranty(body.get("warranty_until"))
        except papers.PaperError as exc:
            _err(400, str(exc))
    changed = 0
    if body.get("category_id"):
        cat = db.one("SELECT * FROM categories WHERE id = ?", (body["category_id"],))
        if not cat:
            _err(400, "Kategorie unbekannt.")
        data.update({"category_id": cat["id"], "category_locked": 1, "is_transfer": 1 if cat["kind"] == "transfer" else 0,
                     "rule_ref": "manual"})
        rule = body.get("rule")
        if rule and (rule.get("pattern") or "").strip():
            db.insert("rules", {"pattern": rule["pattern"].strip(), "field": rule.get("field") or "any", "sign": rule.get("sign") or "any",
                                "category_id": cat["id"], "mark_transfer": 1 if cat["kind"] == "transfer" else 0, "priority": 100,
                                "enabled": 1, "created": now_iso()})
    learned = None
    if "category_id" in data and not body.get("rule") and body.get("learn", True):
        learned = categorize.learn(db, tx, data["category_id"])
    project_before = db.scalar("SELECT project_id FROM project_tx WHERE tx_id = ?", (tx_id,))
    if "project_id" in body:
        try:
            projects.set_for(db, tx_id, body.get("project_id"))
        except projects.ProjectError as error:
            _err(error.status, error.message)
    db.update("transactions", "id", tx_id, data)
    _note_tx_change(db, tx, data, project_before, body)
    if body.get("rule") or learned:
        changed = categorize.recategorize(db)
    _changed()
    return {"ok": True, "recategorized": changed, "learned": bool(learned)}


@router.get("/api/transactions/{tx_id}/receipts")
def receipts(tx_id: int):
    return {"items": papers.list_receipts(get_db(), tx_id), "max": papers.MAX_RECEIPTS_PER_TX}


@router.post("/api/transactions/{tx_id}/receipts")
async def add_receipt(tx_id: int, file: UploadFile = File(...)):
    # Nicht erst die ganze fremde Datei in den Speicher lesen und dann ablehnen.
    data = await file.read(papers.MAX_RECEIPT_BYTES + 1)
    try:
        return papers.add_receipt(get_db(), tx_id, file.filename, data)
    except papers.PaperError as exc:
        _err(404 if "nicht gefunden" in str(exc) else 400, str(exc))


@router.get("/api/receipts/{receipt_id}")
def receipt(receipt_id: int):
    found = papers.receipt_file(get_db(), receipt_id)
    if not found:
        _err(404, "Beleg nicht gefunden.")
    row, path = found
    # Der Typ stammt aus dem Inhalt; der Browser soll ihn nicht selbst raten.
    return FileResponse(path, media_type=row["mime"], filename=row["filename"], content_disposition_type="inline",
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.delete("/api/receipts/{receipt_id}")
def delete_receipt(receipt_id: int):
    if not papers.delete_receipt(get_db(), receipt_id):
        _err(404, "Beleg nicht gefunden.")
    return {"ok": True}


@router.get("/api/warranties")
def warranties():
    return papers.warranties(get_db())


@router.get("/api/tax")
def tax(year: int | None = None):
    db = get_db()
    out = papers.tax_year(db, year if year and 1990 <= year <= 2200 else papers.default_year(db))
    out["kinds"] = [{"key": k, "label": v} for k, v in papers.TAX_KINDS.items()]
    return out


@router.get("/api/tax.csv")
def tax_csv(year: int):
    if not 1990 <= year <= 2200:
        _err(400, "Jahr ungültig.")
    return Response(papers.tax_csv(get_db(), year), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="kassensturz-steuer-{year}.csv"', "Cache-Control": "no-store"})


@router.post("/api/transactions/{tx_id}/reset")
def reset_transaction(tx_id: int):
    db = get_db()
    db.update("transactions", "id", tx_id, {"category_locked": 0})
    categorize.recategorize(db, [tx_id])
    _note_tx(db, tx_id, "wieder automatisch zugeordnet")
    _changed()
    return {"ok": True}


@router.put("/api/transactions/{tx_id}/splits")
def set_splits(tx_id: int, body: dict = Body(...)):
    db = get_db()
    tx = db.one("SELECT * FROM transactions WHERE id = ?", (tx_id,))
    if not tx:
        _err(404, "Buchung nicht gefunden.")
    parts = body.get("splits") or []
    total = sum(int(p.get("amount_cents") or 0) for p in parts)
    if parts and (abs(total) > abs(tx["amount_cents"]) or any((int(p.get("amount_cents") or 0) * tx["amount_cents"]) <= 0 for p in parts)):
        _err(400, "Die Teilbeträge müssen das gleiche Vorzeichen haben und dürfen zusammen nicht größer als die Buchung sein.")
    with db.tx():
        db.execute("DELETE FROM splits WHERE tx_id = ?", (tx_id,))
        for p in parts:
            db.insert("splits", {"tx_id": tx_id, "amount_cents": int(p["amount_cents"]), "category_id": p.get("category_id"),
                                 "note": (p.get("note") or "").strip() or None})
    audit.note(f"{audit.tx_label(tx)}: " + (f"aufgeteilt in {len(parts)} Teile" if parts else "Aufteilung entfernt"),
               tx["account_id"])
    _changed()
    return {"ok": True}


@router.get("/api/transactions/{tx_id}/suggest-rule")
def suggest_rule(tx_id: int):
    db = get_db()
    tx = db.one("SELECT * FROM transactions WHERE id = ?", (tx_id,))
    if not tx:
        _err(404, "Buchung nicht gefunden.")
    pattern = categorize.suggest_pattern(tx)
    count = 0
    if pattern:
        rx = categorize._compile(pattern)
        from .util import norm
        for r in db.query("SELECT counterparty, purpose FROM transactions"):
            if rx.search(norm(r["counterparty"])) or rx.search(norm(r["purpose"])):
                count += 1
    return {"pattern": pattern, "matches": count, "sign": "in" if tx["amount_cents"] > 0 else "out"}


def _note_tx_change(db, tx: dict, data: dict, project_before, body: dict) -> None:
    """Was sich an einer Buchung geändert hat, als ein Satz fürs Protokoll."""
    parts = []
    if "category_id" in data:
        name = db.scalar("SELECT name FROM categories WHERE id = ?", (data["category_id"],))
        rule = (body.get("rule") or {}).get("pattern") if isinstance(body.get("rule"), dict) else None
        parts.append(f"Kategorie „{name}“" + (f", auch künftig bei „{rule.strip()[:40]}“" if rule and rule.strip() else ""))
    if "note" in data and data["note"] != tx["note"]:
        parts.append("Notiz geändert" if data["note"] else "Notiz gelöscht")
    if "tax_kind" in data and data["tax_kind"] != tx["tax_kind"]:
        parts.append("für die Steuer markiert" if data["tax_kind"] else "Steuer-Markierung entfernt")
    if "warranty_until" in data and data["warranty_until"] != tx["warranty_until"]:
        parts.append(f"Garantie bis {date.fromisoformat(data['warranty_until']).strftime('%d.%m.%Y')}"
                     if data["warranty_until"] else "Garantie entfernt")
    if "project_id" in body and body.get("project_id") != project_before:
        name = db.scalar("SELECT name FROM projects WHERE id = ?", (body.get("project_id"),)) if body.get("project_id") else None
        parts.append(f"Projekt „{name}“" if name else "aus dem Projekt genommen")
    if parts:
        audit.note(f"{audit.tx_label(tx)}: {', '.join(parts)}", tx["account_id"])
    else:
        audit.skip()


def _note_tx(db, tx_id: int, what: str) -> None:
    tx = db.one("SELECT * FROM transactions WHERE id = ?", (tx_id,))
    if tx:
        audit.note(f"{audit.tx_label(tx)}: {what}", tx["account_id"])
