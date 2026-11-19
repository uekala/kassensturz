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


def rehearse_restore(db: Database, latest=None) -> dict:
    """Probt die Wiederherstellung aus der jüngsten Sicherungskopie, ohne den laufenden Bestand anzufassen.

    Die Kopie wird in einen privaten Ordner außerhalb von /data kopiert und dort so geöffnet wie beim Start:
    Kassensturz bringt sie auf das aktuelle Schema, prüft sie und rechnet Salden und Übersicht. Dann werden
    Konten und Buchungen mit dem laufenden Bestand verglichen. Der Ordner wird am Ende gelöscht.
    """
    import shutil
    import sqlite3
    import tempfile
    from pathlib import Path

    from . import ledger, services

    latest = latest or backup.newest()
    if latest is None:
        return {"found": False, "ok": False}
    out = {"found": True, "name": latest.name, "ok": False, "steps": []}

    def step(name: str, ok: bool, text: str) -> bool:
        out["steps"].append({"name": name, "ok": ok, "text": text})
        return ok

    work = Path(tempfile.mkdtemp(prefix="kassensturz-probe-"))
    copy = None
    try:
        # 1. Kopieren wie bei einer echten Wiederherstellung, über SQLite statt Dateikopie
        target = work / "kassensturz.sqlite"
        src = sqlite3.connect(f"file:{latest}?mode=ro", uri=True)
        try:
            dst = sqlite3.connect(str(target))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        # 2. Öffnen wie beim Start: Schema, Umstellungen, Prüfung
        copy = dbmod.Database(target)
        if not step("open", copy.integrity == "ok" and not copy.newer_schema,
                    f"Geöffnet und auf Schema {dbmod.SCHEMA_VERSION} gebracht (war {copy.schema_before}), "
                    f"Prüfung: {copy.integrity}." if not copy.newer_schema else
                    "Die Kopie stammt von einer neueren Version von Kassensturz."):
            return out
        # 3. Rechnen: Salden je Konto und die Übersicht
        accounts = ledger.accounts_with_balance(copy, include_archived=True)
        services.build_summary(copy)
        tx_backup = int(copy.scalar("SELECT COUNT(*) FROM transactions") or 0)
        step("compute", True, f"{len(accounts)} Konten und {tx_backup} Buchungen gelesen, Salden und Übersicht berechnet.")
        # 4. Vergleich mit dem laufenden Bestand: was in der Kopie steht, muss auch jetzt da sein
        live_accounts = {a["id"]: a for a in db.query("SELECT id, name FROM accounts")}
        missing_accounts = [a["name"] for a in accounts if a["id"] not in live_accounts]
        top = int(copy.scalar("SELECT COALESCE(MAX(id), 0) FROM transactions") or 0)
        b = copy.one("SELECT COUNT(*) AS n FROM transactions")
        live_new = int(db.scalar("SELECT COUNT(*) FROM transactions WHERE id > ?", (top,)) or 0)
        same_hashes = int(db.scalar(
            "SELECT COUNT(*) FROM transactions WHERE id <= ? AND hash IN (SELECT value FROM json_each(?))",
            (top, __import__("json").dumps([r["hash"] for r in copy.query("SELECT hash FROM transactions")]))) or 0)
        gone = b["n"] - same_hashes
        out.update({"backup_transactions": b["n"], "live_new": live_new, "gone": gone,
                    "accounts": len(accounts), "missing_accounts": missing_accounts})
        text = f"Alle {b['n']} Buchungen der Kopie sind auch im laufenden Bestand." if gone == 0 else \
            f"{gone} Buchungen der Kopie fehlen im laufenden Bestand; sie wurden seither gelöscht oder zusammengeführt."
        if live_new:
            text += f" Seit der Kopie sind {live_new} Buchungen dazugekommen; die fehlten nach einer Wiederherstellung."
        if missing_accounts:
            text += f" Konten nur in der Kopie: {', '.join(missing_accounts[:5])}."
        # Gelöschtes und Neues seit der Kopie ist normal. Falsch wäre eine leere Kopie neben einem vollen Bestand.
        live_total = int(db.scalar("SELECT COUNT(*) FROM transactions") or 0)
        step("compare", b["n"] > 0 or live_total == 0, text if b["n"] or not live_total else
             f"Die Kopie enthält keine Buchungen, der laufende Bestand {live_total}.")
        # 5. Was die Kopie nicht enthält
        receipts = receipts_state(db)
        step("outside", True,
             "Nicht in der Kopie: Belegdateien" + (f" ({receipts['count']})" if receipts["count"] else "") +
             ", gespeicherte PINs und der Enable-Banking-Schlüssel. Belege kommen mit dem Home-Assistant-Backup "
             "oder der vollständigen Sicherung zurück; Bankzugänge gibst du nach einer Wiederherstellung neu frei.")
        out["ok"] = all(s["ok"] for s in out["steps"])
        return out
    except (OSError, sqlite3.Error) as error:
        step("error", False, f"Abgebrochen: {error}")
        return out
    finally:
        if copy is not None:
            try:
                copy.close()
            except sqlite3.Error:
                pass
        shutil.rmtree(work, ignore_errors=True)
