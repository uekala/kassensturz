"""App: Wert eines Depots und Restschuld eines Kredits eintragen – nur erfundene Daten."""
from datetime import date

from test_mobile_write import https_client, paired_headers, reset_mobile_guards

from kassensturz import household


def test_value_of_deposit_and_loan(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    depot = db.insert("accounts", {"name": "KS-Testdepot", "kind": "depot", "in_forecast": 0})
    loan = db.insert("accounts", {"name": "KS-Testkredit", "kind": "kredit", "in_forecast": 0})
    giro = db.insert("accounts", {"name": "KS-Testgiro", "kind": "giro"})
    today = date.today().isoformat()
    with https_client() as client:
        assert client.put(f"/api/v1/accounts/{depot}/value", json={"value_cents": 1}).status_code == 401
        headers = paired_headers(client)
        assert "accounts.value" in client.get("/api/v1/me", headers=headers).json()["capabilities"]
        flags = {a["id"]: a["value_editable"] for a in client.get("/api/v1/accounts", headers=headers).json()["items"]}
        assert flags == {depot: True, loan: True, giro: False}
        over = {a["id"]: a["value_editable"] for a in client.get("/api/v1/overview", headers=headers).json()["accounts"]}
        assert over == flags

        for bad in ({}, {"value_cents": "5"}, {"value_cents": -1}, {"value_cents": True},
                    {"value_cents": 5, "date": "2026-01-01"}, {"value_cents": 10**12}):
            assert client.put(f"/api/v1/accounts/{depot}/value", json=bad, headers=headers).status_code == 400, bad
        assert client.put(f"/api/v1/accounts/{giro}/value", json={"value_cents": 5}, headers=headers).status_code == 409
        assert client.put("/api/v1/accounts/999/value", json={"value_cents": 5}, headers=headers).status_code == 404
        assert db.scalar("SELECT COUNT(*) FROM valuations") == 0

        got = client.put(f"/api/v1/accounts/{depot}/value", json={"value_cents": 1234500}, headers=headers)
        assert got.status_code == 200, got.text
        assert got.json()["account"]["balance_cents"] == 1234500 and got.json()["account"]["balance_date"] == today
        # Ein zweiter Wert am selben Tag ersetzt den ersten.
        client.put(f"/api/v1/accounts/{depot}/value", json={"value_cents": 1300000}, headers=headers)
        assert db.query("SELECT on_date, value_cents FROM valuations WHERE account_id = ?", (depot,)) == [
            {"on_date": today, "value_cents": 1300000}]

        # Die Restschuld wird positiv eingegeben und zählt als Schuld.
        got = client.put(f"/api/v1/accounts/{loan}/value", json={"value_cents": 800000}, headers=headers)
        assert got.json()["account"]["balance_cents"] == -800000
        texts = [r["text"] for r in db.query("SELECT text FROM audit_log ORDER BY id DESC LIMIT 2")]
        assert texts[0].startswith("Restschuld von „KS-Testkredit“ eingetragen: 8.000,00")
        assert texts[1].startswith("Wert von „KS-Testdepot“ eingetragen: 13.000,00")


def test_value_respects_persons(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    anna = household.create_person(db, {"name": "Anna"})["id"]
    ben = household.create_person(db, {"name": "Ben"})["id"]
    kim = household.create_person(db, {"name": "Kim", "is_child": True})["id"]
    depot = db.insert("accounts", {"name": "KS-Annas Depot", "kind": "depot", "in_forecast": 0, "owner_person_id": anna})

    def headers_for(client, person):
        secret = client.post("/api/mobile/pairings", json={"person_id": person}).json()["pairing_secret"]
        token = client.post("/api/v1/pair", json={"pairing_secret": secret, "device_name": "KS-Handy"}).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    with https_client() as client:
        body = {"value_cents": 500000}
        assert client.put(f"/api/v1/accounts/{depot}/value", json=body, headers=headers_for(client, ben)).status_code == 404
        kid = headers_for(client, kim)
        assert "accounts.value" not in client.get("/api/v1/me", headers=kid).json()["capabilities"]
        assert client.put(f"/api/v1/accounts/{depot}/value", json=body, headers=kid).status_code == 403
        assert db.scalar("SELECT COUNT(*) FROM valuations") == 0
        assert client.put(f"/api/v1/accounts/{depot}/value", json=body, headers=headers_for(client, anna)).status_code == 200
