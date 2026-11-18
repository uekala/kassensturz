"""Erwartete Eingänge – nur erfundene Daten."""
from datetime import date, timedelta

import pytest

from kassensturz import expected, household, ledger, services

TODAY = date.today()


def day(back: int) -> str:
    return (TODAY - timedelta(days=back)).isoformat()


def book(db, acc, back, cents, who, **extra):
    ledger.import_rows(db, acc, [{"booking_date": day(back), "amount_cents": cents, "counterparty": who,
                                  "purpose": f"Beleg {back} {cents}", **extra}], "openbanking")
    return db.scalar("SELECT MAX(id) FROM transactions")


@pytest.fixture()
def giro(db):
    return db.insert("accounts", {"name": "KS-Girokonto", "kind": "giro"})


def test_refund_is_expected_from_an_expense_and_ticked_off_when_it_arrives(client, db, giro):
    bought = book(db, giro, 10, -7990, "Erfundener Versand GmbH")
    made = client.post("/api/expected", json={"tx_id": bought})
    assert made.status_code == 200, made.text
    item = made.json()
    assert (item["label"], item["cents"], item["status"], item["since"]) == ("Erfundener Versand GmbH", 7990, "open", day(10))
    assert item["due_date"] == (TODAY + timedelta(days=expected.DUE_DAYS)).isoformat() and item["waiting_days"] == 10
    assert client.get("/api/overview").json()["expected"]["open_cents"] == 7990
    # Ein zweiter offener Eingang zur selben Ausgabe ergibt keinen Sinn.
    assert client.post("/api/expected", json={"tx_id": bought}).status_code == 409

    book(db, giro, 4, 1500, "Erfundener Versand GmbH")             # anderer Betrag: nur ein Vorschlag
    book(db, giro, 3, 7990, "Erfundene Tante")                     # anderer Absender: nur ein Vorschlag
    assert expected.settle(db) == 0
    assert [c["amount_cents"] for c in client.get("/api/expected").json()["open"][0]["candidates"]] == [7990, 1500]

    refund = book(db, giro, 2, 7990, "ERFUNDENER VERSAND GMBH RETOURE 4711")
    services.refresh(db, notify=False)
    seen = client.get("/api/expected").json()
    assert seen["open"] == [] and seen["open_cents"] == 0
    assert [(c["status"], c["received_tx_id"], c["closed_on"]) for c in seen["closed"]] == [("received", refund, day(2))]


def test_what_is_not_ticked_off_by_itself(db, giro):
    other = db.insert("accounts", {"name": "KS-Karte", "kind": "kreditkarte"})
    bought = book(db, giro, 10, -5000, "Erfundener Versand")
    book(db, giro, 12, 5000, "Erfundener Versand")                 # vor der Ausgabe gebucht
    book(db, other, 2, 5000, "Erfundener Versand")                 # anderes Konto
    expected.create(db, {"tx_id": bought})
    assert expected.settle(db) == 0
    # Ohne Ausgabe dahinter gibt es keinen Empfänger zum Wiedererkennen: nie von selbst.
    expected.create(db, {"label": "Auslagen Dienstreise", "cents": 12000, "account_id": giro})
    book(db, giro, 0, 12000, "Erfundener Arbeitgeber")
    assert expected.settle(db) == 0
    alone = [i for i in expected.overview(db)["open"] if i["tx_id"] is None][0]
    assert [c["amount_cents"] for c in alone["candidates"]] == [12000]


def test_refund_is_recognised_by_name_even_after_a_direct_debit(db, giro):
    bought = book(db, giro, 10, -2990, "Erfundenes Abo Ltd", creditor_id="DE98ZZZ09999999999")
    expected.create(db, {"tx_id": bought})
    book(db, giro, 2, 2990, "Erfundenes Abo Ltd")                  # die Gutschrift trägt keine Gläubiger-ID
    assert expected.settle(db) == 1


@pytest.mark.parametrize("payee, other, same", [
    ("erfundener versand", "erfundener versand", True), ("erfundener versand", "erfundener versand retoure", True),
    ("erfundener versand retoure", "erfundener versand", True), ("erfundener versand", "erfundener versandhandel", False),
    ("rewe", "rewe markt", False), ("erfundener versand", "erfundene tante", False), (None, "erfundener versand", False),
    ("erfundener versand", None, False),
])
def test_names_are_compared_carefully(payee, other, same):
    assert expected._same(payee, other) is same


