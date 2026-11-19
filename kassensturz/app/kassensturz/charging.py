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
    "id": ("Ladung-ID", "Session ID"), "network": ("Netz", "Network"), "net": ("Netto", "Net"),
}

_HEADERS = ("Datum;Start;Ende;Standort;kWh", "Date,Start,End,Site,kWh")


def looks_like_export(raw: bytes) -> bool:
    """Ob eine Datei der CSV-Export von Ladecockpit ist, an der Kopfzeile erkannt."""
    head = raw[:400].decode("utf-8", errors="replace").lstrip("\ufeff").lstrip()
    return head.startswith(_HEADERS)


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
        raise ImportError_("Das ist kein Export von Ladecockpit. Erwartet wird die Datei „CSV – alle Ladungen“.")
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
        # Abgebucht wird der Betrag nach Gutschriften (Netto), sonst die Summe.
        net = _number(cell("net"))
        if net is not None and net > 0:
            total = net
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


# Wer Ladestrom abrechnet: Tesla selbst und die großen Netze, die in Ladecockpit auftauchen
_TESLA = re.compile(r"tesla|supercharg|ionity|enbw|fastned|allego|aral ?pulse|ewe ?go|maingau|elli\b", re.I)
# Kreditkarten buchen teils erst Wochen später; mit „Tesla“ im Text wird darum weiter gesucht.
NAMED_DAYS = 35
# Fasst die Bank mehrere Ladevorgänge zu einer Abbuchung zusammen, liegen sie höchstens so lange davor.
GROUP_DAYS = 40


def _named(t: dict) -> bool:
    return bool(_TESLA.search(f"{t.get('counterparty') or ''} {t.get('purpose') or ''}"))


def _used() -> str:
    return "SELECT tx_id FROM charging_sessions WHERE tx_id IS NOT NULL"


def _candidates(db: Database, cents: int, start: date, days: int) -> list[dict]:
    return db.query(
        "SELECT t.id, t.counterparty, t.purpose, t.booking_date FROM transactions t JOIN accounts a ON a.id = t.account_id "
        f"WHERE a.archived = 0 AND t.amount_cents = ? AND t.booking_date BETWEEN ? AND ? AND t.id NOT IN ({_used()}) "
        "ORDER BY t.booking_date",
        (-cents, (start - timedelta(days=1)).isoformat(), (start + timedelta(days=days)).isoformat()))


def match(db: Database) -> int:
    """Ordnet offene Ladevorgänge eindeutig passenden Abbuchungen zu. Gibt zurück, wie viele neu zugeordnet sind.

    1. Gleicher Betrag, gebucht bis 7 Tage danach; bei mehreren gewinnt die mit „Tesla“ im Text.
    2. Gleicher Betrag mit „Tesla“ im Text, bis 35 Tage danach.
    3. Eine Abbuchung mit „Tesla“ im Text, deren Betrag genau die Summe aufeinanderfolgender Ladevorgänge der
       40 Tage davor ist: Dann hat die Bank sie zusammengefasst.
    Ist etwas nicht eindeutig, bleibt es offen."""
    linked = 0
    for s in db.query("SELECT * FROM charging_sessions WHERE tx_id IS NULL ORDER BY started"):
        day = date.fromisoformat(s["started"][:10])
        found = _candidates(db, s["total_cents"], day, 7)
        named = [c for c in found if _named(c)]
        pick = named if named else found
        if len(pick) != 1:
            pick = [c for c in _candidates(db, s["total_cents"], day, NAMED_DAYS) if _named(c)]
        if len(pick) == 1:
            db.execute("UPDATE charging_sessions SET tx_id = ? WHERE id = ?", (pick[0]["id"], s["id"]))
            linked += 1
    linked += _match_groups(db)
    return linked


