"""Zahlungskalender: kommende Abbuchungen, Eingänge und Fristen als Kalender für Home Assistant.

Kassensturz stellt einen Kalender im iCalendar-Format bereit (eine .ics-Adresse). Home Assistant liest
ihn mit der eingebauten Integration „Remote Calendar“; danach gibt es eine Kalender-Entität, die im
Kalender von Home Assistant erscheint und Automationen auslösen kann („am Tag vor der Kfz-Steuer …“).

Die Integration kann sich nicht anmelden. Darum steckt ein langer Zufallsschlüssel in der Adresse,
und die Adresse ist nur im internen Netz von Home Assistant erreichbar, nicht über Tailscale und
nicht von außen. Der Kalender ist aus, bis jemand die Adresse erstellt; eine neue Adresse macht die
alte ungültig.

Im Kalender steht, was absehbar ist: Zahlungen aus Verträgen, geplante Ausgaben, letzte Tage für
Kündigungen, Fälligkeiten von Festgeld und Krediten, erwartete Eingänge, Sparziele und das Ende der
Bankfreigaben. Ganztägige Termine, ein Jahr im Voraus.
"""
from __future__ import annotations

import hmac
import ipaddress
import re
import secrets
import socket
from datetime import UTC, date, datetime, timedelta

from . import contracts as contracts_mod
from .db import Database
from .util import euro

SETTING = "calendar_token"
AHEAD_DAYS = 366
PORT = 8099
# Das interne Netz von Home Assistant: Core, Supervisor und die Apps.
HASSIO_NETWORK = ipaddress.ip_network("172.30.32.0/23")


def token(db: Database) -> str | None:
    value = db.get_setting(SETTING)
    return value if isinstance(value, str) and len(value) >= 32 else None


def switch(db: Database, action: str) -> str | None:
    """„on“ erstellt eine Adresse (oder behält die vorhandene), „renew“ ersetzt sie, „off“ schaltet ab."""
    if action not in ("on", "renew", "off"):
        raise ValueError("Unbekannte Aktion.")
    if action == "off":
        db.set_setting(SETTING, None)
        return None
    if action == "on" and token(db):
        return token(db)
    value = secrets.token_urlsafe(32)
    db.set_setting(SETTING, value)
    return value


def matches(db: Database, offered: str) -> bool:
    known = token(db)
    return bool(known) and hmac.compare_digest(known.encode(), offered.encode())


def peer_allowed(host: str | None) -> bool:
    """Home Assistant Core holt den Kalender aus seinem internen Netz; lokal geht es auch."""
    try:
        ip = ipaddress.ip_address(host or "")
    except ValueError:
        return False
    return ip.is_loopback or ip in HASSIO_NETWORK


FORWARD_HEADERS = ("x-forwarded-for", "x-forwarded-proto", "x-forwarded-host", "forwarded", "x-real-ip")


def forwarded(headers) -> bool:
    """Ob ein Proxy die Anfrage weitergereicht hat. Home Assistant Core fragt direkt, der Tailscale-Proxy nicht."""
    return any(headers.get(name) for name in FORWARD_HEADERS) or any(
        key.lower().startswith("tailscale-") for key in headers)


def address(value: str | None) -> str | None:
    """Die Adresse, wie Home Assistant sie im internen Netz erreicht: Name des Containers und Port."""
    if not value:
        return None
    return f"http://{socket.gethostname()}:{PORT}/calendar/{value}.ics"


