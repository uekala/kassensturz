"""Garantiefristen – nur erfundene Daten."""
from datetime import date, timedelta

from kassensturz import ha, ledger, papers, services
from test_mobile_write import https_client, paired_headers, reset_mobile_guards


def _tx(db, who="Erfundener Elektromarkt", cents=-59900, archived=0):
    acc = db.insert("accounts", {"name": "Testgiro", "kind": "giro", "archived": archived})
    ledger.import_rows(db, acc, [{"booking_date": "2025-01-15", "amount_cents": cents, "counterparty": who, "purpose": "Test"}], "fints")
    return db.scalar("SELECT MAX(id) FROM transactions")


def _in(days):
    return (date.today() + timedelta(days=days)).isoformat()


def test_warranty_is_set_validated_and_cleared(client, db):
    tx = _tx(db)
    assert client.patch(f"/api/transactions/{tx}", json={"warranty_until": "2027-01-15"}).status_code == 200
    assert client.get("/api/transactions").json()["items"][0]["warranty_until"] == "2027-01-15"
    for bad in ("15.01.2027", "2027-13-01", "1999-01-01", "morgen", 20270115):
        assert client.patch(f"/api/transactions/{tx}", json={"warranty_until": bad}).status_code == 400, bad
    assert client.patch(f"/api/transactions/{tx}", json={"note": "Waschmaschine"}).status_code == 200
    assert db.scalar("SELECT warranty_until FROM transactions WHERE id = ?", (tx,)) == "2027-01-15"
    client.patch(f"/api/transactions/{tx}", json={"warranty_until": ""})
    assert db.scalar("SELECT warranty_until FROM transactions WHERE id = ?", (tx,)) is None


def test_overview_sorts_running_and_keeps_recently_expired(client, db):
    later, soon, gone, old, hidden = (_tx(db, "Erfundener Laden A"), _tx(db, "Erfundener Laden B"), _tx(db, "Erfundener Laden C"),
                                      _tx(db, "Erfundener Laden D"), _tx(db, "Erfundener Laden E", archived=1))
    for tx, days in ((later, 400), (soon, 12), (gone, -10), (old, -200), (hidden, 5)):
        db.update("transactions", "id", tx, {"warranty_until": _in(days)})
    db.update("transactions", "id", soon, {"note": "Erfundener Staubsauger"})

    data = client.get("/api/warranties").json()

    assert [w["id"] for w in data["running"]] == [soon, later]
    assert data["running"][0]["label"] == "Erfundener Staubsauger"
    assert data["running"][0]["days_left"] == 12
    assert [w["id"] for w in data["expired"]] == [gone]
    assert data["soon"] == 1


def test_alert_thirty_days_before_the_end_and_only_once(db, monkeypatch):
    tx = _tx(db)
    far = _tx(db, "Erfundener Laden B")
    db.update("transactions", "id", tx, {"warranty_until": _in(20), "note": "Erfundene Waschmaschine"})
    db.update("transactions", "id", far, {"warranty_until": _in(45)})
    sent = []
    monkeypatch.setattr(ha, "available", lambda: True)
    monkeypatch.setattr(ha, "_post", lambda path, payload: sent.append((path, payload)) or True)

    services.refresh(db)
    services.refresh(db)

    alerts = [a for a in services.alerts(db, services.build_summary(db)) if a["key"].startswith("warranty:")]
    assert [a["title"] for a in alerts] == ["Garantie läuft ab: Erfundene Waschmaschine"]
    assert "in 20 Tagen" in alerts[0]["text"]
    assert "Beleg ist noch nicht hinterlegt" in alerts[0]["text"]
    notes = [p for path, p in sent if path.startswith("/services/") and "Garantie" in str(p)]
    assert len(notes) == 1

    papers.add_receipt(db, tx, "a.pdf", b"%PDF-1.4\n")
    alerts = [a for a in services.alerts(db, services.build_summary(db)) if a["key"].startswith("warranty:")]
    assert "Beleg" not in alerts[0]["text"]


def test_app_can_set_and_remove_the_warranty(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    tx = _tx(db)
    with https_client() as client:
        headers = paired_headers(client)
        r = client.patch(f"/api/v1/transactions/{tx}", json={"warranty_until": "2027-01-15"}, headers=headers)
        assert r.status_code == 200
        assert r.json()["transaction"]["warranty_until"] == "2027-01-15"
        assert client.get("/api/v1/transactions", headers=headers).json()["items"][0]["warranty_until"] == "2027-01-15"
        for bad in ("2027-1-5", 5, ["2027-01-15"]):
            assert client.patch(f"/api/v1/transactions/{tx}", json={"warranty_until": bad}, headers=headers).status_code == 400, bad
        r = client.patch(f"/api/v1/transactions/{tx}", json={"warranty_until": None}, headers=headers)
        assert r.json()["transaction"]["warranty_until"] is None
