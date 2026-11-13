"""Papierkram: steuerrelevante Buchungen und Belege."""
from __future__ import annotations

import csv
import io
import os
import re
import uuid
from datetime import date
from pathlib import Path

from . import db as dbmod
from .db import Database, now_iso

# Reihenfolge wie in der Anzeige. Die Schlüssel stehen in der Datenbank und bleiben stabil.
TAX_KINDS = {
    "handwerker": "Handwerkerleistung",
    "haushaltsnah": "Haushaltsnahe Dienstleistung",
    "arbeitsmittel": "Arbeitsmittel und Werbungskosten",
    "spende": "Spende",
    "versicherung": "Versicherung und Vorsorge",
    "gesundheit": "Krankheitskosten",
    "kinder": "Kinderbetreuung",
    "sonstiges": "Sonstiges",
}

MAX_RECEIPT_BYTES = 10 * 1024 * 1024
MAX_RECEIPTS_PER_TX = 10
FOLDER = "belege"


class PaperError(ValueError):
    """Die Angabe oder die Datei passt nicht."""


def clean_tax_kind(value) -> str | None:
    if value in (None, ""):
        return None
    if value not in TAX_KINDS:
        raise PaperError("Steuerart unbekannt.")
    return value


def clean_warranty(value) -> str | None:
    """Garantieende als ISO-Datum; leer entfernt es."""
    if value in (None, ""):
        return None
    try:
        day = date.fromisoformat(value) if isinstance(value, str) and len(value) == 10 else None
    except ValueError:
        day = None
    if day is None or not 2000 <= day.year <= 2100:
        raise PaperError("Das Garantieende ist kein gültiges Datum.")
    return day.isoformat()


WARRANTY_NOTICE_DAYS = 30
WARRANTY_KEEP_DAYS = 90


def warranties(db: Database, today: date | None = None) -> dict:
    """Käufe mit Garantie: laufende zuerst nach Ablauf, dazu die zuletzt abgelaufenen."""
    today = today or date.today()
    rows = db.query(
        """SELECT t.id, t.booking_date, t.amount_cents, t.counterparty, t.purpose, t.note, t.warranty_until,
                  (SELECT COUNT(*) FROM receipts r WHERE r.tx_id = t.id) AS receipt_count
           FROM transactions t JOIN accounts a ON a.id = t.account_id
           WHERE t.warranty_until IS NOT NULL AND a.archived = 0
           ORDER BY t.warranty_until, t.id""")
    running, expired = [], []
    for r in rows:
        try:
            left = (date.fromisoformat(r["warranty_until"]) - today).days
        except ValueError:
            continue
        r["days_left"] = left
        r["label"] = r["note"] or r["counterparty"] or r["purpose"] or "Kauf"
        if left >= 0:
            running.append(r)
        elif left >= -WARRANTY_KEEP_DAYS:
            expired.append(r)
    return {"running": running, "expired": expired[::-1], "soon": sum(1 for r in running if r["days_left"] <= WARRANTY_NOTICE_DAYS)}


# --- Belege --------------------------------------------------------------------------

