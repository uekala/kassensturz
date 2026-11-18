"""Änderungsprotokoll – nur erfundene Daten."""
from datetime import date, timedelta

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from kassensturz import audit, household, ledger, main
from test_household import pair
from test_mobile_write import https_client, reset_mobile_guards


def log(db):
    return [(r["actor"], r["actor_kind"], r["text"]) for r in db.query("SELECT * FROM audit_log ORDER BY id")]


def tx(db, acc, cents=-2340, who="KS-Markt", day="2026-11-12"):
    ledger.import_rows(db, acc, [{"booking_date": day, "amount_cents": cents, "counterparty": who, "purpose": "Einkauf"}], "openbanking")
    return db.scalar("SELECT MAX(id) FROM transactions")


def test_every_write_route_is_labelled_or_deliberately_skipped():
    missing = []
    for route in main.app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/"):
            continue
        for method in route.methods & audit.WRITE_METHODS:
            if (method, route.path) not in audit.LABELS and (method, route.path) not in audit.SKIP:
                missing.append(f"{method} {route.path}")
    assert missing == []
    assert not set(audit.LABELS) & audit.SKIP


def test_change_in_home_assistant_names_the_user_and_what_changed(db):
    acc = db.insert("accounts", {"name": "KS-Girokonto", "kind": "giro"})
    booking = tx(db, acc)
    food = db.scalar("SELECT id FROM categories WHERE builtin_key = 'lebensmittel'")
    with TestClient(main.app, client=(audit.INGRESS_IP, 50123)) as client:
        headers = {"X-Remote-User-Name": "uemit", "X-Remote-User-Display-Name": "Ümit".encode()}
        assert client.patch(f"/api/transactions/{booking}", json={"category_id": food, "note": "Wocheneinkauf",
                                                                  "learn": False}, headers=headers).status_code == 200
        # Speichern ohne Änderung schreibt nichts.
        assert client.patch(f"/api/transactions/{booking}", json={"note": "Wocheneinkauf", "tax_kind": None},
                            headers=headers).status_code == 200
        only_name = {"X-Remote-User-Name": "gast"}
        assert client.patch(f"/api/categories/{food}", json={"budget_cents": 40000}, headers=only_name).status_code == 200
        assert client.get("/api/transactions").status_code == 200        # Lesen kommt nie ins Protokoll
        name = db.scalar("SELECT name FROM categories WHERE id = ?", (food,))
        assert log(db) == [
            ("Ümit", "ha", f"KS-Markt, −23,40 € am 12.11.2026: Kategorie „{name}“, Notiz geändert"),
            ("gast", "ha", f"Budget „{name}“ festgelegt: 400,00 €"),
        ]
        assert db.scalar("SELECT account_id FROM audit_log WHERE id = 1") == acc


def test_names_are_only_trusted_from_ingress(client, db):
    acc = db.insert("accounts", {"name": "KS-Kasse", "kind": "cash"})
    assert client.patch(f"/api/accounts/{acc}", json={"name": "KS-Haushaltskasse"},
                        headers={"X-Remote-User-Display-Name": "Falscher Name"}).status_code == 200
    assert log(db) == [("Lokal", "local", "Konto geändert: KS-Kasse heißt jetzt KS-Haushaltskasse")]


def test_failed_and_read_only_requests_leave_no_entry(client, db):
    assert client.patch("/api/transactions/4711", json={"note": "x"}).status_code == 404
    assert client.post("/api/projects", json={"name": ""}).status_code == 400
    assert client.post("/api/import/analyze", files={"file": ("x.csv", b"kaputt")}).status_code in (200, 400)
    assert client.post("/api/jobs/unbekannt/answer", json={"value": "123456"}).status_code in (200, 404)
    assert log(db) == []


def test_form_contents_never_reach_the_log(client, db):
    cid = db.insert("connections", {"name": "KS-Bank", "blz": "12345678", "login": "alt", "server": "https://bank.invalid"})
    assert client.patch(f"/api/connections/{cid}", json={"login": "geheimer-anmeldename-4711"}).status_code == 200
    assert client.put("/api/settings", json={"buffer_cents": 12345}).status_code == 200
    rows = db.query("SELECT text, route FROM audit_log ORDER BY id")
    assert [r["text"] for r in rows] == ["Bankzugang geändert", "Einstellungen geändert"]
    assert "4711" not in repr(rows) and "12345" not in repr(rows)