def test_transfer_onto_the_account_is_no_refund(db, giro):
    paypal = db.insert("accounts", {"name": "KS-PayPal", "kind": "paypal"})
    bought = book(db, paypal, 5, -6571, "Erfundener Versand")
    funding = book(db, paypal, 5, 6571, "Erfundener Versand", purpose="Bankgutschrift")
    db.execute("UPDATE transactions SET is_transfer = 1 WHERE id = ?", (funding,))
    item = expected.create(db, {"tx_id": bought})
    assert expected.settle(db) == 0 and item["candidates"] == []
    with pytest.raises(expected.ExpectedError):
        expected.close(db, item["id"], {"tx_id": funding})


def test_two_refunds_from_the_same_shop_each_take_one_income(db, giro):
    first = book(db, giro, 10, -2000, "Erfundener Versand", purpose="Bestellung 1")
    second = book(db, giro, 9, -2000, "Erfundener Versand", purpose="Bestellung 2")
    for tx in (first, second):
        expected.create(db, {"tx_id": tx})
    one = book(db, giro, 3, 2000, "Erfundener Versand", purpose="Gutschrift 1")
    assert expected.settle(db) == 1
    state = expected.overview(db)
    assert [i["tx_id"] for i in state["open"]] == [second] and state["closed"][0]["received_tx_id"] == one
    two = book(db, giro, 1, 2000, "Erfundener Versand", purpose="Gutschrift 2")
    assert expected.settle(db) == 1 and expected.settle(db) == 0
    assert {c["received_tx_id"] for c in expected.overview(db)["closed"]} == {one, two}


def test_ticking_off_dropping_and_reopening_by_hand(client, db, giro):
    item = client.post("/api/expected", json={"label": "  Auslagen   Dienstreise ", "cents": 12000, "account_id": giro,
                                              "note": "Hotel und Bahn", "due_date": day(-7)}).json()
    assert (item["label"], item["note"], item["due_date"], item["tx_id"]) == ("Auslagen Dienstreise", "Hotel und Bahn", day(-7), None)
    income = book(db, giro, 0, 11500, "Erfundener Arbeitgeber")
    # Ein Eingang mit anderem Betrag lässt sich trotzdem als der richtige wählen.
    done = client.post(f"/api/expected/{item['id']}/received", json={"tx_id": income}).json()
    assert (done["status"], done["received_tx_id"], done["closed_on"]) == ("received", income, day(0))
    assert client.post(f"/api/expected/{item['id']}/received", json={}).status_code == 409
    again = client.post(f"/api/expected/{item['id']}/reopen").json()
    assert (again["status"], again["received_tx_id"], again["closed_on"]) == ("open", None, None)
    assert client.post(f"/api/expected/{item['id']}/reopen").status_code == 409
    gone = client.post(f"/api/expected/{item['id']}/drop").json()
    assert gone["status"] == "dropped" and client.post(f"/api/expected/{item['id']}/drop").status_code == 409
    # Ohne Buchung abhaken geht auch, etwa bei Bargeld.
    cash = client.post("/api/expected", json={"label": "Geliehen an Erfundenen Freund", "cents": 2000, "account_id": giro}).json()
    assert client.post(f"/api/expected/{cash['id']}/received", json={}).json()["received_tx_id"] is None


def test_an_income_belongs_to_one_expectation_only(client, db, giro):
    a = client.post("/api/expected", json={"label": "Erstattung A", "cents": 3000, "account_id": giro}).json()
    b = client.post("/api/expected", json={"label": "Erstattung B", "cents": 3000, "account_id": giro}).json()
    income = book(db, giro, 0, 3000, "Erfundene Kasse")
    assert client.post(f"/api/expected/{a['id']}/received", json={"tx_id": income}).status_code == 200
    assert client.post(f"/api/expected/{b['id']}/received", json={"tx_id": income}).status_code == 400
    assert client.get("/api/expected").json()["open"][0]["candidates"] == []


