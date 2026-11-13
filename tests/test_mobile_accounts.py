"""Bargeld-Konto aus der App – nur erfundene Daten."""
from datetime import date

from test_mobile_write import https_client, paired_headers, reset_mobile_guards


def test_cash_account_is_created_and_takes_entries(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    with https_client() as client:
        headers = paired_headers(client)
        r = client.post("/api/v1/accounts", json={"name": "  Test  Bargeld ", "balance_cents": 5000}, headers=headers)
        assert r.status_code == 201
        account = r.json()["account"]
        assert account["name"] == "Test Bargeld"
        assert account["type"] == "bargeld"
        assert account["manual_entries"] is True
        assert account["balance_cents"] == 5000

        booked = client.post("/api/v1/transactions", headers=headers, json={
            "client_request_id": "a" * 32, "account_id": account["id"], "booking_date": date.today().isoformat(),
            "amount_cents": -450, "counterparty": "KS-MOBILTEST Bäckerei"})
        assert booked.status_code == 201
        listed = client.get("/api/v1/accounts", headers=headers).json()["items"]
        assert [a["balance_cents"] for a in listed] == [4550]

        again = client.post("/api/v1/accounts", json={"name": "test bargeld"}, headers=headers)
        assert again.status_code == 409
        assert db.scalar("SELECT COUNT(*) FROM accounts") == 1


def test_cash_account_without_balance_and_validation(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    with https_client() as client:
        assert client.post("/api/v1/accounts", json={"name": "Testkasse"}).status_code == 401
        headers = paired_headers(client)
        for bad in ({}, {"name": ""}, {"name": 5}, {"name": "Testkasse", "balance_cents": -1}, {"name": "Testkasse", "balance_cents": "5"},
                    {"name": "Testkasse", "balance_cents": True}, {"name": "Testkasse", "kind": "giro"},
                    {"name": "Testkasse", "iban": "DE00"}):
            assert client.post("/api/v1/accounts", json=bad, headers=headers).status_code == 400, bad
        assert db.scalar("SELECT COUNT(*) FROM accounts") == 0
        r = client.post("/api/v1/accounts", json={"name": "Testkasse"}, headers=headers)
        assert r.status_code == 201
        row = db.one("SELECT kind, balance_date, connection_id, iban FROM accounts")
        assert (row["kind"], row["balance_date"], row["connection_id"], row["iban"]) == ("bargeld", None, None, None)


def test_account_creation_is_rate_limited(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    with https_client() as client:
        headers = paired_headers(client)
        codes = [client.post("/api/v1/accounts", json={"name": ""}, headers=headers).status_code for _ in range(11)]
        assert codes == [400] * 10 + [429]
