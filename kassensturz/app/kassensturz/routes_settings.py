"""HTTP-Routen: Auswertung, Sparziele, Einstellungen, Export, Beispieldaten. Aus main.py ausgelagert; main.py bindet sie ein."""
from __future__ import annotations

import csv
import io
import shutil
import tempfile
from datetime import date
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse, Response
from pathlib import Path
from starlette.background import BackgroundTask

from . import analytics, audit, contracts, db as dbmod, demo, ha, health, options, savings, services, umzug
from .db import get_db
from .web import _changed, _err

router = APIRouter()

# --- Auswertung, Einstellungen, Export ----------------------------------------------------------

@router.get("/api/stats")
def stats(month: str = ""):
    db = get_db()
    month = month or date.today().strftime("%Y-%m")
    return {"month": analytics.month_stats(db, month), "history": analytics.monthly_totals(db, 12),
            "review": analytics.month_review(db, month)}


@router.get("/api/afford")
def afford(amount_cents: int = 0):
    if not 0 < amount_cents <= analytics.MAX_AFFORD_CENTS:
        _err(400, "Bitte einen Betrag größer als 0 eingeben.")
    db = get_db()
    threshold = int(options.load().get("warn_threshold") or 0) * 100
    return analytics.afford(analytics.forecast(db), amount_cents, threshold)


@router.get("/api/goals")
def goals():
    db = get_db()
    fc = analytics.forecast(db)
    return {"goals": savings.list_goals(db),
            "reserve": {"items": fc["reserve_items"], "reserved_cents": fc["reserve_cents"],
                        "monthly_cents": fc["reserve_monthly_cents"], "deducted": fc["reserve_deducted"]}}


@router.post("/api/goals")
def create_goal(body: dict = Body(...)):
    try:
        gid = savings.create_goal(get_db(), body)
    except savings.GoalError as error:
        _err(400, str(error))
    audit.subject(get_db().scalar("SELECT name FROM goals WHERE id = ?", (gid,)))
    return {"ok": True, "id": gid}


@router.patch("/api/goals/{gid}")
def update_goal(gid: int, body: dict = Body(...)):
    try:
        found = savings.update_goal(get_db(), gid, body)
    except savings.GoalError as error:
        _err(400, str(error))
    if not found:
        _err(404, "Sparziel nicht gefunden.")
    return {"ok": True}


@router.delete("/api/goals/{gid}")
def delete_goal(gid: int):
    audit.subject(get_db().scalar("SELECT name FROM goals WHERE id = ?", (gid,)))
    get_db().execute("DELETE FROM goals WHERE id = ?", (gid,))
    return {"ok": True}


@router.get("/api/settings")
def get_settings():
    db = get_db()
    opts = options.load()
    return {"profile": db.get_setting("profile", {}) or {}, "buffer_cents": db.get_setting("buffer_cents", 0) or 0,
            "deduct_reserve": bool(db.get_setting("deduct_reserve", False)),
            "options": {k: opts.get(k) for k in ("sync_time", "sensors", "notify_service", "warn_threshold", "mobile_server_url")},
            "product_id": bool((opts.get("fints_product_id") or "").strip()), "ha": ha.available()}


@router.put("/api/settings")
def put_settings(body: dict = Body(...)):
    db = get_db()
    if "profile" in body:
        p = body["profile"] or {}
        db.set_setting("profile", {k: (p.get(k) or "").strip() for k in ("name", "street", "city", "email")})
    if "buffer_cents" in body:
        db.set_setting("buffer_cents", int(body["buffer_cents"] or 0))
    if "deduct_reserve" in body:
        db.set_setting("deduct_reserve", bool(body["deduct_reserve"]))
    _changed()
    return get_settings()


@router.post("/api/demo")
def load_demo():
    db = get_db()
    res = demo.load_demo(db)
    contracts.detect(db)
    services.schedule_refresh()
    return res