def test_invalid_requests_are_refused(client, db, giro):
    income = book(db, giro, 3, 5000, "Erfundener Arbeitgeber")
    spent = book(db, giro, 2, -5000, "Erfundener Laden")
    archived = db.insert("accounts", {"name": "KS-Alt", "kind": "giro", "archived": 1})
    bad = [
        {"tx_id": income},                                           # kein Geld zurück zu einem Eingang
        {"tx_id": 9999}, {"tx_id": "1"},
        {"tx_id": spent, "cents": 5001},                             # mehr als bezahlt
        {"tx_id": spent, "cents": 0}, {"tx_id": spent, "cents": 12.5},
        {"tx_id": spent, "due_date": "bald"},
        {"cents": 1000, "account_id": giro},                         # ohne Bezeichnung
        {"label": "X", "cents": 1000},                               # ohne Konto
        {"label": "X", "cents": 1000, "account_id": archived},
        {"label": "X", "cents": -5, "account_id": giro},
        {"label": "X", "cents": 1000, "account_id": giro, "note": 7},
    ]
    for body in bad:
        assert client.post("/api/expected", json=body).status_code in (400, 404, 409), body
    assert db.scalar("SELECT COUNT(*) FROM expected_incomes") == 0
    assert client.post("/api/expected/77/received", json={}).status_code == 404
    partial = client.post("/api/expected", json={"tx_id": spent, "cents": 2000}).json()
    assert partial["cents"] == 2000  # nur ein Teil kommt zurück


def test_overdue_income_reminds_once_and_arrival_is_announced(client, db, giro, monkeypatch):
    bought = book(db, giro, 30, -4900, "Erfundener Versand")
    item = expected.create(db, {"tx_id": bought, "due_date": day(5)})
    sent = []
    monkeypatch.setattr(services.ha, "available", lambda: True)
    monkeypatch.setattr(services.ha, "_post", lambda path, body: sent.append(body.get("title", "")) or True)
    services.refresh(db)
    services.refresh(db)
    alerts = [a for a in client.get("/api/overview").json()["alerts"] if a["key"].startswith("expected-due:")]
    assert [(a["expected"], a["level"]) for a in alerts] == [(item["id"], "warning")]
    assert "49,00 € erwartet seit" in alerts[0]["text"]
    assert [t for t in sent if "Geld" in t] == ["Kassensturz: Geld steht noch aus: Erfundener Versand"]

    book(db, giro, 0, 4900, "Erfundener Versand")
    services.refresh(db)
    services.refresh(db)
    assert [t for t in sent if "Geld" in t][1:] == ["Kassensturz: Geld ist da: Erfundener Versand"]
    assert not [a for a in client.get("/api/overview").json()["alerts"] if a["key"].startswith("expected-due:")]


def test_each_person_sees_only_what_is_expected_on_their_accounts(db):
    anna = household.create_person(db, {"name": "Anna"})["id"]
    ben = household.create_person(db, {"name": "Ben"})["id"]
    shared = db.insert("accounts", {"name": "KS-Gemeinsam", "kind": "giro"})
    private = db.insert("accounts", {"name": "KS-Anna", "kind": "giro", "owner_person_id": anna})
    expected.create(db, {"label": "Kaution", "cents": 50000, "account_id": shared, "due_date": day(1)})
    mine = expected.create(db, {"label": "Auslagen Anna", "cents": 9000, "account_id": private, "due_date": day(1)})
    assert mine["owner_person_id"] == anna
    assert [i["label"] for i in expected.overview(db.scoped(anna))["open"]] == ["Kaution", "Auslagen Anna"]
    assert [i["label"] for i in expected.overview(db.scoped(ben))["open"]] == ["Kaution"]
    assert [a["owner_person_id"] for a in expected.alerts(db)] == [None, anna]
    assert len(expected.alerts(db.scoped(ben))) == 1


def test_deleted_bookings_and_accounts_take_their_expectations_along(db, giro):
    other = db.insert("accounts", {"name": "KS-Zweitkonto", "kind": "giro"})
    bought = book(db, giro, 10, -3000, "Erfundener Versand")
    expected.create(db, {"tx_id": bought})
    expected.create(db, {"label": "Kaution", "cents": 50000, "account_id": other})
    kept = expected.create(db, {"label": "Pfand", "cents": 800, "account_id": giro})
    income = book(db, giro, 0, 800, "Erfundener Getränkemarkt")
    expected.close(db, kept["id"], {"tx_id": income})
    db.execute("DELETE FROM transactions WHERE id IN (?, ?)", (bought, income))
    ledger.delete_account(db, other)
    services.refresh(db, notify=False)
    left = db.query("SELECT label, status, received_tx_id FROM expected_incomes")
    assert left == [{"label": "Pfand", "status": "received", "received_tx_id": None}]
