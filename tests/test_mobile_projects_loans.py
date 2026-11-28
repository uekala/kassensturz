"""App: Projekte und Tilgungsplan – nur erfundene Daten."""
from datetime import date

from test_household import pair
from test_mobile_write import https_client, reset_mobile_guards

from kassensturz import household, ledger, projects


def book(db, acc, day, cents, who):
    ledger.import_rows(db, acc, [{"booking_date": day, "amount_cents": cents, "counterparty": who,
                                  "purpose": f"Beleg {who}"}], "openbanking")
    return db.scalar("SELECT MAX(id) FROM transactions")


def setup(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    anna = household.create_person(db, {"name": "Anna"})["id"]
    ben = household.create_person(db, {"name": "Ben"})["id"]
    shared = db.insert("accounts", {"name": "KS-Gemeinsam", "kind": "giro"})
    bens = db.insert("accounts", {"name": "KS-Bens Konto", "kind": "giro", "owner_person_id": ben})
    trip = projects.create(db, {"name": "KS-Urlaub", "budget_cents": 100000})["id"]
    flight = book(db, shared, "2026-10-01", -40000, "KS-Flug")
    hotel = book(db, bens, "2026-10-05", -30000, "KS-Hotel")
    projects.assign(db, trip, [flight, hotel])
    return {"anna": anna, "ben": ben, "shared": shared, "bens": bens, "trip": trip, "flight": flight, "hotel": hotel}


def test_projects_show_only_what_the_person_sees(db, monkeypatch):
    s = setup(db, monkeypatch)
    with https_client() as client:
        anna = pair(client, s["anna"], "Annas Handy")
        ben = pair(client, s["ben"], "Bens Handy")
        mine = client.get("/api/v1/projects", headers=anna).json()["items"]
        assert [(p["name"], p["cost_cents"], p["count"], p["left_cents"]) for p in mine] == [("KS-Urlaub", 40000, 1, 60000)]
        assert client.get("/api/v1/projects", headers=ben).json()["items"][0]["cost_cents"] == 70000
        detail = client.get(f"/api/v1/projects/{s['trip']}", headers=anna).json()
        assert [t["counterparty"] for t in detail["transactions"]] == ["KS-Flug"]
        assert detail["months"] == [{"month": "2026-10", "cents": 40000}]
        assert client.get("/api/v1/projects/4711", headers=anna).status_code == 404
        assert client.get("/api/v1/projects/abc", headers=anna).status_code == 404


def test_transaction_can_be_put_into_a_project_from_the_phone(db, monkeypatch):
    s = setup(db, monkeypatch)
    other = projects.create(db, {"name": "KS-Auto"})["id"]
    old = projects.create(db, {"name": "KS-Alt"})["id"]
    projects.change(db, old, {"archived": True})
    with https_client() as client:
        anna = pair(client, s["anna"], "Annas Handy")
        seen = client.get(f"/api/v1/transactions/{s['flight']}/project", headers=anna).json()
        assert seen["project_id"] == s["trip"] and [p["name"] for p in seen["projects"]] == ["KS-Urlaub", "KS-Auto"]
        assert client.put(f"/api/v1/transactions/{s['flight']}/project", headers=anna, json={"project_id": other}).status_code == 200
        assert db.scalar("SELECT project_id FROM project_tx WHERE tx_id = ?", (s["flight"],)) == other
        assert client.put(f"/api/v1/transactions/{s['flight']}/project", headers=anna, json={"project_id": None}).status_code == 200
        assert db.scalar("SELECT project_id FROM project_tx WHERE tx_id = ?", (s["flight"],)) is None
        # Bens Buchung sieht Anna nicht; falsche Felder und unbekannte Projekte werden abgelehnt.
        assert client.put(f"/api/v1/transactions/{s['hotel']}/project", headers=anna, json={"project_id": other}).status_code == 404
        assert client.get(f"/api/v1/transactions/{s['hotel']}/project", headers=anna).status_code == 404
        assert client.put(f"/api/v1/transactions/{s['flight']}/project", headers=anna, json={"project_id": 4711}).status_code == 404
        assert client.put(f"/api/v1/transactions/{s['flight']}/project", headers=anna, json={"x": 1}).status_code == 400
        texts = [r["text"] for r in db.query("SELECT text FROM audit_log WHERE actor = 'Anna' ORDER BY id")]
        assert texts == ["KS-Flug, −400,00 € am 01.10.2026: Projekt „KS-Auto“", "KS-Flug, −400,00 € am 01.10.2026: aus dem Projekt genommen"]


def test_loan_plan_for_a_visible_loan(db, monkeypatch):
    s = setup(db, monkeypatch)
    loan = db.insert("accounts", {"name": "KS-Autokredit", "kind": "kredit", "loan_rate_milli": 3600, "loan_payment_cents": 100000})
    ledger.record_valuation(db, loan, -10_000_000, date.today().isoformat())
    hidden = db.insert("accounts", {"name": "KS-Bens Kredit", "kind": "kredit", "owner_person_id": s["ben"]})
    with https_client() as client:
        anna = pair(client, s["anna"], "Annas Handy")
        plan = client.get(f"/api/v1/accounts/{loan}/loan", headers=anna).json()
        assert plan["ready"] and plan["today_cents"] == 10_000_000 and plan["months"] > 100 and "account_id" not in plan
        extra = client.get(f"/api/v1/accounts/{loan}/loan?extra_cents=500000", headers=anna).json()["extra"]
        assert extra["months_saved"] > 0 and extra["interest_saved_cents"] > 0
        assert client.get(f"/api/v1/accounts/{hidden}/loan", headers=anna).status_code == 404
        assert client.get(f"/api/v1/accounts/{s['shared']}/loan", headers=anna).status_code == 409
        assert client.get(f"/api/v1/accounts/{loan}/loan?extra_cents=-5", headers=anna).status_code == 400


def test_booked_rates_on_the_phone_come_only_from_visible_accounts(db, monkeypatch):
    s = setup(db, monkeypatch)
    loan = db.insert("accounts", {"name": "KS-Autokredit", "kind": "kredit", "loan_rate_milli": 3600, "loan_payment_cents": 100000})
    entered = date.today().replace(day=1)
    ledger.record_valuation(db, loan, -10_000_000, (entered.replace(year=entered.year - 1)).isoformat())
    day = entered.isoformat()
    book(db, s["bens"], day, -100000, "KS-Kreditbank")
    with https_client() as client:
        anna = pair(client, s["anna"], "Annas Handy")
        ben = pair(client, s["ben"], "Bens Handy")
        assert client.get(f"/api/v1/accounts/{loan}/loan", headers=anna).json()["booked"]["count"] == 0
        assert client.get(f"/api/v1/accounts/{loan}/loan", headers=ben).json()["booked"]["count"] == 1
