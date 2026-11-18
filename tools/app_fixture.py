#!/usr/bin/env python3
"""Antworten des Servers für die Bildschirmfotos der App.

Startet Kassensturz in einem leeren Ordner, lädt die Beispieldaten, richtet einen kleinen
Haushalt ein, koppelt zwei Geräte und speichert, was die App beim Lesen vom Server bekommt.
Die Flutter-Tests unter ``mobile/app/tool/bilder`` spielen diese Antworten ab und rendern
damit jede Seite der App.

So sieht die App in den Bildern echte Antworten des Servers und keine von Hand gebauten.
Ändert der Server ein Feld, das die App braucht, fällt das hier auf.

Aufruf: python3 tools/app_fixture.py mobile/app/tool/bilder/server.json
Es sind nur erfundene Daten im Spiel; die Datei wird nicht eingecheckt.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Lesewege der App. Die App hängt je nach Seite Parameter an; abgespielt wird nach dem Pfad.
READS = {
    "/api/v1/me": {},
    "/api/v1/overview": {},
    "/api/v1/accounts": {},
    "/api/v1/categories": {},
    "/api/v1/transactions": {"limit": 50},
    "/api/v1/stats": {},
    "/api/v1/contracts": {},
    "/api/v1/networth": {},
    "/api/v1/news": {},
    "/api/v1/papers": {},
    "/api/v1/triage": {},
    "/api/v1/budgets/suggestions": {},
    "/api/v1/sync": {},
    "/api/v1/household/sharing": {},
    "/api/v1/afford": {"amount_cents": 30000},
}


def _ok(response, what: str):
    if response.status_code >= 300:
        raise SystemExit(f"{what}: {response.status_code} {response.text[:300]}")
    return response.json()


def _household(admin) -> dict:
    """Zwei Erwachsene, ein Kind: eigenes Konto, geteilte Ausgabe, Ausgleich, Taschengeld, Ziele, Budgets."""
    anna = _ok(admin.post("/api/persons", json={"name": "Anna"}), "Person")["id"]
    ben = _ok(admin.post("/api/persons", json={"name": "Ben"}), "Person")["id"]
    mia = _ok(admin.post("/api/persons", json={"name": "Mia", "is_child": True}), "Kind")["id"]
    accounts = {a["name"]: a for a in _ok(admin.get("/api/accounts"), "Konten")}
    today = date.today().isoformat()
    # Anna zahlt mit ihrer Karte, das Girokonto ist gemeinsam, Ben hat ein eigenes Tagesgeld.
    _ok(admin.patch(f"/api/accounts/{accounts['American Express']['id']}", json={"owner_person_id": anna}), "Konto")
    saving = _ok(admin.post("/api/accounts", json={"name": "Tagesgeld Ben", "kind": "tagesgeld", "owner_person_id": ben}), "Konto")
    _ok(admin.post(f"/api/accounts/{saving['id']}/balance", json={"balance_cents": 420000, "date": today}), "Stand")
    for account in ("Girokonto", "PayPal", "American Express"):
        acc = accounts[account]
        _ok(admin.post(f"/api/accounts/{acc['id']}/balance", json={"balance_cents": acc["balance_now"], "date": today}), "Stand")
    depot = _ok(admin.post("/api/accounts", json={"name": "Depot", "kind": "depot"}), "Depot")
    before = (date.today() - timedelta(days=40)).isoformat()
    _ok(admin.post(f"/api/accounts/{depot['id']}/balance", json={"balance_cents": 1840000, "date": before}), "Wert")
    _ok(admin.post(f"/api/accounts/{depot['id']}/balance", json={"balance_cents": 1912000, "date": today}), "Wert")
    loan = _ok(admin.post("/api/accounts", json={"name": "Autokredit", "kind": "kredit",
                                                 "matures_on": (date.today() + timedelta(days=900)).isoformat()}), "Kredit")
    _ok(admin.post(f"/api/accounts/{loan['id']}/balance", json={"balance_cents": 1150000, "date": today}), "Wert")
    _ok(admin.post("/api/accounts", json={"name": "Taschengeld Mia", "kind": "taschengeld", "owner_person_id": mia,
                                          "allowance_cents": 800, "allowance_interval": "week"}), "Taschengeld")
    # Eine Ausgabe von Annas Karte teilen; Ben gleicht einen Teil aus.
    card = _ok(admin.get("/api/transactions", params={"account": accounts["American Express"]["id"], "limit": 50}), "Umsätze")
    spent = [t for t in card["items"] if t["amount_cents"] < -2000 and not t["is_transfer"]]
    if spent:
        _ok(admin.put(f"/api/transactions/{spent[0]['id']}/share", json={}), "Teilen")
        _ok(admin.post("/api/household/settlements", json={"from_person_id": ben, "to_person_id": anna, "cents": 1000,
                                                             "note": "Bar gegeben"}), "Ausgleich")
    # Budgets für den Haushalt, eines nur für Anna, ein gemeinsames und ein eigenes Sparziel.
    cats = {c["builtin_key"]: c["id"] for c in _ok(admin.get("/api/categories"), "Kategorien") if c["builtin_key"]}
    for key, cents in (("supermarkt", 45000), ("restaurant", 12000), ("laden", 15000)):
        _ok(admin.patch(f"/api/categories/{cats[key]}", json={"budget_cents": cents}), "Budget")
    _ok(admin.put(f"/api/persons/{anna}/budgets/{cats['kleidung']}", json={"budget_cents": 8000}), "eigenes Budget")
    due = (date.today() + timedelta(days=210)).isoformat()
    _ok(admin.post("/api/goals", json={"name": "Sommerurlaub", "target_cents": 250000, "saved_cents": 120000, "due_date": due}), "Ziel")
    _ok(admin.post("/api/goals", json={"name": "Neues Rad", "target_cents": 90000, "saved_cents": 30000,
                                       "owner_person_id": anna}), "Ziel")
    # Papierkram: eine Buchung mit Steuerart, eine mit Garantie.
    giro = _ok(admin.get("/api/transactions", params={"account": accounts["Girokonto"]["id"], "limit": 80}), "Umsätze")
    out = [t for t in giro["items"] if t["amount_cents"] < -1500 and not t["is_transfer"]]
    if len(out) >= 2:
        _ok(admin.patch(f"/api/transactions/{out[0]['id']}", json={"tax_kind": "handwerker"}), "Steuerart")
        until = (date.today() + timedelta(days=400)).isoformat()
        _ok(admin.patch(f"/api/transactions/{out[1]['id']}", json={"warranty_until": until}), "Garantie")
    return {"anna": anna, "ben": ben, "mia": mia}


def _pair(client, admin, person_id: int, name: str) -> dict:
    secret = _ok(admin.post("/api/mobile/pairings", json={"person_id": person_id}), "Kopplung")["pairing_secret"]
    paired = _ok(client.post("/api/v1/pair", json={"pairing_secret": secret, "device_name": name}), "Kopplung einlösen")
    return {"Authorization": f"Bearer {paired['access_token']}"}


def _reads(client, headers: dict) -> dict:
    out = {}
    for path, params in READS.items():
        response = client.get(path, params=params, headers=headers)
        out[f"GET {path}"] = {"status": response.status_code, "body": response.json()}
    # Was die App für eine einzelne Buchung nachlädt.
    listed = out["GET /api/v1/transactions"]["body"].get("items") or []
    for tx in listed[:3]:
        for tail in ("receipts", "share"):
            path = f"/api/v1/transactions/{tx['id']}/{tail}"
            response = client.get(path, headers=headers)
            out[f"GET {path}"] = {"status": response.status_code, "body": response.json()}
    return out


def build() -> dict:
    data = tempfile.mkdtemp(prefix="kassensturz-bilder-")
    os.environ.update({"KASSENSTURZ_DATA": data, "KASSENSTURZ_DEV": "1", "KASSENSTURZ_NO_BACKGROUND": "1",
                       "KASSENSTURZ_INBOX": ""})
    sys.path.insert(0, str(ROOT / "kassensturz" / "app"))
    from fastapi.testclient import TestClient

    from kassensturz import main, services

    with TestClient(main.app, base_url="https://testserver", client=("127.0.0.1", 50123)) as client:
        admin = client
        _ok(admin.post("/api/demo"), "Beispieldaten")
        persons = _household(admin)
        services.refresh(notify=False)
        views = {}
        for key, device in (("anna", "Annas Handy"), ("mia", "Mias Handy")):
            views[key] = _reads(client, _pair(client, admin, persons[key], device))
    failed = [f"{view}: {name} → {answer['status']}" for view, answers in views.items()
              for name, answer in answers.items() if answer["status"] >= 500]
    if failed:
        raise SystemExit("Der Server antwortet mit einem Fehler:\n" + "\n".join(failed))
    return {"today": date.today().isoformat(), "views": views}


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "server.json")
    fixture = build()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(fixture, ensure_ascii=False, indent=1), "utf-8")
    for view, answers in fixture["views"].items():
        bad = sorted(f"{name} ({answer['status']})" for name, answer in answers.items() if answer["status"] != 200)
        print(f"{view}: {len(answers)} Antworten" + (f", nicht 200: {', '.join(bad)}" if bad else ""))