def _sniff(data: bytes) -> tuple[str, str] | None:
    """Dateityp aus dem Inhalt. Der Name und der Typ, den der Browser meldet, zählen nicht."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg", "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    if data[:5] == b"%PDF-":
        return "application/pdf", "pdf"
    return None


def _folder() -> Path:
    path = dbmod.DATA_DIR / FOLDER
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    return path


def _display_name(filename: str | None, ext: str) -> str:
    name = Path((filename or "").replace("\\", "/")).name
    name = re.sub(r"[^\w .()+-]", "_", name, flags=re.UNICODE).strip(" .")[:80]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return f"{stem or 'Beleg'}.{ext}"


def list_receipts(db: Database, tx_id: int) -> list[dict]:
    return db.query("SELECT id, tx_id, filename, mime, size, created FROM receipts WHERE tx_id = ? ORDER BY id", (tx_id,))


def add_receipt(db: Database, tx_id: int, filename: str | None, data: bytes) -> dict:
    if not db.one("SELECT id FROM transactions WHERE id = ?", (tx_id,)):
        raise PaperError("Buchung nicht gefunden.")
    if not data:
        raise PaperError("Die Datei ist leer.")
    if len(data) > MAX_RECEIPT_BYTES:
        raise PaperError("Die Datei ist größer als 10 MB.")
    kind = _sniff(data)
    if not kind:
        raise PaperError("Als Beleg gehen Fotos (JPEG, PNG, WebP) und PDF.")
    if int(db.scalar("SELECT COUNT(*) FROM receipts WHERE tx_id = ?", (tx_id,)) or 0) >= MAX_RECEIPTS_PER_TX:
        raise PaperError(f"Mehr als {MAX_RECEIPTS_PER_TX} Belege je Buchung gehen nicht.")
    mime, ext = kind
    stored = f"{uuid.uuid4().hex}.{ext}"
    path = _folder() / stored
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        rid = db.insert("receipts", {"tx_id": tx_id, "filename": _display_name(filename, ext), "stored": stored,
                                     "mime": mime, "size": len(data), "created": now_iso()})
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return db.one("SELECT id, tx_id, filename, mime, size, created FROM receipts WHERE id = ?", (rid,))


def receipt_file(db: Database, receipt_id: int) -> tuple[dict, Path] | None:
    row = db.one("SELECT * FROM receipts WHERE id = ?", (receipt_id,))
    if not row or not re.fullmatch(r"[0-9a-f]{32}\.(jpg|png|webp|pdf)", row["stored"] or ""):
        return None
    path = _folder() / row["stored"]
    return (row, path) if path.is_file() else None


def delete_receipt(db: Database, receipt_id: int) -> bool:
    row = db.one("SELECT stored FROM receipts WHERE id = ?", (receipt_id,))
    if not row:
        return False
    db.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))
    _unlink(row["stored"])
    return True


def _unlink(stored: str | None) -> None:
    if stored and re.fullmatch(r"[0-9a-f]{32}\.(jpg|png|webp|pdf)", stored):
        (_folder() / stored).unlink(missing_ok=True)


def prune(db: Database) -> int:
    """Belege entfernen, deren Buchung es nicht mehr gibt."""
    rows = db.query("SELECT r.id, r.stored FROM receipts r LEFT JOIN transactions t ON t.id = r.tx_id WHERE t.id IS NULL")
    for row in rows:
        db.execute("DELETE FROM receipts WHERE id = ?", (row["id"],))
        _unlink(row["stored"])
    return len(rows)


# --- Steuer --------------------------------------------------------------------------

def tax_years(db: Database) -> list[int]:
    rows = db.query("SELECT DISTINCT substr(booking_date, 1, 4) AS y FROM transactions WHERE tax_kind IS NOT NULL ORDER BY y DESC")
    return [int(r["y"]) for r in rows if (r["y"] or "").isdigit()]


def tax_year(db: Database, year: int) -> dict:
    """Markierte Buchungen eines Jahres, nach Steuerart. Beträge als Ausgabe positiv."""
    rows = db.query(
        """SELECT t.id, t.booking_date, t.amount_cents, t.counterparty, t.purpose, t.note, t.tax_kind,
                  a.name AS account_name, c.name AS category_name,
                  (SELECT COUNT(*) FROM receipts r WHERE r.tx_id = t.id) AS receipt_count
           FROM transactions t JOIN accounts a ON a.id = t.account_id
           LEFT JOIN categories c ON c.id = t.category_id
           WHERE t.tax_kind IS NOT NULL AND substr(t.booking_date, 1, 4) = ?
           ORDER BY t.booking_date, t.id""",
        (f"{int(year):04d}",),
    )
    groups = []
    for key, label in TAX_KINDS.items():
        items = [r for r in rows if r["tax_kind"] == key]
        if not items:
            continue
        groups.append({"kind": key, "label": label, "count": len(items),
                       "total_cents": -sum(r["amount_cents"] for r in items),
                       "missing_receipts": sum(1 for r in items if not r["receipt_count"]), "items": items})
    return {"year": int(year), "years": tax_years(db), "count": len(rows),
            "total_cents": sum(g["total_cents"] for g in groups),
            "missing_receipts": sum(g["missing_receipts"] for g in groups), "groups": groups}


def _safe(text) -> str:
    """Kein Feld darf in einer Tabellenkalkulation als Formel starten."""
    text = " ".join(str(text or "").split())
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def tax_csv(db: Database, year: int) -> bytes:
    data = tax_year(db, year)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Steuerart", "Datum", "Empfänger", "Verwendungszweck", "Betrag", "Konto", "Kategorie", "Notiz", "Belege"])
    for g in data["groups"]:
        for r in g["items"]:
            w.writerow([g["label"], r["booking_date"], _safe(r["counterparty"]), _safe(r["purpose"]),
                        f"{-r['amount_cents'] / 100:.2f}".replace(".", ","), _safe(r["account_name"]),
                        _safe(r["category_name"]), _safe(r["note"]), r["receipt_count"]])
        w.writerow([f"Summe {g['label']}", "", "", "", f"{g['total_cents'] / 100:.2f}".replace(".", ","), "", "", "", ""])
    return buf.getvalue().encode("utf-8-sig")


def default_year(db: Database, today: date | None = None) -> int:
    years = tax_years(db)
    return years[0] if years else (today or date.today()).year
