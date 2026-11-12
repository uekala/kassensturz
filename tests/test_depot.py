"""Depot als Konto mit eingetragenem Gesamtwert – nur erfundene Daten."""
from kassensturz import ledger, services


def test_depot_is_created_outside_the_forecast(client):
    acc = client.post("/api/accounts", json={"name": "Testdepot", "kind": "depot"}).json()
    assert acc["in_forecast"] == 0
    giro = client.post("/api/accounts", json={"name": "Testgiro", "kind": "giro"}).json()
    assert giro["in_forecast"] == 1
    explicit = client.post("/api/accounts", json={"name": "Depot im Alltag", "kind": "depot", "in_forecast": 1}).json()
    assert explicit["in_forecast"] == 1


def test_depot_values_are_kept_and_show_the_change(client, db):
    aid = client.post("/api/accounts", json={"name": "Testdepot", "kind": "depot"}).json()["id"]
    client.post(f"/api/accounts/{aid}/balance", json={"balance_cents": 1000000, "date": "2026-10-01"})
    client.post(f"/api/accounts/{aid}/balance", json={"balance_cents": 1012345, "date": "2026-11-01"})
    client.post(f"/api/accounts/{aid}/balance", json={"balance_cents": 1050000, "date": "2026-11-01"})

    assert ledger.valuations(db, aid) == [
        {"on_date": "2026-10-01", "value_cents": 1000000},
        {"on_date": "2026-11-01", "value_cents": 1050000},
    ]
    acc = next(a for a in client.get("/api/accounts").json() if a["id"] == aid)
    assert acc["balance_now"] == 1050000
    assert acc["value_prev_cents"] == 1000000 and acc["value_prev_date"] == "2026-10-01"


def test_depot_does_not_change_the_daily_balance(client, db):
    giro = client.post("/api/accounts", json={"name": "Testgiro", "kind": "giro"}).json()["id"]
    client.post(f"/api/accounts/{giro}/balance", json={"balance_cents": 150000, "date": "2026-11-01"})
    depot = client.post("/api/accounts", json={"name": "Testdepot", "kind": "depot"}).json()["id"]
    client.post(f"/api/accounts/{depot}/balance", json={"balance_cents": 2000000, "date": "2026-11-01"})

    summary = services.build_summary(db)
    assert {a["id"] for a in summary["forecast"]["accounts"]} == {giro}


def test_giro_balance_does_not_create_valuations(client, db):
    giro = client.post("/api/accounts", json={"name": "Testgiro", "kind": "giro"}).json()["id"]
    client.post(f"/api/accounts/{giro}/balance", json={"balance_cents": 150000, "date": "2026-11-01"})
    assert ledger.valuations(db, giro) == []


def test_deleting_a_depot_removes_its_values(client, db):
    aid = client.post("/api/accounts", json={"name": "Testdepot", "kind": "depot"}).json()["id"]
    client.post(f"/api/accounts/{aid}/balance", json={"balance_cents": 500000, "date": "2026-11-01"})
    client.delete(f"/api/accounts/{aid}")
    assert db.scalar("SELECT COUNT(*) FROM valuations") == 0
