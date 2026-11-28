"""App: Hinweise erledigen, geplante Ausgaben und erwartete Eingänge – nur erfundene Daten."""
from datetime import date, timedelta

from test_household import pair
from test_mobile_write import https_client, reset_mobile_guards

from kassensturz import expected, household, ledger, planned

TODAY = date.today()


def d(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


def book(db, acc, days, cents, who):
    ledger.import_rows(db, acc, [{"booking_date": d(days), "amount_cents": cents, "counterparty": who,
                                  "purpose": f"Beleg {who}"}], "openbanking")
    return db.scalar("SELECT MAX(id) FROM transactions")


def home(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    anna = household.create_person(db, {"name": "Anna"})["id"]
    ben = household.create_person(db, {"name": "Ben"})["id"]
    mia = household.create_person(db, {"name": "Mia", "is_child": True})["id"]
    shared = db.insert("accounts", {"name": "KS-Gemeinsam", "kind": "giro", "in_forecast": 1})
    bens = db.insert("accounts", {"name": "KS-Bens Konto", "kind": "giro", "in_forecast": 1, "owner_person_id": ben})
    return {"anna": anna, "ben": ben, "mia": mia, "shared": shared, "bens": bens}


def test_overview_lists_open_plans_and_alert_actions(db, monkeypatch):
    h = home(db, monkeypatch)
    planned.create(db, {"label": "KS-Handwerker", "cents": 85000, "due_date": d(5), "account_id": h["shared"]})
    planned.create(db, {"label": "KS-Bens Rad", "cents": 40000, "due_date": d(6), "account_id": h["bens"]})
    late = planned.create(db, {"label": "KS-Kaution", "cents": 60000, "due_date": d(-3), "account_id": h["shared"]},
                          today=TODAY - timedelta(days=10))
    expected.create(db, {"label": "KS-Auslagen", "cents": 1850, "account_id": h["shared"], "due_date": d(-1)},
                    today=TODAY - timedelta(days=30))
    with https_client() as client:
        anna = pair(client, h["anna"], "Annas Handy")
        seen = client.get("/api/v1/overview", headers=anna).json()
        plans = seen["plans"]
        assert [p["label"] for p in plans["planned"]] == ["KS-Kaution", "KS-Handwerker"]
        assert plans["planned_cents"] == 145000 and plans["expected"][0]["label"] == "KS-Auslagen"
        assert plans["expected"][0]["overdue"] is True and plans["planned"][0]["overdue"] is True
        by_key = {a["key"]: a for a in seen["alerts"] if "key" in a}
        assert by_key[f"planned-due:{late['id']}:{d(-3)}"]["actions"] == ["paid", "drop"]
        assert any(a.get("actions") == ["received", "drop"] for a in seen["alerts"])
        assert all("key" not in a for a in seen["alerts"] if not a.get("actions"))
        assert "plans" in client.get("/api/v1/me", headers=anna).json()["capabilities"]


def test_plans_can_be_created_and_ticked_off_only_where_visible(db, monkeypatch):
    h = home(db, monkeypatch)
    bens = planned.create(db, {"label": "KS-Bens Rad", "cents": 40000, "due_date": d(6), "account_id": h["bens"]})
    with https_client() as client:
        anna = pair(client, h["anna"], "Annas Handy")
        ben = pair(client, h["ben"], "Bens Handy")
        mia = pair(client, h["mia"], "Mias Handy")
        made = client.post("/api/v1/planned", headers=anna, json={"label": "KS-Waschmaschine", "cents": 64900,
                                                                   "due_date": d(9), "account_id": h["shared"]})
        assert made.status_code == 201, made.text
        assert [p["label"] for p in made.json()["planned"]] == ["KS-Waschmaschine"]
        # Fremdes Konto, unbekannte Felder, falsche Werte, Kind: abgelehnt.
        assert client.post("/api/v1/planned", headers=anna, json={"label": "x", "cents": 1, "due_date": d(1),
                                                                  "account_id": h["bens"]}).status_code == 404
        assert client.post("/api/v1/planned", headers=anna, json={"label": "x", "cents": 1, "due_date": d(1),
                                                                  "account_id": h["shared"], "status": "paid"}).status_code == 400
        assert client.post("/api/v1/planned", headers=anna, json={"label": "x", "cents": -1, "due_date": d(1),
                                                                  "account_id": h["shared"]}).status_code == 400
        assert client.post("/api/v1/planned", headers=mia, json={"label": "x", "cents": 1, "due_date": d(1),
                                                                 "account_id": h["shared"]}).status_code == 403
        # Abhaken: Annas Handy kennt Bens Plan nicht.
        assert client.post(f"/api/v1/planned/{bens['id']}/paid", headers=anna).status_code == 404
        assert client.post(f"/api/v1/planned/{bens['id']}/weg", headers=ben).status_code == 404
        assert client.post(f"/api/v1/planned/{bens['id']}/drop", headers=ben).status_code == 200
        assert client.post(f"/api/v1/planned/{bens['id']}/drop", headers=ben).status_code == 404     # nicht mehr offen
        mine = made.json()["planned"][0]["id"]
        assert client.post(f"/api/v1/planned/{mine}/paid", headers=anna).status_code == 200
        assert planned.overview(db)["open"] == []
        texts = [r["text"] for r in db.query("SELECT text FROM audit_log WHERE actor_kind = 'phone' ORDER BY id")]
        assert texts == ["Geplante Ausgabe angelegt: KS-Waschmaschine", "Geplante Ausgabe gestrichen: KS-Bens Rad",
                         "Geplante Ausgabe abgehakt: KS-Waschmaschine"]


def test_money_back_from_an_expense_and_ticked_off(db, monkeypatch):
    h = home(db, monkeypatch)
    buy = book(db, h["shared"], -4, -7990, "KS-Versand")
    bens_buy = book(db, h["bens"], -4, -2500, "KS-Bens Laden")
    with https_client() as client:
        anna = pair(client, h["anna"], "Annas Handy")
        made = client.post("/api/v1/expected", headers=anna, json={"tx_id": buy, "cents": 5000})
        assert made.status_code == 201, made.text
        item = made.json()["expected"][0]
        assert (item["label"], item["cents"], item["account"]) == ("KS-Versand", 5000, "KS-Gemeinsam")
        assert client.post("/api/v1/expected", headers=anna, json={"tx_id": buy}).status_code == 409   # schon offen
        assert client.post("/api/v1/expected", headers=anna, json={"tx_id": bens_buy}).status_code == 404
        assert client.post("/api/v1/expected", headers=anna, json={"tx_id": buy, "label": "x"}).status_code == 400
        assert client.post(f"/api/v1/expected/{item['id']}/received", headers=anna).status_code == 200
        assert expected.overview(db)["open"] == [] and expected.overview(db)["closed"][0]["status"] == "received"


def test_anomaly_alert_can_be_acknowledged_from_the_phone(db, monkeypatch):
    h = home(db, monkeypatch)
    for back in range(70, 10, -10):
        book(db, h["shared"], -back, -1500, f"KS-Kiosk {back}")
    ledger.import_rows(db, h["shared"], [
        {"booking_date": d(-2), "amount_cents": -4999, "counterparty": "KS-Doppelt", "purpose": "Rechnung 1"},
        {"booking_date": d(-1), "amount_cents": -4999, "counterparty": "KS-Doppelt", "purpose": "Rechnung 2"},
    ], "openbanking")
    with https_client() as client:
        anna = pair(client, h["anna"], "Annas Handy")
        alerts = client.get("/api/v1/overview", headers=anna).json()["alerts"]
        double = next(a for a in alerts if a.get("actions") == ["ack"])
        assert client.post("/api/v1/alerts/ack", headers=anna, json={"key": "anomaly:erfunden:1"}).status_code == 404
        assert client.post("/api/v1/alerts/ack", headers=anna, json={"key": double["key"], "x": 1}).status_code == 400
        assert client.post("/api/v1/alerts/ack", headers=anna, json={"key": double["key"]}).status_code == 200
        keys = {a.get("key") for a in client.get("/api/v1/overview", headers=anna).json()["alerts"]}
        assert double["key"] not in keys
