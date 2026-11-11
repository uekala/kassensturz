"""Umzug der Datenbank in eine andere Kassensturz-Installation.

Die alte Installation liefert über die Oberfläche eine vollständige, in sich
stimmige Kopie der Datenbank. Die neue übernimmt sie beim Start aus dem
Eingangsordner – aber nur, solange sie selbst noch keine Konten und Umsätze
hat. Eine Installation mit Daten wird nie überschrieben.

Gespeicherte PINs und der Enable-Banking-Schlüssel liegen nicht in der
Datenbank und ziehen deshalb nicht mit um.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

log = logging.getLogger("kassensturz.umzug")

SUBFOLDER = "umzug"
FILENAME = "kassensturz-umzug.sqlite"
REQUIRED_TABLES = {"accounts", "transactions", "settings"}


def incoming(inbox: Path | None) -> Path | None:
    """Pfad der abgelegten Umzugsdatei oder None."""
    if not inbox:
        return None
    path = inbox / SUBFOLDER / FILENAME
    try:
        if path.is_symlink() or not path.is_file():
            return None
    except OSError:
        return None
    return path


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _has_data(path: Path) -> bool:
    """True, wenn die Datenbank schon Konten oder Umsätze enthält."""
    if not path.exists() or path.stat().st_size == 0:
        return False
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = _tables(conn)
        for table in ("accounts", "transactions"):
            if table in tables and conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                return True
        return False
    finally:
        conn.close()


def _check(source: sqlite3.Connection) -> None:
    result = source.execute("PRAGMA integrity_check").fetchone()
    if not result or result[0] != "ok":
        raise ValueError("Die Umzugsdatei ist beschädigt.")
    missing = REQUIRED_TABLES - _tables(source)
    if missing:
        raise ValueError("Die Umzugsdatei ist keine Kassensturz-Datenbank.")


def write_copy(source: sqlite3.Connection, target: Path) -> None:
    """Stimmige Kopie über die Backup-Funktion von SQLite, nur für den Besitzer lesbar."""
    tmp = target.with_name(target.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.close(fd)
    dest = sqlite3.connect(str(tmp))
    try:
        source.backup(dest)
        # Eine einzelne Datei ohne Nebendateien, damit sie sich kopieren lässt.
        dest.execute("PRAGMA journal_mode=DELETE")
    finally:
        dest.close()
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)


def adopt_if_fresh(path: Path, inbox: Path | None) -> bool:
    """Übernimmt eine abgelegte Umzugsdatei, wenn hier noch keine Daten liegen.

    Läuft vor dem Öffnen der Datenbank. Schlägt etwas fehl, bleibt alles, wie es
    ist, und die App startet normal; der Grund steht im Protokoll.
    """
    source_path = incoming(inbox)
    if source_path is None:
        return False
    try:
        if _has_data(path):
            log.warning(
                "Umzugsdatei gefunden, aber diese Installation hat schon Daten. Nichts übernommen; "
                "bitte %s/%s löschen.", SUBFOLDER, FILENAME,
            )
            return False
        source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
        try:
            _check(source)
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            write_copy(source, path)
        finally:
            source.close()
        for suffix in ("-wal", "-shm"):
            Path(str(path) + suffix).unlink(missing_ok=True)
    except (OSError, sqlite3.Error, ValueError) as error:
        log.error("Umzugsdatei nicht übernommen: %s", error)
        return False
    try:
        source_path.unlink()
    except OSError:
        log.warning("Daten übernommen. Bitte %s/%s von Hand löschen.", SUBFOLDER, FILENAME)
    log.info("Daten aus der Umzugsdatei übernommen.")
    return True
