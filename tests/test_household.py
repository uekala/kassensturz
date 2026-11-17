"""Haushalt: Personen, Kontobesitz und was ein Handy sehen darf – nur erfundene Daten."""
from datetime import date

import pytest

from kassensturz import db as dbmod
from kassensturz import household
from test_mobile_write import https_client, reset_mobile_guards

TODAY = date.today().isoformat()

# Alle Leseendpunkte der App. Jeder muss für jede Person funktionieren und darf nichts Fremdes zeigen.
READ_PATHS = (
    "/api/v1/me", "/api/v1/overview", "/api/v1/transactions", "/api/v1/transactions?q=KS", "/api/v1/stats",
    "/api/v1/afford?amount_cents=100", "/api/v1/accounts", "/api/v1/sync", "/api/v1/categories", "/api/v1/contracts",
    "/api/v1/networth", "/api/v1/news", "/api/v1/papers", "/api/v1/triage", "/api/v1/budgets/suggestions",
)


def pair(client, person_id=None, name="Testgerät"):
    body = {} if person_id is None else {"person_id": person_id}
    created = client.post("/api/mobile/pairings", json=body)
    assert created.status_code == 201, created.text
    paired = client.post("/api/v1/pair", json={"pairing_secret": created.json()["pairing_secret"], "device_name": name})
    assert paired.status_code == 201
    return {"Authorization": f"Bearer {paired.json()['access_token']}"}


def booking(db, account_id, cents, who, request_id=None):
    return db.insert("transactions", {
        "account_id": account_id, "booking_date": TODAY, "amount_cents": cents, "counterparty": who,
        "purpose": f"Zweck {who}", "source": "manual", "created": TODAY, "client_request_id": request_id})


@pytest.fixture()
def home(db, monkeypatch):
    """Anna und Ben mit je einem privaten Konto und einem gemeinsamen."""
    reset_mobile_guards(monkeypatch)
    anna = household.create_person(db, {"name": "Anna"})["id"]
    ben = household.create_person(db, {"name": "Ben"})["id"]
    accounts = {
        "shared": db.insert("accounts", {"name": "KS-GEMEINSAM Kasse", "kind": "cash", "balance_cents": 10000,
                                         "balance_date": "2020-01-01"}),
        "anna": db.insert("accounts", {"name": "KS-ANNA Kasse", "kind": "cash", "owner_person_id": anna,
                                       "balance_cents": 20000, "balance_date": "2020-01-01"}),
        "ben": db.insert("accounts", {"name": "KS-BEN Kasse", "kind": "cash", "owner_person_id": ben,
                                      "balance_cents": 40000, "balance_date": "2020-01-01"}),
    }
    tx = {
        "shared": booking(db, accounts["shared"], -1100, "KS-GEMEINSAM Markt"),
        "anna": booking(db, accounts["anna"], -2200, "KS-ANNA Buchladen"),
        "ben": booking(db, accounts["ben"], -4400, "KS-BEN Baumarkt"),
    }
    db.insert("contracts", {"key": "ks-ben-vertrag", "name": "KS-BEN Vertrag", "counterparty": "KS-BEN Anbieter",
                            "interval": "monthly", "amount_cents": -999, "account_id": accounts["ben"], "manual": 1,
                            "status": "confirmed", "next_due": TODAY})
    db.insert("goals", {"name": "KS-BEN Ziel", "target_cents": 50000, "account_id": accounts["ben"]})
    db.insert("valuations", {"account_id": accounts["ben"], "on_date": TODAY, "value_cents": 123456})
    return {"db": db, "anna": anna, "ben": ben, "accounts": accounts, "tx": tx}


