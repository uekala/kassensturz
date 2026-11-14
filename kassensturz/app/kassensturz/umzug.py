"""Umzug der Datenbank in eine andere Kassensturz-Installation.

Die alte Installation liefert über die Oberfläche eine vollständige, in sich
stimmige Kopie der Datenbank. Die neue übernimmt sie beim Start aus dem
Eingangsordner – aber nur, solange sie selbst noch keine Konten und Umsätze
hat. Eine Installation mit Daten wird nie überschrieben.

Gespeicherte PINs und der Enable-Banking-Schlüssel liegen nicht in der
Datenbank und ziehen deshalb nicht mit um.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

log = logging.getLogger("kassensturz.umzug")

SUBFOLDER = "umzug"
FILENAME = "kassensturz-umzug.sqlite"
REQUIRED_TABLES = {"accounts", "transactions", "settings"}

# Vollständige Sicherung: Datenbank und Belege in einer Datei.
ARCHIVE = "kassensturz-sicherung.zip"
ARCHIVE_DB = "kassensturz.sqlite"
ARCHIVE_MANIFEST = "manifest.json"
ARCHIVE_FORMAT = 1
RECEIPT_FOLDER = "belege"
RECEIPT_NAME = re.compile(r"[0-9a-f]{32}\.(jpg|png|webp|pdf)")
MAX_RECEIPT_BYTES = 10 * 1024 * 1024
MAX_DB_BYTES = 2 * 1024 * 1024 * 1024
MAX_MEMBERS = 50_000


def incoming(inbox: Path | None) -> Path | None:
    """Pfad der abgelegten Umzugsdatei oder None. Die vollständige Sicherung hat Vorrang."""
    if not inbox:
        return None
    for name in (ARCHIVE, FILENAME):
        path = inbox / SUBFOLDER / name
        try:
            if not path.is_symlink() and path.is_file():
                return path
        except OSError:
            continue
    return None


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_archive(source: sqlite3.Connection, data_dir: Path, target: Path, version: str) -> dict:
    """Datenbank und alle Belege, auf die sie verweist, in eine ZIP-Datei.

    Das Verzeichnis nennt zu jeder Datei Größe und Prüfsumme; damit merkt die
    Übernahme, wenn unterwegs etwas verloren ging oder verändert wurde.
    """
    work = Path(tempfile.mkdtemp(prefix="kassensturz-archiv-"))
    copy = work / ARCHIVE_DB
    try:
        write_copy(source, copy)
        files = {ARCHIVE_DB: {"bytes": copy.stat().st_size, "sha256": _sha256(copy)}}
        check = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
        try:
            stored = [r[0] for r in check.execute("SELECT stored FROM receipts ORDER BY id")] if "receipts" in _tables(check) else []
        finally:
            check.close()
        receipts, missing = [], 0
        for name in stored:
            path = data_dir / RECEIPT_FOLDER / (name or "-")
            if not RECEIPT_NAME.fullmatch(name or "") or path.is_symlink() or not path.is_file():
                missing += 1
                continue
            files[f"{RECEIPT_FOLDER}/{name}"] = {"bytes": path.stat().st_size, "sha256": _sha256(path)}
            receipts.append(path)
        manifest = {"format": ARCHIVE_FORMAT, "app_version": version,
                    "created": datetime.now().replace(microsecond=0).isoformat(),
                    "receipts": len(receipts), "missing_receipts": missing, "files": files}
        tmp = target.with_name(target.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as raw, zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            archive.writestr(ARCHIVE_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=1))
            archive.write(copy, ARCHIVE_DB)
            for path in receipts:
                # Fotos und PDF sind schon gepackt.
                archive.write(path, f"{RECEIPT_FOLDER}/{path.name}", compress_type=zipfile.ZIP_STORED)
        os.replace(tmp, target)
        return manifest
    finally:
        copy.unlink(missing_ok=True)
        try:
            work.rmdir()
        except OSError:
            pass


def _extract(archive: zipfile.ZipFile, name: str, expected: dict, target: Path, limit: int) -> None:
    """Eine Datei aus dem Archiv, höchstens so groß wie angekündigt, mit geprüfter Summe."""
    size = expected.get("bytes")
    if not isinstance(size, int) or not 0 <= size <= limit or archive.getinfo(name).file_size != size:
        raise ValueError(f"Die Größe von {name} passt nicht.")
    digest = hashlib.sha256()
    written = 0
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as out, archive.open(name) as member:
        while True:
            block = member.read(1024 * 1024)
            if not block:
                break
            written += len(block)
            if written > size:
                raise ValueError(f"{name} ist größer als angekündigt.")
            digest.update(block)
            out.write(block)
    if written != size or digest.hexdigest() != expected.get("sha256"):
        raise ValueError(f"Die Prüfsumme von {name} stimmt nicht.")


def _adopt_archive(source_path: Path, path: Path) -> int:
    """Übernimmt Datenbank und Belege aus einer vollständigen Sicherung. Gibt die Zahl der Belege zurück."""
    data_dir = path.parent
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    work = Path(tempfile.mkdtemp(prefix="umzug-", dir=data_dir))
    try:
        with zipfile.ZipFile(source_path) as archive:
            names = archive.namelist()
            if len(names) > MAX_MEMBERS or len(set(names)) != len(names):
                raise ValueError("Die Sicherung hat einen unerwarteten Aufbau.")
            try:
                manifest = json.loads(archive.read(ARCHIVE_MANIFEST)[: 16 * 1024 * 1024])
            except (KeyError, ValueError):
                raise ValueError("Der Sicherung fehlt das Verzeichnis.") from None
            files = manifest.get("files") if isinstance(manifest, dict) else None
            if not isinstance(files, dict) or manifest.get("format") != ARCHIVE_FORMAT or ARCHIVE_DB not in files:
                raise ValueError("Die Sicherung ist keine vollständige Kassensturz-Sicherung.")
            if set(names) != set(files) | {ARCHIVE_MANIFEST}:
                raise ValueError("Inhalt und Verzeichnis der Sicherung passen nicht zusammen.")
            receipts = [n for n in files if n != ARCHIVE_DB]
            for name in receipts:
                folder, _, base = name.partition("/")
                if folder != RECEIPT_FOLDER or not RECEIPT_NAME.fullmatch(base):
                    raise ValueError("Die Sicherung enthält eine unerwartete Datei.")
            # Erst alles in einen Arbeitsordner und prüfen, dann an den Platz schieben.
            database = work / ARCHIVE_DB
            _extract(archive, ARCHIVE_DB, files[ARCHIVE_DB], database, MAX_DB_BYTES)
            source = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
            try:
                _check(source)
            finally:
                source.close()
            (work / RECEIPT_FOLDER).mkdir(mode=0o700)
            for name in receipts:
                _extract(archive, name, files[name], work / name, MAX_RECEIPT_BYTES)
        target_folder = data_dir / RECEIPT_FOLDER
        target_folder.mkdir(exist_ok=True, mode=0o700)
        os.chmod(target_folder, 0o700)
        for name in receipts:
            os.replace(work / name, target_folder / name.partition("/")[2])
        source = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        try:
            write_copy(source, path)
        finally:
            source.close()
        return len(receipts)
    finally:
        for leftover in sorted(work.rglob("*"), reverse=True):
            try:
                leftover.rmdir() if leftover.is_dir() else leftover.unlink()
            except OSError:
                pass
        try:
            work.rmdir()
        except OSError:
            pass


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
                "bitte %s/%s löschen.", SUBFOLDER, source_path.name,
            )
            return False
        receipts = None
        if source_path.name == ARCHIVE:
            receipts = _adopt_archive(source_path, path)
        else:
            source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
            try:
                _check(source)
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                write_copy(source, path)
            finally:
                source.close()
        for suffix in ("-wal", "-shm"):
            Path(str(path) + suffix).unlink(missing_ok=True)
    except (OSError, sqlite3.Error, ValueError, zipfile.BadZipFile) as error:
        log.error("Umzugsdatei nicht übernommen: %s", error)
        return False
    try:
        source_path.unlink()
    except OSError:
        log.warning("Daten übernommen. Bitte %s/%s von Hand löschen.", SUBFOLDER, source_path.name)
    if receipts is None:
        log.info("Daten aus der Umzugsdatei übernommen.")
    else:
        log.info("Daten aus der vollständigen Sicherung übernommen, dazu %d Belege.", receipts)
    return True
