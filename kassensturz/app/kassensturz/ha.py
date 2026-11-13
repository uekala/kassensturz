"""Anbindung an Home Assistant über die Supervisor-API: Sensoren und Benachrichtigungen."""
from __future__ import annotations

import logging
import os
import re
import time

import requests

from .db import Database, now_iso

log = logging.getLogger("kassensturz.ha")
API = os.environ.get("KASSENSTURZ_HA_API", "http://supervisor/core/api")


def _token() -> str | None:
    return os.environ.get("SUPERVISOR_TOKEN")


def available() -> bool:
    return bool(_token())


_down_until = 0.0


def _post(path: str, payload: dict) -> bool:
    global _down_until
    token = _token()
    if not token or time.time() < _down_until:
        return False
    try:
        r = requests.post(f"{API}{path}", json=payload, timeout=8, headers={"Authorization": f"Bearer {token}"})
        if r.status_code >= 400:
            log.warning("Home Assistant antwortet %s auf %s: %s", r.status_code, path, r.text[:200])
            return False
        return True
    except requests.RequestException as exc:
        _down_until = time.time() + 120  # nicht bei jedem Sensor erneut in den Timeout laufen
        log.warning("Home Assistant nicht erreichbar: %s", exc)
        return False


def slug(text: str) -> str:
    t = (text or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:40] or "x"


def _euro(cents: int | None):
    return None if cents is None else round(cents / 100, 2)


def _sensor(entity: str, cents: int | None, name: str, icon: str, attrs: dict | None = None, stats: bool = False) -> bool:
    attributes = {"unit_of_measurement": "€", "device_class": "monetary", "friendly_name": name, "icon": icon}
    if stats:  # Bestände bekommen eine Langzeitstatistik, Prognosen und Restbeträge nicht
        attributes["state_class"] = "total"
    attributes.update(attrs or {})
    state = "unknown" if cents is None else _euro(cents)
    return _post(f"/states/sensor.kassensturz_{entity}", {"state": state, "attributes": attributes})


def push_sensors(summary: dict) -> int:
    """summary stammt aus services.build_summary()."""
    if not available():
        return 0
    fc = summary["forecast"]
    n = 0
    n += _sensor("kontostand", fc["balance_now"], "Kassensturz Kontostand", "mdi:bank",
                 {"konten": {a["name"]: _euro(a["balance"]) for a in fc["accounts"]}}, stats=True)
    n += _sensor("frei_verfuegbar", fc["free_cents"], "Kassensturz frei verfügbar", "mdi:wallet-outline",
                 {"bis": fc["period_end"], "zeitraum": fc["period_label"], "pro_tag": _euro(fc["free_per_day_cents"])})
    n += _sensor("prognose_monatsende", fc["month_end_cents"], "Kassensturz Prognose Monatsende", "mdi:chart-timeline-variant")
    n += _sensor("tiefster_stand", fc["low_point"]["cents"], "Kassensturz tiefster Stand (Prognose)", "mdi:arrow-collapse-down",
                 {"datum": fc["low_point"]["date"]})
    n += _sensor("fixkosten_monat", summary["fixed_monthly_cents"], "Kassensturz Fixkosten pro Monat", "mdi:file-document-multiple-outline",
                 {"vertraege": summary["contract_count"]})
    n += _sensor("ausgaben_monat", summary["month"]["expense_cents"], "Kassensturz Ausgaben diesen Monat", "mdi:cart-outline",
                 {"einnahmen": _euro(summary["month"]["income_cents"])})
    nxt = summary.get("next_payment")
    n += _sensor("naechste_zahlung", nxt["amount_cents"] if nxt else None, "Kassensturz nächste Zahlung", "mdi:calendar-clock",
                 {"empfaenger": nxt["name"], "datum": nxt["date"]} if nxt else {})
    for a in summary["accounts"]:
        n += _sensor(f"konto_{slug(a['name'])}", a["balance_now"], f"Kassensturz {a['name']}", "mdi:credit-card-outline",
                     {"iban": a.get("iban") or "", "stand": a.get("last_date") or ""}, stats=True)
    for b in summary["budgets"]:
        n += _sensor(f"budget_{slug(b['name'])}", b["left_cents"], f"Kassensturz Budget {b['name']}", "mdi:target",
                     {"budget": _euro(b["budget_cents"]), "ausgegeben": _euro(b["spent_cents"]), "prozent": round(b["ratio"] * 100)})
    worth = summary.get("worth")
    if worth:
        g = worth["groups"]
        n += _sensor("vermoegen", worth["total_cents"], "Kassensturz Vermögen", "mdi:scale-balance",
                     {"alltag": _euro(g["alltag"]), "ruecklagen": _euro(g["ruecklagen"]), "depots": _euro(g["depots"]),
                      "immobilien": _euro(g["immobilien"]), "kredite": _euro(g["kredite"])}, stats=True)
        n += _sensor("ersparnisse", g["ruecklagen"] + g["depots"], "Kassensturz Ersparnisse", "mdi:piggy-bank-outline",
                     {"ruecklagen": _euro(g["ruecklagen"]), "depots": _euro(g["depots"])}, stats=True)
        n += _sensor("schulden", -g["kredite"], "Kassensturz Schulden", "mdi:hand-coin-outline",
                     {"kredite": worth["loan_count"]}, stats=True)
    n += _sensor("ruecklage_jahreskosten", fc.get("reserve_cents"), "Kassensturz Rücklage für Jahreskosten", "mdi:calendar-sync-outline",
                 {"pro_monat": _euro(fc.get("reserve_monthly_cents")), "abgezogen": bool(fc.get("reserve_deducted"))})
    for goal in summary.get("goals") or []:
        n += _sensor(f"sparziel_{slug(goal['name'])}", goal["saved_cents"], f"Kassensturz Sparziel {goal['name']}", "mdi:flag-checkered",
                     {"ziel": _euro(goal["target_cents"]), "rest": _euro(goal["rest_cents"]), "prozent": round(goal["progress"] * 100),
                      "bis": goal["due_date"] or "", "pro_monat": _euro(goal["monthly_cents"]), "status": goal["status"]})
    return n


def fire(event: str, data: dict) -> bool:
    """Ereignis auf dem Bus von Home Assistant, als Auslöser für Automationen."""
    if not available():
        return False
    return _post(f"/events/kassensturz_{event}", data)


def fire_once(db: Database, key: str, event: str, data: dict) -> bool:
    """Wie fire(), aber je Schlüssel nur ein einziges Mal."""
    if db.one("SELECT key FROM notices WHERE key = ?", (key,)):
        return False
    db.execute("INSERT OR IGNORE INTO notices(key, created) VALUES(?, ?)", (key, now_iso()))
    return fire(event, data)


def notify(db: Database, key: str, title: str, message: str, service: str | None) -> bool:
    if db.one("SELECT key FROM notices WHERE key = ?", (key,)):
        return False
    db.execute("INSERT OR IGNORE INTO notices(key, created) VALUES(?, ?)", (key, now_iso()))
    if not available():
        return False
    service = (service or "").strip()
    if service.startswith("notify.") and len(service) > 7:
        return _post(f"/services/notify/{service[7:]}", {"title": title, "message": message})
    return _post("/services/persistent_notification/create",
                 {"title": title, "message": message, "notification_id": f"kassensturz_{slug(key)}"})