def test_details_for_accounts_projects_persons_and_settlements(client, db):
    made = client.post("/api/accounts", json={"name": "KS-Kredit", "kind": "kredit"}).json()
    assert client.post(f"/api/accounts/{made['id']}/balance", json={"balance_cents": 1500000, "date": "2026-11-01"}).status_code == 200
    giro = db.insert("accounts", {"name": "KS-Altkonto", "kind": "giro"})
    tx(db, giro)
    tx(db, giro, -100, "KS-Kiosk")
    assert client.delete(f"/api/accounts/{giro}").status_code == 200
    pid = client.post("/api/projects", json={"name": "KS-Urlaub"}).json()["id"]
    assert client.delete(f"/api/projects/{pid}").status_code == 200
    anna = client.post("/api/persons", json={"name": "KS-Anna"}).json()["id"]
    ben = client.post("/api/persons", json={"name": "KS-Ben"}).json()["id"]
    assert client.post("/api/household/settlements", json={"from_person_id": anna, "to_person_id": ben, "cents": 5000}).status_code == 200
    assert [r[2] for r in log(db)] == [
        "Konto angelegt: KS-Kredit",
        "Restschuld von „KS-Kredit“ eingetragen: 15.000,00 €",
        "Konto „KS-Altkonto“ gelöscht, mit 2 Buchungen",
        "Projekt angelegt: KS-Urlaub",
        "Projekt gelöscht: KS-Urlaub",
        "Person angelegt: KS-Anna",
        "Person angelegt: KS-Ben",
        "Ausgleichszahlung: KS-Anna an KS-Ben, 50,00 €",
    ]


def test_phone_changes_carry_the_person_of_the_device(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    anna = household.create_person(db, {"name": "Anna"})["id"]
    cash = db.insert("accounts", {"name": "KS-Kasse", "kind": "cash", "balance_cents": 0, "balance_date": "2020-01-01"})
    food = db.scalar("SELECT id FROM categories WHERE builtin_key = 'lebensmittel'")
    name = db.scalar("SELECT name FROM categories WHERE id = ?", (food,))
    with https_client() as client:
        headers = pair(client, anna, "Annas Handy")
        loose = pair(client, None, "Altes Handy")
        made = client.post("/api/v1/transactions", headers=headers, json={
            "account_id": cash, "amount_cents": -450, "booking_date": "2026-11-15", "counterparty": "KS-Bäcker",
            "category_id": food, "client_request_id": "ks-anfrage-0001-erfunden"})
        assert made.status_code == 201, made.text
        tx_id = made.json()["transaction"]["id"]
        again = client.post("/api/v1/transactions", headers=headers, json={
            "account_id": cash, "amount_cents": -450, "booking_date": "2026-11-15", "counterparty": "KS-Bäcker",
            "category_id": food, "client_request_id": "ks-anfrage-0001-erfunden"})
        assert again.status_code == 200
        assert client.patch(f"/api/v1/transactions/{tx_id}", headers=headers, json={"note": "Brötchen"}).status_code == 200
        assert client.put(f"/api/v1/budgets/{food}", headers=loose, json={"limit_cents": 30000}).status_code == 200
        assert client.delete(f"/api/v1/transactions/{tx_id}", headers=headers).status_code == 200
        assert client.post("/api/v1/auth/logout", headers=loose).status_code in (200, 204)
        rows = log(db)
        assert rows[0] == ("Lokal", "local", "Kopplungscode für ein Handy erstellt")
        assert [r for r in rows if r[1] == "phone"] == [
            ("Anna", "phone", "Buchung angelegt: KS-Bäcker, −4,50 € am 15.11.2026"),
            ("Anna", "phone", "KS-Bäcker, −4,50 € am 15.11.2026: Notiz geändert"),
            ("Altes Handy", "phone", f"Budget „{name}“: 300,00 €"),
            ("Anna", "phone", "Buchung gelöscht: KS-Bäcker, −4,50 € am 15.11.2026"),
        ]


def test_listing_filters_by_actor_and_pages(client, db):
    for i in range(5):
        client.post("/api/projects", json={"name": f"KS-Projekt {i}"})
    db.execute("UPDATE audit_log SET actor = 'Ben' WHERE id IN (2, 4)")
    seen = client.get("/api/changes?limit=2").json()
    assert seen["total"] == 5 and [i["text"] for i in seen["items"]] == ["Projekt angelegt: KS-Projekt 4",
                                                                      "Projekt angelegt: KS-Projekt 3"]
    assert seen["actors"] == ["Lokal", "Ben"]
    ben = client.get("/api/changes?actor=Ben").json()
    assert ben["total"] == 2 and {i["actor"] for i in ben["items"]} == {"Ben"}
    assert client.get("/api/changes?offset=4").json()["items"][0]["text"] == "Projekt angelegt: KS-Projekt 0"


def test_old_entries_and_overflow_are_pruned(db, monkeypatch):
    old = (date.today() - timedelta(days=audit.KEEP_DAYS + 1)).isoformat() + "T12:00:00"
    db.insert("audit_log", {"at": old, "actor": "Lokal", "actor_kind": "local", "text": "alt"})
    for i in range(6):
        db.insert("audit_log", {"at": f"{date.today().isoformat()}T10:00:0{i}", "actor": "Lokal", "actor_kind": "local",
                                "text": f"neu {i}"})
    monkeypatch.setattr(audit, "KEEP_ROWS", 4)
    audit.prune(db)
    assert [r["text"] for r in db.query("SELECT text FROM audit_log ORDER BY id")] == ["neu 2", "neu 3", "neu 4", "neu 5"]


def test_outside_a_request_nothing_happens(db):
    audit.note("ohne Anfrage")
    audit.subject("ohne Anfrage")
    audit.skip()
    assert log(db) == []
