"""Ladevorgänge aus Ladecockpit: kWh, Preis und Ort zu den Buchungen, mit denen die Bank sie abgerechnet hat.

Zwei Wege hinein, beide nur lesend:
- Home Assistant: Ladecockpit veröffentlicht ``sensor.ladecockpit_last_charge`` mit dem jüngsten Ladevorgang.
  Kassensturz liest ihn höchstens alle fünf Minuten und merkt sich jeden neuen.
- Datei: der CSV-Export von Ladecockpit (deutsch oder englisch) für die Ladevorgänge davor.

Ein Ladevorgang legt nie eine Buchung an; die Abbuchung kommt von der Bank. Er wird nur einer Buchung mit genau
diesem Betrag zugeordnet, die bis zu einen Tag vor und sieben Tage nach dem Laden gebucht wurde.
"""
from __future__ import annotations

import csv
import io
import re
import time
from datetime import date, datetime, timedelta

from . import ha
from .db import Database, now_iso

SENSOR = "sensor.ladecockpit_last_charge"
POLL_SECONDS = 300
MAX_ROWS = 20_000
_last_poll = 0.0

# Spalten des Exports; deutsche und englische Kopfzeile
_COLUMNS = {
    "date": ("Datum", "Date"), "start": ("Start",), "site": ("Standort", "Site"), "kwh": ("kWh",),
    "idle": ("Blockiergebühr", "Idle fee"), "total": ("Summe", "Total"), "currency": ("Währung", "Currency"),
    "id": ("Ladung-ID", "Session ID"), "network": ("Netz", "Network"),
}


class ImportError_(ValueError):
    pass


def _cents(value) -> int | None:
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError):
        return None


def _wh(value) -> int | None:
    try:
        wh = round(float(value) * 1000)
    except (TypeError, ValueError):
        return None
    return wh if 0 < wh <= 1_000_000 else None


def _store(db: Database, row: dict, source: str) -> bool:
    """Legt einen Ladevorgang an, den es noch nicht gibt. Bestehende bleiben, wie sie sind."""
    if db.scalar("SELECT 1 FROM charging_sessions WHERE session_id = ?", (row["session_id"],)):
        return False
    db.insert("charging_sessions", {**row, "source": source, "created": now_iso()})
    return True


def from_sensor(data: dict | None) -> dict | None:
    """Der Ladevorgang aus dem Sensor von Ladecockpit; ``None``, wenn der Sensor nichts Brauchbares meldet."""
    if not isinstance(data, dict):
        return None
    attrs = data.get("attributes") or {}
    session_id = str(attrs.get("session_id") or "").strip()[:80]
    started = str(attrs.get("start") or "")[:32]
    wh = _wh(attrs.get("energy_kwh"))
    total = _cents(data.get("state"))
    if not session_id or not wh or total is None or total <= 0 or not re.match(r"\d{4}-\d{2}-\d{2}", started):
        return None
    if attrs.get("unit_of_measurement") not in (None, "EUR", "€"):
        return None
    return {"session_id": session_id, "started": started, "site": str(attrs.get("site") or "")[:120] or None,
            "network": str(attrs.get("network") or "supercharger")[:20], "kwh_wh": wh, "total_cents": total,
            "idle_cents": _cents(attrs.get("idle_fee")) or 0}


def poll(db: Database, force: bool = False) -> bool:
    """Holt den jüngsten Ladevorgang aus Home Assistant, höchstens alle fünf Minuten."""
    global _last_poll
    if not ha.available() or (not force and time.monotonic() - _last_poll < POLL_SECONDS):
        return False
    _last_poll = time.monotonic()
    row = from_sensor(ha.state(SENSOR))
    added = bool(row) and _store(db, row, "ha")
    if added:
        match(db)
    return added


def _number(text: str) -> float | None:
    text = (text or "").strip().replace("\u00a0", "")
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def import_csv(db: Database, raw: bytes) -> dict:
    """Liest den CSV-Export von Ladecockpit. Gibt zurück, wie viele neu sind und wie viele es schon gab."""
    text = raw.decode("utf-8-sig", errors="replace")
    first = text.split("\n", 1)[0]
    sep = ";" if first.count(";") > first.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=sep))
    if not rows:
        raise ImportError_("Die Datei ist leer.")
    header = [h.strip() for h in rows[0]]
    index = {}
    for key, names in _COLUMNS.items():
        index[key] = next((header.index(n) for n in names if n in header), None)
    if None in (index["date"], index["kwh"], index["total"], index["id"]):
        raise ImportError_("Das ist kein Export von Ladecockpit. Erwartet wird die Datei „Ladevorgänge als CSV“.")
    added = known = skipped = 0
    for cells in rows[1:MAX_ROWS + 1]:
        def cell(key):
            i = index.get(key)
            return cells[i].strip() if i is not None and i < len(cells) else ""
        if not any(c.strip() for c in cells):
            continue
        day = cell("date")
        try:
            day = (datetime.strptime(day, "%d.%m.%Y") if "." in day else datetime.strptime(day, "%Y-%m-%d")).date()
        except ValueError:
            skipped += 1
            continue
        start = cell("start") if re.fullmatch(r"\d{1,2}:\d{2}", cell("start")) else "00:00"
        kwh, total, idle = _number(cell("kwh")), _number(cell("total")), _number(cell("idle"))
        wh = _wh(kwh)
        if not cell("id") or not wh or total is None or total <= 0 or cell("currency") not in ("", "EUR"):
            skipped += 1
            continue
        network = "multipass" if cell("network").lower() == "multipass" else "supercharger"
        row = {"session_id": cell("id")[:80], "started": f"{day.isoformat()}T{start.zfill(5)}:00",
               "site": cell("site")[:120] or None, "network": network, "kwh_wh": wh,
               "total_cents": round(total * 100), "idle_cents": round((idle or 0) * 100)}
        if _store(db, row, "csv"):
            added += 1
        else:
            known += 1
    linked = match(db)
    return {"added": added, "known": known, "skipped": skipped, "linked": linked}


