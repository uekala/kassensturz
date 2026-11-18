"""Geplante Ausgaben – nur erfundene Daten."""
from datetime import date, timedelta

import pytest

from kassensturz import analytics, household, ledger, planned, services

TODAY = date.today()


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def book(db, acc, offset, cents, who, **extra):
    ledger.import_rows(db, acc, [{"booking_date": day(offset), "amount_cents": cents, "counterparty": who,
                                  "purpose": f"Beleg {offset} {cents}", **extra}], "openbanking")
    return db.scalar("SELECT MAX(id) FROM transactions")


@pytest.fixture()
def giro(db):
    acc = db.insert("accounts", {"name": "KS-Girokonto", "kind": "giro", "in_forecast": 1})
    ledger.set_balance_anchor(db, acc, 300000, TODAY.isoformat())
    return acc


def plan(client, giro, **over):
    body = {"label": "Erfundene Handwerkerrechnung", "cents": 85000, "due_date": day(5), "account_id": giro, **over}
    return client.post("/api/planned", json=body)


def test_planned_expense_lowers_free_money_and_the_curve_from_its_day(client, db, giro):
    before = analytics.forecast(db)
    made = plan(client, giro)
    assert made.status_code == 200, made.text
    item = made.json()
    assert (item["label"], item["cents"], item["status"], item["days_left"], item["overdue"]) == (
        "Erfundene Handwerkerrechnung", 85000, "open", 5, False)
    after = analytics.forecast(db)
    in_period = day(5) <= after["period_end"]
    assert after["planned_out_cents"] == (-85000 if in_period else 0)
    assert after["free_cents"] == before["free_cents"] + after["planned_out_cents"]
    assert after["fixed_out_cents"] == before["fixed_out_cents"]
    curve_before, curve_after = dict(before["future"]), dict(after["future"])
    assert curve_after[day(4)] == curve_before[day(4)]
    assert curve_after[day(5)] == curve_before[day(5)] - 85000
    assert curve_after[day(40)] == curve_before[day(40)] - 85000
    line = next(u for u in after["upcoming"] if u.get("planned") == item["id"])
    assert (line["date"], line["amount_cents"], line["name"], line["overdue"]) == (
        day(5), -85000, "Erfundene Handwerkerrechnung", False)
    seen = client.get("/api/overview").json()
    assert seen["planned"]["open_cents"] == 85000 and seen["forecast"]["planned_out_cents"] == after["planned_out_cents"]
    assert any(u["name"] == "Erfundene Handwerkerrechnung" for u in seen["upcoming"])


def test_plan_beyond_the_horizon_waits_and_one_on_a_savings_account_does_not_count(client, db, giro):
    before = analytics.forecast(db)
    assert plan(client, giro, due_date=day(120)).status_code == 200
    spar = db.insert("accounts", {"name": "KS-Tagesgeld", "kind": "tagesgeld", "in_forecast": 0})
    made = plan(client, spar, label="Erfundene Anzahlung")
    assert made.status_code == 200 and made.json()["in_forecast"] is False
    after = analytics.forecast(db)
    assert after["free_cents"] == before["free_cents"] and after["future"] == before["future"]
    assert client.get("/api/planned").json()["open_cents"] == 170000


def test_exact_booking_ticks_the_plan_off_and_stops_counting(client, db, giro):
    item = plan(client, giro).json()
    book(db, giro, 0, -4990, "Erfundener Baumarkt")                # anderer Betrag: bleibt offen
    assert planned.settle(db) == 0
    paid = book(db, giro, 0, -85000, "Erfundener Handwerker")
    services.refresh(db, notify=False)
    seen = client.get("/api/planned").json()
    assert seen["open"] == [] and seen["closed"][0]["paid_tx_id"] == paid and seen["closed"][0]["status"] == "paid"
    fc = analytics.forecast(db)
    assert fc["planned_out_cents"] == 0 and not any(u.get("planned") == item["id"] for u in fc["upcoming"])
    # Wieder offen, etwa nach falschem Abhaken; dieselbe Buchung hakt beim nächsten Lauf wieder ab.
    assert client.post(f"/api/planned/{item['id']}/reopen").json()["status"] == "open"
    assert client.post(f"/api/planned/{item['id']}/reopen").status_code == 409


