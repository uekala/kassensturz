"""Eingangsordner: Kontoauszug-Dateien, die dort landen, werden automatisch importiert.

Der Ordner liegt in der Home-Assistant-Freigabe (/share), damit man ihn per Samba, über die Dateien-App am iPhone
oder mit einer Sync-App erreicht. Erfolgreich importierte Dateien wandern nach „importiert“."""
from __future__ import annotations

import logging
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from . import importers, ledger, options
from .db import Database, now_iso

log = logging.getLogger("kassensturz.inbox")

SUFFIXES = {".csv", ".txt", ".xml", ".zip", ".sta", ".mt940", ".940"}
DONE_DIR = "importiert"


def folder() -> Path | None:
    if "KASSENSTURZ_INBOX" in os.environ:
        raw = os.environ["KASSENSTURZ_INBOX"]
    else:
        raw = options.load().get("import_folder") or ""
    raw = raw.strip()
    if not raw:
        return None
    return Path(raw)


def ensure_folder() -> Path | None:
    p = folder()
    if not p:
        return None
    try:
        (p / DONE_DIR).mkdir(parents=True, exist_ok=True)
        readme = p / "LIESMICH.md"
        if not readme.exists():
            readme.write_text(
                "Kontoauszug-Dateien (CSV, CAMT, MT940) hier ablegen.\n"
                "Kassensturz importiert sie innerhalb einer Minute und verschiebt sie danach in den Ordner „importiert“.\n"
                "Dateien, deren Konto Kassensturz nicht erkennt, bleiben liegen und lassen sich unter Konten zuordnen.\n",
                "utf-8")
        return p
    except OSError as exc:
        log.warning("Eingangsordner %s nicht nutzbar: %s", p, exc)
        return None


def _candidates(p: Path) -> list[Path]:
    out = []
    for f in sorted(p.iterdir()):
        if f.is_file() and f.suffix.lower() in SUFFIXES and not f.name.startswith("."):
            out.append(f)
    return out


def match_account(db: Database, res: dict, filename: str) -> int | None:
    """Findet das Zielkonto ohne Rückfrage – oder None."""
    iban = (res.get("meta") or {}).get("iban")
    if iban:
        acc = db.one("SELECT id FROM accounts WHERE iban = ? AND archived = 0", (iban,))
        if acc:
            return acc["id"]
    sig = res.get("signature")
    if sig:
        prof = db.one("SELECT account_id FROM csv_profiles WHERE signature = ?", (sig,))
        if prof and db.one("SELECT id FROM accounts WHERE id = ? AND archived = 0", (prof["account_id"],)):
            return prof["account_id"]
    suggest = res.get("suggest") or {}
    name = (suggest.get("name") or "").lower()
    kind = suggest.get("kind")
    accounts = db.query("SELECT id, name, kind, settlement_pattern FROM accounts WHERE archived = 0")
    def has(word: str, text: str) -> bool:
        return bool(word) and re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", text or "") is not None

    if res.get("format") not in ("CSV", "CAMT", "CAMT (ZIP)", "MT940") and name:
        word = name.split()[0]
        hits = [a for a in accounts if has(word, a["name"].lower()) or has(word, (a["settlement_pattern"] or "").lower())]
        if len(hits) == 1:
            return hits[0]["id"]
        if kind == "paypal":
            pp = [a for a in accounts if a["kind"] == "paypal"]
            if len(pp) == 1:
                return pp[0]["id"]
    low = filename.lower()
    hits = [a for a in accounts if len(a["name"]) >= 3 and has(a["name"].lower().split()[0], low)]
    if len(hits) == 1:
        return hits[0]["id"]
    return None


def move_done(path: Path) -> None:
    target_dir = path.parent / DONE_DIR
    target_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    target = target_dir / f"{stamp}_{path.name}"
    n = 1
    while target.exists():
        target = target_dir / f"{stamp}_{n}_{path.name}"
        n += 1
    shutil.move(str(path), str(target))


