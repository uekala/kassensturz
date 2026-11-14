"""Eigene Sicherungskopien der Datenbank in /data/backups.

Ergänzt die Home-Assistant-Backups: eine Kopie pro Tag und eine vor dem ersten
Start einer neuen Version. Die Kopien entstehen über die Backup-Funktion von
SQLite und sind deshalb auch im laufenden Betrieb in sich stimmig.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

from . import db as dbmod

log = logging.getLogger("kassensturz.backup")

KEEP_DAILY = 7
KEEP_PRE_UPDATE = 3
VERSION_KEY = "app_version"


def folder() -> Path:
    return dbmod.DATA_DIR / "backups"


def _prepare_folder() -> Path:
    path = folder()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    return path


def _copy(source: sqlite3.Connection, target: Path) -> None:
    """Schreibt erst in eine Nebendatei, damit nie eine halbe Kopie liegen bleibt."""
    tmp = target.with_name(target.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.close(fd)
    dest = sqlite3.connect(str(tmp))
    try:
        source.backup(dest)
    finally:
        dest.close()
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)


def _prune(prefix: str, keep: int) -> None:
    files = sorted(folder().glob(f"{prefix}-*.sqlite"))
    for old in files[:-keep] if keep else files:
        try:
            old.unlink()
        except OSError:
            log.warning("Alte Sicherungskopie ließ sich nicht löschen: %s", old.name)


def snapshot(database: dbmod.Database, today: date | None = None) -> Path:
    """Legt die Tageskopie an (oder ersetzt sie) und räumt ältere auf."""
    target = _prepare_folder() / f"daily-{(today or date.today()).isoformat()}.sqlite"
    with database.lock:
        if database._depth:
            raise RuntimeError("Sicherungskopie nicht innerhalb einer Transaktion möglich.")
        _copy(database.conn, target)
    _prune("daily", KEEP_DAILY)
    return target


def run_if_due(database: dbmod.Database, today: date | None = None) -> Path | None:
    """Einmal am Tag; der Dateiname ist das Gedächtnis."""
    day = today or date.today()
    if (folder() / f"daily-{day.isoformat()}.sqlite").exists():
        return None
    target = snapshot(database, day)
    log.info("Sicherungskopie der Datenbank angelegt: %s", target.name)
    return target


def before_update(path: Path, version: str) -> Path | None:
    """Kopie des bisherigen Stands, bevor eine neue Version die Datenbank öffnet.

    Liest dazu nur die gespeicherte Versionsnummer. Schlägt die Kopie fehl,
    startet die App trotzdem; der Fehler steht im Protokoll.
    """
    try:
        if not path.exists() or path.stat().st_size == 0:
            return None
        source = sqlite3.connect(str(path))
        try:
            try:
                row = source.execute("SELECT value FROM settings WHERE key = ?", (VERSION_KEY,)).fetchone()
            except sqlite3.OperationalError:
                row = None
            previous = (row[0] if row else "") or ""
            if previous.strip('"') == version:
                return None
            label = re.sub(r"[^0-9A-Za-z.]+", "", previous) or "unbekannt"
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            target = _prepare_folder() / f"pre-update-{stamp}-von-{label}.sqlite"
            _copy(source, target)
        finally:
            source.close()
        _prune("pre-update", KEEP_PRE_UPDATE)
        log.info("Stand vor dem Versionswechsel gesichert: %s", target.name)
        return target
    except (OSError, sqlite3.Error):
        log.exception("Sicherungskopie vor dem Versionswechsel fehlgeschlagen")
        return None


def newest() -> Path | None:
    """Die jüngste Sicherungskopie, egal welcher Art."""
    try:
        files = [f for f in folder().glob("*.sqlite") if f.is_file() and not f.is_symlink()]
    except OSError:
        return None
    return max(files, key=lambda f: f.stat().st_mtime, default=None)


def verify(path: Path) -> dict:
    """Öffnet eine Sicherungskopie nur lesend und prüft sie vollständig.

    Das ist die Probe, ob sich aus der Kopie wiederherstellen ließe: Die Datei
    muss sich öffnen lassen, in sich stimmig sein und Konten und Buchungen enthalten.
    """
    out = {"name": path.name, "bytes": 0, "ok": False, "integrity": "", "accounts": 0, "transactions": 0,
           "newest_booking": None, "created": None}
    try:
        stat = path.stat()
        out["bytes"] = stat.st_size
        out["created"] = datetime.fromtimestamp(stat.st_mtime).replace(microsecond=0).isoformat()
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = conn.execute("PRAGMA integrity_check(1)").fetchone()
            out["integrity"] = str(row[0]) if row else "keine Antwort"
            out["accounts"] = int(conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0])
            out["transactions"] = int(conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
            out["newest_booking"] = conn.execute("SELECT MAX(booking_date) FROM transactions").fetchone()[0]
        finally:
            conn.close()
        out["ok"] = out["integrity"] == "ok"
    except (OSError, sqlite3.Error) as error:
        out["integrity"] = str(error)
    return out
