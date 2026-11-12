"""Verträge aus der App ändern und Kündigungsschreiben holen – nur erfundene Daten."""
from datetime import date, timedelta

from test_mobile_write import https_client, paired_headers, reset_mobile_guards

KEY = "manual:test-abo"


def _contract(db, **extra):
    data = {"key": KEY, "name": "Erfundenes Abo", "status": "confirmed", "manual": 1, "active": 1,
            "kind": "expense", "interval": "monatlich", "amount_cents": -1599}
    data.update(extra)
    db.insert("contracts", data)


def test_status_changes_and_price_acknowledgement(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    _contract(db, prev_amount_cents=-1399)
    with https_client() as client:
        headers = paired_headers(client)
        listed = client.get("/api/v1/contracts", headers=headers).json()["items"]
        item = next(c for c in listed if c["key"] == KEY)
        assert item["price_change_cents"] == -200 and item["manual"] is True

        r = client.patch(f"/api/v1/contracts/{KEY}", json={"price_change_ack": True}, headers=headers)
        assert r.status_code == 200 and r.json()["contract"]["price_change_cents"] is None

        r = client.patch(f"/api/v1/contracts/{KEY}", json={"status": "cancelled"}, headers=headers)
        assert r.status_code == 200 and r.json()["contract"]["status"] == "cancelled"
        assert db.scalar("SELECT cancelled_on FROM contracts WHERE key = ?", (KEY,)) == date.today().isoformat()

        r = client.patch(f"/api/v1/contracts/{KEY}", json={"status": "ignored"}, headers=headers)
        assert r.status_code == 200
        listed = client.get("/api/v1/contracts", headers=headers).json()["items"]
        assert all(c["key"] != KEY for c in listed)


def test_contract_changes_are_validated(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    _contract(db)
    with https_client() as client:
        headers = paired_headers(client)
        for body in ({}, {"status": "weg"}, {"name": "Neu"}, {"price_change_ack": False},
                     {"status": "confirmed", "notes": "x"}):
            assert client.patch(f"/api/v1/contracts/{KEY}", json=body, headers=headers).status_code == 400, body
        assert client.patch("/api/v1/contracts/manual:gibtsnicht", json={"status": "confirmed"},
                            headers=headers).status_code == 404
        assert client.patch("/api/v1/contracts/" + "x" * 201, json={"status": "confirmed"},
                            headers=headers).status_code == 404
        assert client.patch(f"/api/v1/contracts/{KEY}", json={"status": "ignored"}).status_code == 401
        assert db.scalar("SELECT status FROM contracts WHERE key = ?", (KEY,)) == "confirmed"


def test_letter_uses_the_profile_and_the_mode(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    _contract(db, customer_no="K-0001", provider_email="kuendigung@example.org")
    db.set_setting("profile", {"name": "Erika Muster", "street": "Testweg 1", "city": "12345 Teststadt"})
    with https_client() as client:
        headers = paired_headers(client)
        r = client.post(f"/api/v1/contracts/{KEY}/letter", json={}, headers=headers)
        assert r.status_code == 200
        letter = r.json()
        assert letter["profile_complete"] is True
        assert letter["email"] == "kuendigung@example.org"
        assert "fristgerecht zum nächstmöglichen Zeitpunkt" in letter["body"]
        assert letter["letter"].startswith("Erika Muster\nTestweg 1\n12345 Teststadt")
        assert "K-0001" in letter["subject"]

        on = (date.today() + timedelta(days=40)).isoformat()
        r = client.post(f"/api/v1/contracts/{KEY}/letter", json={"mode": "termin", "date": on}, headers=headers)
        assert r.status_code == 200
        assert date.fromisoformat(on).strftime("%d.%m.%Y") in r.json()["body"]

        r = client.post(f"/api/v1/contracts/{KEY}/letter", json={"mode": "sonder"}, headers=headers)
        assert "Preiserhöhung" in r.json()["body"]


def test_letter_requests_are_validated(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    _contract(db)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    with https_client() as client:
        headers = paired_headers(client)
        for body in ({"mode": "fristlos"}, {"mode": "termin"}, {"mode": "termin", "date": "morgen"},
                     {"mode": "termin", "date": yesterday}, {"mode": "ordentlich", "date": "2030-01-01"},
                     {"mode": "ordentlich", "to": "x"}):
            assert client.post(f"/api/v1/contracts/{KEY}/letter", json=body, headers=headers).status_code == 400, body
        r = client.post(f"/api/v1/contracts/{KEY}/letter", json={}, headers=headers)
        assert r.json()["profile_complete"] is False
        assert client.post("/api/v1/contracts/manual:nix/letter", json={}, headers=headers).status_code == 404
        assert client.post(f"/api/v1/contracts/{KEY}/letter", json={}).status_code == 401