def test_without_private_accounts_every_device_sees_everything(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    household.create_person(db, {"name": "Anna"})
    account = db.insert("accounts", {"name": "KS-GEMEINSAM Kasse", "kind": "cash"})
    booking(db, account, -500, "KS-GEMEINSAM Markt")
    assert db.scoped(None) is db
    with https_client() as client:
        headers = pair(client)
        assert [a["ownership"] for a in client.get("/api/v1/accounts", headers=headers).json()["items"]] == ["shared"]
        assert client.get("/api/v1/transactions", headers=headers).json()["total"] == 1
        profile = client.get("/api/v1/me", headers=headers).json()["household"]
        assert profile == {"person": None, "persons": 1, "private_accounts": False}


def test_every_read_endpoint_hides_the_other_persons_data(home):
    with https_client() as client:
        anna = pair(client, home["anna"], "Annas Handy")
        ben = pair(client, home["ben"], "Bens Handy")
        nobody = pair(client, None, "Altes Handy")
        for path in READ_PATHS:
            for headers, foreign, own in ((anna, ("KS-BEN",), "KS-ANNA"), (ben, ("KS-ANNA",), "KS-BEN"),
                                          (nobody, ("KS-ANNA", "KS-BEN"), None)):
                response = client.get(path, headers=headers)
                assert response.status_code == 200, (path, response.text)
                for marker in foreign:
                    assert marker not in response.text, (path, marker)
        # Gegenprobe: Bei Ben selbst tauchen seine Buchung, sein Vertrag und sein Ziel auf.
        seen = "".join(client.get(path, headers=ben).text for path in READ_PATHS)
        for marker in ("KS-BEN Baumarkt", "KS-BEN Vertrag", "KS-BEN Ziel", "KS-BEN Kasse", "KS-GEMEINSAM Markt"):
            assert marker in seen, marker
        # Das Eigene und das Gemeinsame kommen an.
        listed = client.get("/api/v1/transactions", headers=anna).json()
        assert sorted(i["counterparty"] for i in listed["items"]) == ["KS-ANNA Buchladen", "KS-GEMEINSAM Markt"]
        accounts = {a["name"]: a for a in client.get("/api/v1/accounts", headers=anna).json()["items"]}
        assert {name: a["ownership"] for name, a in accounts.items()} == {
            "KS-GEMEINSAM Kasse": "shared", "KS-ANNA Kasse": "mine"}
        assert accounts["KS-ANNA Kasse"]["balance_cents"] == 20000 - 2200
        overview = client.get("/api/v1/overview", headers=anna).json()
        assert {a["name"]: a["ownership"] for a in overview["accounts"]} == {
            "KS-GEMEINSAM Kasse": "shared", "KS-ANNA Kasse": "mine"}
        assert overview["household"]["person"]["name"] == "Anna"
        assert overview["household"]["private_accounts"] is True
        assert client.get("/api/v1/overview", headers=nobody).json()["household"]["person"] is None
        # Summen rechnen nur mit dem Sichtbaren.
        month = client.get("/api/v1/stats", headers=anna).json()["month"]
        assert month["expense_cents"] == 1100 + 2200
        assert client.get("/api/v1/stats", headers=nobody).json()["month"]["expense_cents"] == 1100
        # Ein Filter auf ein fremdes Konto liefert nichts, nicht dessen Buchungen.
        hidden = client.get(f"/api/v1/transactions?account_id={home['accounts']['ben']}", headers=anna).json()
        assert hidden["total"] == 0 and hidden["items"] == []
        assert client.get("/api/v1/me", headers=anna).json()["household"] == {
            "person": {"id": home["anna"], "name": "Anna", "color": None}, "persons": 2, "private_accounts": True}


def test_writes_to_foreign_accounts_are_refused_like_unknown_ones(home):
    db, tx, accounts = home["db"], home["tx"], home["accounts"]
    receipt = db.insert("receipts", {"tx_id": tx["ben"], "filename": "ks-ben.pdf", "stored": "ks-ben.pdf",
                                     "mime": "application/pdf", "size": 3, "created": TODAY})
    with https_client() as client:
        anna = pair(client, home["anna"])
        created = client.post("/api/v1/transactions", headers=anna, json={
            "client_request_id": "a" * 32, "account_id": accounts["ben"], "booking_date": TODAY,
            "amount_cents": -100, "counterparty": "KS-ANNA Versuch"})
        assert created.status_code == 400
        unknown = client.post("/api/v1/transactions", headers=anna, json={
            "client_request_id": "b" * 32, "account_id": 999999, "booking_date": TODAY,
            "amount_cents": -100, "counterparty": "KS-ANNA Versuch"})
        assert created.json() == unknown.json()

        assert client.patch(f"/api/v1/transactions/{tx['ben']}", headers=anna, json={"note": "x"}).status_code == 404
        assert client.delete(f"/api/v1/transactions/{tx['ben']}", headers=anna).status_code == 404
        assert client.get(f"/api/v1/transactions/{tx['ben']}/receipts", headers=anna).status_code == 404
        assert client.post(f"/api/v1/transactions/{tx['ben']}/receipts?filename=a.pdf", headers=anna,
                           content=b"%PDF-1.4").status_code == 404
        assert client.get(f"/api/v1/receipts/{receipt}", headers=anna).status_code == 404
        assert client.delete(f"/api/v1/receipts/{receipt}", headers=anna).status_code == 404
        assert client.patch("/api/v1/contracts/ks-ben-vertrag", headers=anna, json={"status": "ignored"}).status_code == 404
        assert client.post("/api/v1/contracts/ks-ben-vertrag/letter", headers=anna, json={}).status_code == 404

        # Nichts davon hat etwas verändert.
        assert db.scalar("SELECT COUNT(*) FROM transactions") == 3
        assert db.scalar("SELECT note FROM transactions WHERE id = ?", (tx["ben"],)) is None
        assert db.scalar("SELECT COUNT(*) FROM receipts") == 1
        assert db.scalar("SELECT status FROM contracts WHERE key = 'ks-ben-vertrag'") == "confirmed"

        # Auf dem eigenen und dem gemeinsamen Konto geht es.
        assert client.patch(f"/api/v1/transactions/{tx['anna']}", headers=anna, json={"note": "ok"}).status_code == 200
        assert client.patch(f"/api/v1/transactions/{tx['shared']}", headers=anna, json={"note": "ok"}).status_code == 200
        ben = pair(client, home["ben"])
        assert client.patch("/api/v1/contracts/ks-ben-vertrag", headers=ben, json={"status": "ignored"}).status_code == 200


def test_cash_account_from_the_app_belongs_to_its_person(home):
    db = home["db"]
    with https_client() as client:
        anna = pair(client, home["anna"])
        ben = pair(client, home["ben"])
        created = client.post("/api/v1/accounts", headers=anna, json={"name": "KS-ANNA Spardose"})
        assert created.status_code == 201
        assert created.json()["account"]["ownership"] == "mine"
        assert db.scalar("SELECT owner_person_id FROM accounts WHERE name = 'KS-ANNA Spardose'") == home["anna"]
        assert "KS-ANNA Spardose" not in client.get("/api/v1/accounts", headers=ben).text


def test_the_view_of_a_person_cannot_write(home):
    view = home["db"].scoped(home["anna"])
    assert view is not home["db"]
    assert view.scalar("SELECT COUNT(*) FROM accounts") == 2
    for call in (lambda: view.execute("DELETE FROM accounts"), lambda: view.insert("accounts", {"name": "x"}),
                 lambda: view.update("accounts", "id", 1, {"name": "x"}), lambda: view.tx()):
        with pytest.raises(RuntimeError):
            call()
    with pytest.raises(Exception):
        view.query("DELETE FROM main.accounts")
    assert home["db"].scalar("SELECT COUNT(*) FROM accounts") == 3


def test_ownership_changes_show_up_at_once(home):
    db = home["db"]
    with https_client() as client:
        anna = pair(client, home["anna"])
        assert "KS-BEN" not in client.get("/api/v1/accounts", headers=anna).text
        assert client.patch(f"/api/accounts/{home['accounts']['ben']}", json={"owner_person_id": None}).status_code == 200
        assert "KS-BEN Kasse" in client.get("/api/v1/accounts", headers=anna).text
        assert client.patch(f"/api/accounts/{home['accounts']['ben']}", json={"owner_person_id": home["ben"]}).status_code == 200
        assert "KS-BEN" not in client.get("/api/v1/accounts", headers=anna).text
        assert client.patch(f"/api/accounts/{home['accounts']['ben']}", json={"owner_person_id": 999}).status_code == 400
        assert db.scalar("SELECT owner_person_id FROM accounts WHERE id = ?", (home["accounts"]["ben"],)) == home["ben"]


def test_persons_are_managed_from_the_local_administration(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    with https_client() as client:
        anna = client.post("/api/persons", json={"name": "  Anna  Muster ", "color": "#AABBCC"})
        assert anna.status_code == 200
        assert (anna.json()["name"], anna.json()["color"]) == ("Anna Muster", "#aabbcc")
        pid = anna.json()["id"]
        assert client.post("/api/persons", json={"name": "anna muster"}).status_code == 409
        for bad in ({}, {"name": ""}, {"name": 5}, {"name": "Ben", "color": "rot"}):
            assert client.post("/api/persons", json=bad).status_code == 400, bad
        assert client.patch(f"/api/persons/{pid}", json={"name": "Anna"}).json()["name"] == "Anna"
        assert client.patch("/api/persons/999", json={"name": "X"}).status_code == 404

        account = db.insert("accounts", {"name": "KS-ANNA Kasse", "kind": "cash", "owner_person_id": pid})
        headers = pair(client, pid, "Annas Handy")
        listed = client.get("/api/persons").json()
        assert [(p["name"], p["accounts"], p["devices"]) for p in listed] == [("Anna", 1, 1)]

        # Solange Konten oder Geräte daran hängen, bleibt die Person: Privates wird nicht still gemeinsam.
        assert client.delete(f"/api/persons/{pid}").status_code == 409
        db.update("accounts", "id", account, {"owner_person_id": None})
        assert client.delete(f"/api/persons/{pid}").status_code == 409
        device = client.get("/api/mobile/devices").json()["items"][0]
        assert device["person_id"] == pid
        assert client.patch(f"/api/mobile/devices/{device['id']}", json={"person_id": None}).status_code == 200
        assert client.get("/api/v1/me", headers=headers).json()["household"]["person"] is None
        assert client.delete(f"/api/persons/{pid}").status_code == 200
        assert client.get("/api/persons").json() == []


def test_device_assignment_is_validated(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    pid = household.create_person(db, {"name": "Anna"})["id"]
    with https_client() as client:
        assert client.post("/api/mobile/pairings", json={"person_id": 999}).status_code == 400
        assert client.post("/api/mobile/pairings", json={"person_id": "1"}).status_code == 400
        headers = pair(client)
        device = client.get("/api/mobile/devices").json()["items"][0]["id"]
        assert client.patch(f"/api/mobile/devices/{device}", json={"person_id": 999}).status_code == 400
        assert client.patch(f"/api/mobile/devices/{device}", json={}).status_code == 400
        assert client.patch("/api/mobile/devices/gibtsnicht", json={"person_id": pid}).status_code == 404
        assert client.patch(f"/api/mobile/devices/{device}", json={"person_id": pid}).status_code == 200
        assert client.get("/api/v1/me", headers=headers).json()["household"]["person"]["name"] == "Anna"
        # Von außerhalb der lokalen Verwaltung geht das nicht.
        outside = https_client(peer="203.0.113.7")
        assert outside.patch(f"/api/mobile/devices/{device}", json={"person_id": None}).status_code == 403
        assert outside.get("/api/persons").status_code == 403
        assert outside.post("/api/persons", json={"name": "Fremd"}).status_code == 403
        assert db.scalar("SELECT person_id FROM mobile_devices WHERE id = ?", (device,)) == pid
        assert db.scalar("SELECT COUNT(*) FROM persons") == 1


def test_old_database_gets_the_new_columns(tmp_path):
    import sqlite3

    path = tmp_path / "alt.sqlite"
    first = dbmod.Database(path)
    first.close()
    # Stand vor dem Haushalt nachstellen: Spalten weg, Tabelle weg, alte Schema-Version.
    raw = sqlite3.connect(path)
    for table, column in (("accounts", "owner_person_id"), ("mobile_devices", "person_id"), ("mobile_pairings", "person_id")):
        raw.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
    raw.execute("DROP TABLE persons")
    raw.execute("INSERT INTO accounts(name, kind) VALUES('KS-ALT Kasse', 'cash')")
    raw.execute("PRAGMA user_version = 1")
    raw.commit()
    raw.close()

    again = dbmod.Database(path)
    try:
        assert again.one("SELECT name, owner_person_id FROM accounts") == {"name": "KS-ALT Kasse", "owner_person_id": None}
        assert again.scalar("SELECT COUNT(*) FROM persons") == 0
        for table in ("mobile_devices", "mobile_pairings"):
            assert "person_id" in {r["name"] for r in again.query(f"PRAGMA table_info({table})")}
        assert again.conn.execute("PRAGMA user_version").fetchone()[0] == dbmod.SCHEMA_VERSION
    finally:
        again.close()
