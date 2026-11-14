"""Zustand der Installation: Datenbank, Belege, Sicherungen."""
from __future__ import annotations

from datetime import date, datetime

from . import backup, papers
from . import db as dbmod
from .db import Database

BACKUP_MAX_AGE_DAYS = 2


def receipts_state(db: Database) -> dict:
    """Zahl und Größe der Belege, dazu Einträge, deren Datei fehlt."""
    rows = db.query("SELECT stored, size FROM receipts")
    folder = dbmod.DATA_DIR / papers.FOLDER
    missing = sum(1 for r in rows if not (folder / (r["stored"] or "-")).is_file())
    return {"count": len(rows), "bytes": sum(int(r["size"] or 0) for r in rows), "missing": missing}


def status(db: Database, today: date | None = None) -> dict:
    today = today or date.today()
    latest = backup.newest()
    age = None
    if latest is not None:
        try:
            age = (today - datetime.fromtimestamp(latest.stat().st_mtime).date()).days
        except OSError:
            latest = None
    size = 0
    for suffix in ("", "-wal"):  # frische Änderungen liegen zuerst im Schreibprotokoll
        try:
            size += db.path.with_name(db.path.name + suffix).stat().st_size
        except OSError:
            pass
    try:
        copies = len(list(backup.folder().glob("*.sqlite")))
    except OSError:
        copies = 0
    return {
        "integrity": db.integrity,
        "integrity_ok": db.integrity == "ok",
        "schema_version": dbmod.SCHEMA_VERSION,
        "schema_found": max(db.schema_before, dbmod.SCHEMA_VERSION) if db.newer_schema else dbmod.SCHEMA_VERSION,
        "newer_schema": db.newer_schema,
        "database_bytes": size,
        "accounts": int(db.scalar("SELECT COUNT(*) FROM accounts") or 0),
        "transactions": int(db.scalar("SELECT COUNT(*) FROM transactions") or 0),
        "receipts": receipts_state(db),
        "backups": {"count": copies, "newest": latest.name if latest else None, "age_days": age,
                    "stale": latest is None or (age is not None and age > BACKUP_MAX_AGE_DAYS)},
    }


def check_newest_backup(db: Database) -> dict:
    """Prüft die jüngste Kopie und stellt sie dem laufenden Bestand gegenüber."""
    latest = backup.newest()
    if latest is None:
        return {"found": False, "ok": False}
    result = backup.verify(latest)
    result["found"] = True
    result["live_accounts"] = int(db.scalar("SELECT COUNT(*) FROM accounts") or 0)
    result["live_transactions"] = int(db.scalar("SELECT COUNT(*) FROM transactions") or 0)
    return result


def alerts(db: Database) -> list[dict]:
    """Nur Zustände, bei denen etwas zu tun ist."""
    out = []
    if db.integrity != "ok":
        out.append({"key": "health:integrity", "level": "critical", "title": "Die Datenbank ist beschädigt",
                    "text": "Die Prüfung beim Start hat einen Fehler gemeldet. Ändere vorerst nichts und stelle die "
                            "letzte Sicherung wieder her; wie das geht, steht in der Dokumentation unter Wiederherstellung."})
    if db.newer_schema:
        out.append({"key": f"health:schema:{db.schema_before}", "level": "warning",
                    "title": "Die Daten stammen von einer neueren Version",
                    "text": "Diese Version von Kassensturz ist älter als die, die zuletzt mit den Daten gearbeitet hat. "
                            "Aktualisiere die App, bevor du weiterarbeitest."})
    missing = receipts_state(db)["missing"]
    if missing:
        out.append({"key": f"health:receipts:{missing}", "level": "warning",
                    "title": "Belegdateien fehlen",
                    "text": f"Zu {missing} {'Beleg' if missing == 1 else 'Belegen'} fehlt die Datei. Das passiert nach einem "
                            "Umzug nur mit der Datenbank; nimm für den Umzug die vollständige Sicherung."})
    return out