def scan(db: Database) -> dict:
    """Ein Durchlauf: importiert, was eindeutig ist, merkt sich den Rest."""
    p = ensure_folder()
    result = {"imported": [], "pending": 0}
    if not p:
        return result
    seen = set()
    for f in _candidates(p):
        seen.add(f.name)
        try:
            st = f.stat()
        except OSError:
            continue
        if time.time() - st.st_mtime < 8:
            continue  # wird vermutlich noch geschrieben
        known = db.one("SELECT * FROM inbox WHERE filename = ?", (f.name,))
        if known and known["size"] == st.st_size and known["mtime"] == st.st_mtime:
            continue  # unverändert und schon bewertet
        try:
            data = f.read_bytes()
            res = importers.analyze(data, f.name)
            if res.get("signature"):
                prof = db.one("SELECT mapping FROM csv_profiles WHERE signature = ?", (res["signature"],))
                if prof:
                    import json
                    res = importers.analyze(data, f.name, json.loads(prof["mapping"]))
        except Exception as exc:  # noqa: BLE001
            _remember(db, f, st, "error", f"Datei nicht lesbar: {exc}", None, 0)
            continue
        if res.get("error") or not res.get("rows"):
            _remember(db, f, st, "error", res.get("error") or "Keine Buchungen gefunden.", res.get("format"), 0)
            continue
        account_id = match_account(db, res, f.name)
        if not account_id:
            _remember(db, f, st, "pending", "Konto nicht eindeutig – bitte zuordnen.", res.get("format"), res.get("count"))
            continue
        r = ledger.import_rows(db, account_id, res["rows"], "ordner", f.name, res.get("meta"))
        move_done(f)
        db.execute("DELETE FROM inbox WHERE filename = ?", (f.name,))
        acc = db.one("SELECT name FROM accounts WHERE id = ?", (account_id,))
        result["imported"].append({"file": f.name, "account": acc["name"] if acc else "?", "added": r["added"], "skipped": r["skipped"]})
        log.info("Eingangsordner: %s → %s (%s neu)", f.name, acc["name"] if acc else account_id, r["added"])
    if seen:
        db.execute(f"DELETE FROM inbox WHERE filename NOT IN ({','.join('?' * len(seen))})", tuple(seen))
    else:
        db.execute("DELETE FROM inbox")
    result["pending"] = db.scalar("SELECT COUNT(*) FROM inbox")
    return result


def _remember(db: Database, f: Path, st, status: str, message: str, fmt, count) -> None:
    db.execute("INSERT INTO inbox(filename, size, mtime, status, message, format, count, created) VALUES(?,?,?,?,?,?,?,?) "
               "ON CONFLICT(filename) DO UPDATE SET size=excluded.size, mtime=excluded.mtime, status=excluded.status, "
               "message=excluded.message, format=excluded.format, count=excluded.count",
               (f.name, st.st_size, st.st_mtime, status, message, fmt, count or 0, now_iso()))


def status(db: Database) -> dict:
    p = folder()
    recent = db.query("SELECT i.filename, i.created, i.added, i.skipped, a.name AS account FROM imports i "
                      "LEFT JOIN accounts a ON a.id = i.account_id WHERE i.source = 'ordner' ORDER BY i.id DESC LIMIT 5")
    return {
        "path": str(p) if p else None,
        "available": bool(p and p.exists()),
        "files": db.query("SELECT filename, status, message, format, count FROM inbox ORDER BY filename"),
        "recent": recent,
    }


def read_file(name: str) -> tuple[bytes, Path]:
    p = folder()
    if not p:
        raise FileNotFoundError(name)
    path = (p / name).resolve()
    if path.parent != p.resolve() or not path.is_file():
        raise FileNotFoundError(name)
    return path.read_bytes(), path


def delete_file(db: Database, name: str) -> None:
    _, path = read_file(name)
    path.unlink()
    db.execute("DELETE FROM inbox WHERE filename = ?", (name,))