def test_two_equal_bookings_are_not_guessed_but_offered(client, db, giro):
    item = plan(client, giro).json()
    ledger.import_rows(db, giro, [
        {"booking_date": day(0), "amount_cents": -85000, "counterparty": "Erfundener Handwerker", "purpose": "Rechnung 1"},
        {"booking_date": day(0), "amount_cents": -85000, "counterparty": "Erfundene Werkstatt", "purpose": "Rechnung 2"},
        {"booking_date": day(0), "amount_cents": -79000, "counterparty": "Erfundener Maler", "purpose": "Rechnung 3"},
        {"booking_date": day(0), "amount_cents": -1200, "counterparty": "Erfundener Bäcker", "purpose": "Brot"},
    ], "openbanking")
    assert planned.settle(db) == 0
    offered = client.get("/api/planned").json()["open"][0]["candidates"]
    assert [c["amount_cents"] for c in offered] == [-85000, -85000, -79000]
    taken = client.post(f"/api/planned/{item['id']}/paid", json={"tx_id": offered[2]["tx_id"]})
    assert taken.status_code == 200 and taken.json()["paid_tx_id"] == offered[2]["tx_id"]
    # Dieselbe Buchung kann nicht zwei Pläne erledigen.
    other = plan(client, giro, label="Erfundener Zweitplan", cents=79000).json()
    assert client.post(f"/api/planned/{other['id']}/paid", json={"tx_id": offered[2]["tx_id"]}).status_code == 400
    assert client.post(f"/api/planned/{other['id']}/paid", json={}).json()["status"] == "paid"


def test_contract_debits_transfers_and_old_bookings_never_match(client, db, giro):
    plan(client, giro, cents=5000)
    book(db, giro, -3, -5000, "Erfundener Altkauf")                 # vor dem Eintragen gebucht
    book(db, giro, 0, -5000, "Erfundener Stromversorger")
    db.execute("UPDATE transactions SET contract_key = 'ks-strom' WHERE counterparty = 'Erfundener Stromversorger'")
    book(db, giro, 0, -5000, "Erfundene Umbuchung")
    db.execute("UPDATE transactions SET is_transfer = 1 WHERE counterparty = 'Erfundene Umbuchung'")
    assert planned.settle(db) == 0
    assert client.get("/api/planned").json()["open"][0]["candidates"] == []


def test_overdue_plan_keeps_counting_and_asks_once(client, db, giro):
    item = planned.create(db, {"label": "Erfundene Kaution", "cents": 60000, "due_date": day(-4), "account_id": giro},
                          today=TODAY - timedelta(days=10))
    fc = analytics.forecast(db)
    line = next(u for u in fc["upcoming"] if u.get("planned") == item["id"])
    assert (line["date"], line["overdue"]) == (day(1), True) and fc["planned_out_cents"] == -60000
    found = [a for a in services.alerts(db, services.build_summary(db)) if a.get("planned") == item["id"]]
    assert len(found) == 1 and found[0]["key"] == f"planned-due:{item['id']}:{day(-4)}" and "600,00" in found[0]["text"]
    # Verschieben: neuer Tag, keine Nachfrage mehr, zählt am neuen Tag.
    moved = client.post(f"/api/planned/{item['id']}", json={"due_date": day(20), "cents": 65000, "note": " später  fällig "})
    assert moved.status_code == 200 and (moved.json()["due_date"], moved.json()["cents"], moved.json()["note"]) == (
        day(20), 65000, "später fällig")
    assert not [a for a in services.alerts(db, services.build_summary(db)) if a.get("planned")]
    assert dict(analytics.forecast(db)["future"])[day(19)] == dict(fc["future"])[day(19)] + 60000
    # Entfällt: zählt nicht mehr.
    assert client.post(f"/api/planned/{item['id']}/drop").json()["status"] == "dropped"
    assert analytics.forecast(db)["planned_out_cents"] == 0
    assert client.post(f"/api/planned/{item['id']}/drop").status_code == 409
    assert client.post(f"/api/planned/{item['id']}", json={"cents": 1}).status_code == 409