@router.delete("/api/demo")
def remove_demo():
    db = get_db()
    demo.remove_demo(db)
    contracts.detect(db)
    services.schedule_refresh()
    return {"ok": True}


@router.post("/api/refresh")
def refresh():
    services.refresh(get_db(), notify=False)
    return {"ok": True}


def _csv_safe_text(value: str | None) -> str:
    """Prevent spreadsheet formula execution when untrusted text is opened from CSV."""
    text = str(value or "")
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


@router.get("/api/umzug/export")
def umzug_export():
    """Vollständige Kopie der Datenbank für den Umzug in eine andere Installation."""
    db = get_db()
    target = Path(tempfile.mkdtemp(prefix="kassensturz-umzug-")) / umzug.FILENAME
    with db.lock:
        if db._depth:
            raise HTTPException(409, "Gerade läuft eine Änderung. Bitte gleich noch einmal versuchen.")
        umzug.write_copy(db.conn, target)
    return FileResponse(
        target, media_type="application/vnd.sqlite3", filename=umzug.FILENAME,
        headers={"Cache-Control": "no-store"},
        background=BackgroundTask(shutil.rmtree, target.parent, ignore_errors=True),
    )


@router.get("/api/umzug/archive")
def umzug_archive():
    """Vollständige Sicherung: Datenbank und Belege in einer ZIP-Datei."""
    db = get_db()
    target = Path(tempfile.mkdtemp(prefix="kassensturz-sicherung-")) / umzug.ARCHIVE
    with db.lock:
        if db._depth:
            raise HTTPException(409, "Gerade läuft eine Änderung. Bitte gleich noch einmal versuchen.")
        umzug.write_archive(db.conn, dbmod.DATA_DIR, target, options.VERSION)
    return FileResponse(
        target, media_type="application/zip", filename=umzug.ARCHIVE,
        headers={"Cache-Control": "no-store"},
        background=BackgroundTask(shutil.rmtree, target.parent, ignore_errors=True),
    )


@router.get("/api/health")
def health_status():
    return health.status(get_db())


@router.post("/api/health/backup-check")
def health_backup_check():
    return health.check_newest_backup(get_db())


@router.get("/api/export.csv")
def export_csv():
    db = get_db()
    rows = db.query("SELECT t.id, t.booking_date, t.value_date, a.name AS konto, t.counterparty, t.counterparty_iban, t.purpose, t.amount_cents, "
                    "c.name AS kategorie, t.is_transfer, t.note FROM transactions t JOIN accounts a ON a.id = t.account_id "
                    "LEFT JOIN categories c ON c.id = t.category_id ORDER BY t.booking_date, t.id")
    split_rows = db.query(
        "SELECT s.tx_id, s.amount_cents, c.name AS category_name FROM splits s "
        "LEFT JOIN categories c ON c.id = s.category_id ORDER BY s.tx_id, s.id"
    )
    splits_by_tx = {}
    for split in split_rows:
        splits_by_tx.setdefault(split["tx_id"], []).append(split)

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Buchungstag", "Wertstellung", "Konto", "Gegenseite", "IBAN", "Verwendungszweck", "Betrag", "Kategorie", "Umbuchung", "Notiz", "Aufteilungen"])
    for r in rows:
        split_text = " | ".join(
            f"{_csv_safe_text(split['category_name'] or 'Ohne Kategorie')}: "
            f"{split['amount_cents'] / 100:.2f}".replace(".", ",") + " EUR"
            for split in splits_by_tx.get(r["id"], [])
        )
        w.writerow([r["booking_date"], r["value_date"], _csv_safe_text(r["konto"]), _csv_safe_text(r["counterparty"]),
                    _csv_safe_text(r["counterparty_iban"]), _csv_safe_text(r["purpose"]),
                    f"{r['amount_cents'] / 100:.2f}".replace(".", ","), _csv_safe_text(r["kategorie"]),
                    "ja" if r["is_transfer"] else "", _csv_safe_text(r["note"]), _csv_safe_text(split_text)])
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="kassensturz-{date.today()}.csv"'})
