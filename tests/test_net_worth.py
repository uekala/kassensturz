"""Sparkonto, Festgeld, VL, Immobilie, Kredit und Vermögensverlauf – nur erfundene Daten."""
from datetime import date, timedelta

from kassensturz import ledger, services


def _new(client, name, kind, **extra):
    return client.post("/api/accounts", json={"name": name, "kind": kind, **extra}).json()


def _value(client, aid, cents, on):
    return client.post(f"/api/accounts/{aid}/balance", json={"balance_cents": cents, "date": on})


def _accounts(client):
    return {a["name"]: a for a in client.get("/api/accounts").json()}


def test_new_kinds_stay_out_of_the_forecast_and_get_their_group(client, db):
    for name, kind in (("Giro", "giro"), ("Spar", "sparkonto"), ("Fest", "festgeld"), ("VL", "vl"),
                       ("Depot", "depot"), ("Haus", "immobilie"), ("Auto", "kredit")):
        _new(client, name, kind)
    accounts = _accounts(client)
    assert {n: a["in_forecast"] for n, a in accounts.items()} == {
        "Giro": 1, "Spar": 0, "Fest": 0, "VL": 0, "Depot": 0, "Haus": 0, "Auto": 0}
    assert {n: a["group"] for n, a in accounts.items()} == {
        "Giro": "alltag", "Spar": "ruecklagen", "Fest": "ruecklagen", "VL": "ruecklagen",
        "Depot": "depots", "Haus": "immobilien", "Auto": "kredite"}


def test_loan_counts_negative_whatever_sign_is_entered(client, db):
    aid = _new(client, "Autokredit", "kredit")["id"]
    _value(client, aid, 1500000, "2026-10-01")
    _value(client, aid, -1450000, "2026-11-01")
    acc = _accounts(client)["Autokredit"]
    assert acc["balance_now"] == -1450000
    assert acc["value_prev_cents"] == -1500000
    assert [v["value_cents"] for v in ledger.valuations(db, aid)] == [-1500000, -1450000]


def test_loan_does_not_touch_the_daily_balance(client, db):
    giro = _new(client, "Giro", "giro")["id"]
    _value(client, giro, 200000, "2026-11-01")
    loan = _new(client, "Autokredit", "kredit")["id"]
    _value(client, loan, 1000000, "2026-11-01")
    assert {a["id"] for a in services.build_summary(db)["forecast"]["accounts"]} == {giro}


def test_maturity_date_is_validated_and_announced(client, db):
    soon = (date.today() + timedelta(days=12)).isoformat()
    later = (date.today() + timedelta(days=200)).isoformat()
    assert client.post("/api/accounts", json={"name": "X", "kind": "festgeld", "matures_on": "bald"}).status_code == 400
    fest = _new(client, "Festgeld Test", "festgeld", matures_on=soon)
    _new(client, "Festgeld spaet", "festgeld", matures_on=later)
    loan = _new(client, "Autokredit", "kredit", matures_on=soon)
    _new(client, "Giro mit Datum", "giro", matures_on=soon)

    summary = services.build_summary(db)
    found = {a["key"]: a for a in services.alerts(db, summary) if a["key"].startswith("maturity:")}
    assert set(found) == {f"maturity:{fest['id']}:{soon}", f"maturity:{loan['id']}:{soon}"}
    assert found[f"maturity:{fest['id']}:{soon}"]["title"] == "Festgeld wird fällig: Festgeld Test"
    assert "in 12 Tagen" in found[f"maturity:{fest['id']}:{soon}"]["text"]
    assert found[f"maturity:{loan['id']}:{soon}"]["title"] == "Kredit läuft aus: Autokredit"

    client.patch(f"/api/accounts/{fest['id']}", json={"matures_on": ""})
    assert db.scalar("SELECT matures_on FROM accounts WHERE id = ?", (fest["id"],)) is None


def test_net_worth_history_combines_transactions_and_values(client, db):
    today = date(2026, 11, 13)
    giro = _new(client, "Giro", "giro")["id"]
    ledger.import_rows(db, giro, [
        {"booking_date": "2026-09-10", "amount_cents": 100000, "counterparty": "Erfundene Firma", "purpose": "Lohn"},
        {"booking_date": "2026-10-10", "amount_cents": -30000, "counterparty": "Erfundener Laden", "purpose": "Einkauf"},
        {"booking_date": "2026-11-05", "amount_cents": -20000, "counterparty": "Erfundener Laden", "purpose": "Einkauf"},
    ], "datei")
    _value(client, giro, 50000, "2026-11-13")
    depot = _new(client, "Depot", "depot")["id"]
    _value(client, depot, 1000000, "2026-10-15")
    _value(client, depot, 1100000, "2026-11-10")
    history = {h["date"]: h["cents"] for h in ledger.net_worth_history(db, months=3, today=today)}
    # Der Verlauf beginnt, sobald auch das Depot einen Wert hat (15.10.).
    assert history == {"2026-10-31": 70000 + 1000000, "2026-11-13": 50000 + 1100000}

    loan = _new(client, "Autokredit", "kredit")["id"]
    _value(client, loan, 400000, "2026-11-01")
    history = {h["date"]: h["cents"] for h in ledger.net_worth_history(db, months=3, today=today)}
    # Mit dem Kredit beginnt er am 1.11.; ein Sprung durch das neue Konto entsteht nicht.
    assert history == {"2026-11-13": 50000 + 1100000 - 400000}
    assert client.get("/api/networth").json()["history"][-1]["cents"] == 750000


def test_mobile_accounts_carry_group_and_maturity(client, db):
    from kassensturz import mobile_read

    soon = (date.today() + timedelta(days=5)).isoformat()
    aid = _new(client, "Festgeld Test", "festgeld", matures_on=soon)["id"]
    _value(client, aid, 500000, date.today().isoformat())
    item = next(a for a in mobile_read.get_overview(db)["accounts"] if a["id"] == aid)
    assert item["group"] == "ruecklagen" and item["matures_on"] == soon and item["type"] == "festgeld"