def test_paid_plan_does_not_raise_the_everyday_rate(client, db, giro):
    from kassensturz.util import add_months, month_start
    for back in range(1, 135, 3):
        book(db, giro, -back, -2000, f"Erfundener Markt {back}")
    usual = analytics.variable_daily_rate(db, [giro])
    # In jedem der drei Vormonate eine große, geplante Anschaffung.
    for i in (1, 2, 3):
        on = add_months(month_start(TODAY), -i) + timedelta(days=14)
        planned.create(db, {"label": f"Erfundene Anschaffung {i}", "cents": 64900 + i, "due_date": on.isoformat(),
                            "account_id": giro}, today=on - timedelta(days=5))
        book(db, giro, (on - TODAY).days, -64900 - i, "Erfundener Elektromarkt")
    assert analytics.variable_daily_rate(db, [giro]) > usual
    assert planned.settle(db) == 3
    assert analytics.variable_daily_rate(db, [giro]) == usual


@pytest.mark.parametrize("body", [
    {"label": "", "cents": 100}, {"cents": 0}, {"cents": -5}, {"cents": 1.5}, {"cents": True}, {"cents": 100_000_001},
    {"due_date": "bald"}, {"due_date": (TODAY - timedelta(days=1)).isoformat()},
    {"due_date": (TODAY + timedelta(days=2000)).isoformat()}, {"account_id": 99999}, {"account_id": None}, {"label": 7},
])
def test_bad_input_is_refused(client, db, giro, body):
    assert plan(client, giro, **body).status_code == 400
    assert client.get("/api/planned").json()["open"] == []


def test_unknown_plan_and_deleted_account(client, db, giro):
    assert client.post("/api/planned/4711/paid", json={}).status_code == 404
    assert client.post("/api/planned/4711", json={"cents": 5}).status_code == 404
    other = db.insert("accounts", {"name": "KS-Zweitkonto", "kind": "giro", "in_forecast": 1})
    plan(client, other)
    paid = plan(client, giro).json()
    tx = book(db, giro, 0, -85000, "Erfundener Handwerker")
    assert planned.settle(db) == 1
    db.execute("DELETE FROM transactions WHERE id = ?", (tx,))
    db.execute("DELETE FROM accounts WHERE id = ?", (other,))
    planned.prune(db)
    seen = planned.overview(db)
    assert seen["open"] == [] and [(c["id"], c["paid_tx_id"]) for c in seen["closed"]] == [(paid["id"], None)]


def test_person_sees_only_plans_on_own_and_shared_accounts(db, giro):
    anna = household.create_person(db, {"name": "KS-Anna"})["id"]
    ben = household.create_person(db, {"name": "KS-Ben"})["id"]
    own = db.insert("accounts", {"name": "KS-Bens Konto", "kind": "giro", "in_forecast": 1, "owner_person_id": ben})
    planned.create(db, {"label": "Erfundene Gemeinsame", "cents": 1000, "due_date": day(3), "account_id": giro})
    mine = planned.create(db, {"label": "Erfundene Eigene", "cents": 2000, "due_date": day(-1), "account_id": own},
                          today=TODAY - timedelta(days=5))
    assert [i["label"] for i in planned.overview(db.scoped(anna))["open"]] == ["Erfundene Gemeinsame"]
    assert planned.overview(db.scoped(ben))["open_cents"] == 3000
    alert = next(a for a in planned.alerts(db) if a["planned"] == mine["id"])
    assert alert["owner_person_id"] == ben


def test_mobile_forecast_reports_planned_part(db, giro):
    from kassensturz import mobile_read
    planned.create(db, {"label": "Erfundene Rechnung", "cents": 12300, "due_date": day(1), "account_id": giro})
    dto = mobile_read._forecast_dto(analytics.forecast(db))
    assert dto["planned_out_cents"] == -12300
    assert any(u["name"] == "Erfundene Rechnung" and u["interval"] is None for u in dto["upcoming"])