def _day(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def events(db: Database, today: date | None = None) -> list[dict]:
    """Alle Termine von heute bis ein Jahr voraus, nach Tag sortiert."""
    today = today or date.today()
    end = today + timedelta(days=AHEAD_DAYS)
    out: list[dict] = []

    def add(uid: str, day: date | None, summary: str, description: str = "") -> None:
        if day and today <= day <= end:
            uid = re.sub(r"[^A-Za-z0-9._-]+", "-", uid).strip("-")[:80]
            out.append({"uid": f"{uid}-{day.isoformat()}@kassensturz", "date": day, "summary": summary,
                        "description": description})

    cons = contracts_mod.list_contracts(db)
    for u in contracts_mod.upcoming(db, today, end, cons):
        if u.get("overdue"):
            continue
        income = u["amount_cents"] > 0
        add(f"contract-{u['key']}", _day(u["date"]), f"{u['name']}: {'+' if income else ''}{euro(u['amount_cents'])}",
            "Erwarteter Eingang aus einem Vertrag." if income else "Erwartete Abbuchung aus einem Vertrag.")
    for c in cons:
        if c["status"] in ("cancelled", "ignored") or not c.get("deadline"):
            continue
        ends = _day(c.get("contract_end"))
        add(f"deadline-{c['key']}", _day(c["deadline"]), f"Letzter Tag zum Kündigen: {c['name']}",
            f"Kündigungsfrist {c['notice_months']} Monate" + (f", Vertrag endet sonst am {ends.strftime('%d.%m.%Y')}" if ends else "") + ".")
    for p in db.query("SELECT p.*, a.name AS account FROM planned_expenses p JOIN accounts a ON a.id = p.account_id "
                      "WHERE p.status = 'open'"):
        add(f"planned-{p['id']}", max(_day(p["due_date"]) or today, today), f"Geplant: {p['label']} {euro(-p['cents'])}",
            f"Geplante Ausgabe von {p['account']}." + (f" {p['note']}" if p["note"] else ""))
    for e in db.query("SELECT e.*, a.name AS account FROM expected_incomes e JOIN accounts a ON a.id = e.account_id "
                      "WHERE e.status = 'open' AND e.due_date IS NOT NULL"):
        add(f"expected-{e['id']}", _day(e["due_date"]), f"Geld steht aus: {e['label']} +{euro(e['cents'])}",
            f"Erwartet auf {e['account']}. Ist es bis dahin nicht da, erinnert Kassensturz.")
    for a in db.query("SELECT id, name, kind, matures_on FROM accounts WHERE archived = 0 AND matures_on IS NOT NULL "
                      "AND kind IN ('festgeld', 'kredit')"):
        what = "Festgeld fällig" if a["kind"] == "festgeld" else "Kredit endet"
        add(f"matures-{a['id']}", _day(a["matures_on"]), f"{what}: {a['name']}")
    for g in db.query("SELECT id, name, due_date, target_cents FROM goals WHERE due_date IS NOT NULL"):
        add(f"goal-{g['id']}", _day(g["due_date"]), f"Sparziel: {g['name']}", f"Ziel {euro(g['target_cents'])}.")
    for s in db.query("SELECT id, aspsp_name, valid_until FROM eb_sessions WHERE status = 'active' AND valid_until IS NOT NULL"):
        add(f"eb-{s['id']}", _day(s["valid_until"]), f"Bankfreigabe läuft ab: {s['aspsp_name']}",
            "Danach kommen keine neuen Umsätze mehr. Erneuern in Kassensturz unter Konten.")
    out.sort(key=lambda e: (e["date"], e["summary"]))
    return out


def _escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> list[str]:
    """Zeilen über 75 Byte werden umbrochen; Fortsetzungen beginnen mit einem Leerzeichen (RFC 5545)."""
    out, chunk, size = [], "", 0
    for ch in line:
        width = len(ch.encode("utf-8"))
        if size + width > (75 if not out else 74):
            out.append(chunk)
            chunk, size = "", 0
        chunk += ch
        size += width
    out.append(chunk)
    return [out[0]] + [" " + part for part in out[1:]]


def ics(items: list[dict], now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Kassensturz//Zahlungskalender//DE", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "X-WR-CALNAME:Kassensturz", "X-WR-TIMEZONE:Europe/Berlin"]
    for e in items:
        lines += ["BEGIN:VEVENT", f"UID:{e['uid']}", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{e['date'].strftime('%Y%m%d')}",
                  f"DTEND;VALUE=DATE:{(e['date'] + timedelta(days=1)).strftime('%Y%m%d')}",
                  f"SUMMARY:{_escape(e['summary'])}", "TRANSP:TRANSPARENT"]
        if e.get("description"):
            lines.append(f"DESCRIPTION:{_escape(e['description'])}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(part for line in lines for part in _fold(line)) + "\r\n"