_TESLA = re.compile(r"tesla|supercharg", re.I)


def match(db: Database) -> int:
    """Ordnet offene Ladevorgänge eindeutig passenden Abbuchungen zu. Gibt zurück, wie viele neu zugeordnet sind."""
    linked = 0
    for s in db.query("SELECT * FROM charging_sessions WHERE tx_id IS NULL ORDER BY started"):
        day = date.fromisoformat(s["started"][:10])
        candidates = db.query(
            "SELECT t.id, t.counterparty, t.purpose FROM transactions t JOIN accounts a ON a.id = t.account_id "
            "WHERE a.archived = 0 AND t.amount_cents = ? AND t.booking_date BETWEEN ? AND ? "
            "AND t.id NOT IN (SELECT tx_id FROM charging_sessions WHERE tx_id IS NOT NULL) ORDER BY t.booking_date",
            (-s["total_cents"], (day - timedelta(days=1)).isoformat(), (day + timedelta(days=7)).isoformat()))
        named = [c for c in candidates if _TESLA.search(f"{c['counterparty'] or ''} {c['purpose'] or ''}")]
        pick = named if named else candidates
        if len(pick) == 1:
            db.execute("UPDATE charging_sessions SET tx_id = ? WHERE id = ?", (pick[0]["id"], s["id"]))
            linked += 1
    return linked


def prune(db: Database) -> None:
    """Löst Zuordnungen zu Buchungen, die es nicht mehr gibt."""
    db.execute("UPDATE charging_sessions SET tx_id = NULL WHERE tx_id IS NOT NULL "
               "AND tx_id NOT IN (SELECT id FROM transactions)")


def public(s: dict) -> dict:
    kwh = s["kwh_wh"] / 1000
    return {"id": s["id"], "started": s["started"], "site": s["site"], "network": s["network"],
            "kwh": round(kwh, 2), "total_cents": s["total_cents"], "idle_cents": s["idle_cents"],
            "price_per_kwh_cents": round(s["total_cents"] / kwh, 1) if kwh else None, "tx_id": s["tx_id"]}


def for_transactions(db: Database, tx_ids: list[int]) -> dict[int, dict]:
    if not tx_ids:
        return {}
    marks = ",".join("?" * len(tx_ids))
    rows = db.query(f"SELECT * FROM charging_sessions WHERE tx_id IN ({marks})", tuple(tx_ids))
    return {r["tx_id"]: public(r) for r in rows}


def summary(db: Database, months: int = 12) -> dict:
    """Je Monat: Ladevorgänge, kWh, Kosten und Preis je kWh; dazu, was noch keiner Buchung zugeordnet ist."""
    rows = db.query("SELECT substr(started, 1, 7) AS month, COUNT(*) AS sessions, SUM(kwh_wh) AS wh, "
                    "SUM(total_cents) AS cents, SUM(idle_cents) AS idle FROM charging_sessions "
                    "GROUP BY month ORDER BY month DESC LIMIT ?", (max(1, min(months, 60)),))
    out = [{"month": r["month"], "sessions": r["sessions"], "kwh": round(r["wh"] / 1000, 1), "total_cents": r["cents"],
            "idle_cents": r["idle"], "price_per_kwh_cents": round(r["cents"] * 1000 / r["wh"], 1) if r["wh"] else None}
           for r in rows]
    open_rows = db.query("SELECT * FROM charging_sessions WHERE tx_id IS NULL ORDER BY started DESC LIMIT 20")
    count = int(db.scalar("SELECT COUNT(*) FROM charging_sessions") or 0)
    return {"months": out, "count": count, "unlinked": [public(r) for r in open_rows],
            "unlinked_count": int(db.scalar("SELECT COUNT(*) FROM charging_sessions WHERE tx_id IS NULL") or 0)}