def _match_groups(db: Database) -> int:
    open_rows = db.query("SELECT id, started, total_cents FROM charging_sessions WHERE tx_id IS NULL ORDER BY started")
    if len(open_rows) < 2:
        return 0
    first = date.fromisoformat(open_rows[0]["started"][:10])
    bookings = [t for t in db.query(
        "SELECT t.id, t.counterparty, t.purpose, t.booking_date, t.amount_cents FROM transactions t "
        "JOIN accounts a ON a.id = t.account_id WHERE a.archived = 0 AND t.amount_cents < 0 AND t.booking_date >= ? "
        f"AND t.id NOT IN ({_used()}) ORDER BY t.booking_date", (first.isoformat(),)) if _named(t)]
    linked = 0
    taken: set[int] = set()
    for t in bookings:
        booked = date.fromisoformat(t["booking_date"])
        window = [s for s in open_rows if s["id"] not in taken
                  and booked - timedelta(days=GROUP_DAYS) <= date.fromisoformat(s["started"][:10]) <= booked + timedelta(days=1)]
        target = -t["amount_cents"]
        # Rückwärts vom jüngsten Ladevorgang vor der Buchung aufsummieren
        hits = []
        for end in range(len(window) - 1, -1, -1):
            total, run = 0, []
            for s in reversed(window[:end + 1]):
                total += s["total_cents"]
                run.append(s)
                if total >= target:
                    break
            if total == target and len(run) >= 2:
                hits.append(run)
        if len(hits) == 1:
            for s in hits[0]:
                db.execute("UPDATE charging_sessions SET tx_id = ? WHERE id = ?", (t["id"], s["id"]))
                taken.add(s["id"])
            linked += len(hits[0])
    return linked


def link(db: Database, session_id: int, tx_id: int | None) -> None:
    """Ordnet einen Ladevorgang von Hand einer Buchung zu oder löst die Zuordnung (``None``)."""
    if not db.scalar("SELECT 1 FROM charging_sessions WHERE id = ?", (session_id,)):
        raise ValueError("Ladevorgang nicht gefunden.")
    if tx_id is not None and not db.scalar("SELECT 1 FROM transactions WHERE id = ? AND amount_cents < 0", (tx_id,)):
        raise ValueError("Buchung nicht gefunden.")
    db.execute("UPDATE charging_sessions SET tx_id = ? WHERE id = ?", (tx_id, session_id))


def suggestions(db: Database, session_id: int) -> list[dict]:
    """Buchungen, die zu einem offenen Ladevorgang passen könnten: gleicher Betrag oder „Tesla“ im Text, ±40 Tage."""
    s = db.one("SELECT * FROM charging_sessions WHERE id = ?", (session_id,))
    if not s:
        return []
    day = date.fromisoformat(s["started"][:10])
    rows = db.query(
        "SELECT t.id, t.booking_date, t.amount_cents, t.counterparty, t.purpose, a.name AS account_name FROM transactions t "
        "JOIN accounts a ON a.id = t.account_id WHERE a.archived = 0 AND t.amount_cents < 0 AND t.booking_date BETWEEN ? AND ? "
        "ORDER BY ABS(julianday(t.booking_date) - julianday(?)), t.id",
        ((day - timedelta(days=GROUP_DAYS)).isoformat(), (day + timedelta(days=GROUP_DAYS)).isoformat(), day.isoformat()))
    out = [r for r in rows if r["amount_cents"] == -s["total_cents"] or _named(r)]
    return out[:15]


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
    rows = db.query(f"SELECT * FROM charging_sessions WHERE tx_id IN ({marks}) ORDER BY started", tuple(tx_ids))
    grouped: dict[int, list[dict]] = {}
    for r in rows:
        grouped.setdefault(r["tx_id"], []).append(r)
    out = {}
    for tx, group in grouped.items():
        if len(group) == 1:
            out[tx] = {**public(group[0]), "count": 1}
            continue
        wh, cents = sum(g["kwh_wh"] for g in group), sum(g["total_cents"] for g in group)
        out[tx] = {"id": group[0]["id"], "started": group[0]["started"], "site": f"{len(group)} Ladevorgänge",
                   "network": group[0]["network"], "kwh": round(wh / 1000, 2), "total_cents": cents,
                   "idle_cents": sum(g["idle_cents"] for g in group),
                   "price_per_kwh_cents": round(cents * 1000 / wh, 1) if wh else None, "tx_id": tx, "count": len(group)}
    return out


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
    first = db.scalar("SELECT MIN(started) FROM charging_sessions")
    named = [t for t in db.query(
        "SELECT t.id, t.counterparty, t.purpose FROM transactions t WHERE t.amount_cents < 0 AND t.booking_date >= ? "
        f"AND t.id NOT IN ({_used()})", ((first or "9999")[:10],)) if _named(t)] if first else []
    return {"months": out, "count": count, "unlinked": [public(r) for r in open_rows],
            "free_tesla_bookings": len(named),
            "unlinked_count": int(db.scalar("SELECT COUNT(*) FROM charging_sessions WHERE tx_id IS NULL") or 0)}
