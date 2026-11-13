"""Sensoren und Ereignisse für Home Assistant – nur mit erfundenen Daten."""
from datetime import date

from kassensturz import ha, ledger, options, savings, services


def _row(day, cents, who, text=""):
    return {"booking_date": day, "amount_cents": cents, "counterparty": who, "purpose": "Test", "booking_text": text}


def _capture(monkeypatch):
    sent = []
    monkeypatch.setattr(ha, "available", lambda: True)
    monkeypatch.setattr(ha, "_post", lambda path, payload: sent.append((path, payload)) or True)
    return sent


def _events(sent, name):
    return [p for path, p in sent if path == f"/events/kassensturz_{name}"]


def _states(sent):
    return {path.removeprefix("/states/sensor.kassensturz_"): p for path, p in sent if path.startswith("/states/")}


def test_sensors_cover_net_worth_savings_goals_and_loans(db, monkeypatch):
    today = date.today().isoformat()
    giro = db.insert("accounts", {"name": "Testgiro", "kind": "giro", "in_forecast": 1})
    spar = db.insert("accounts", {"name": "Testsparbuch", "kind": "tagesgeld", "in_forecast": 0})
    depot = db.insert("accounts", {"name": "Testdepot", "kind": "depot", "in_forecast": 0})
    kredit = db.insert("accounts", {"name": "Testkredit", "kind": "kredit", "in_forecast": 0})
    for acc, cents in ((giro, 150000), (spar, 400000), (depot, 250000), (kredit, -300000)):
        ledger.set_balance_anchor(db, acc, cents, today)
    savings.create_goal(db, {"name": "Erfundene Reise", "target_cents": 800000, "account_id": spar})
    sent = _capture(monkeypatch)

    services.refresh(db, notify=False)

    states = _states(sent)
    assert states["vermoegen"]["state"] == 5000.0
    assert states["vermoegen"]["attributes"]["kredite"] == -3000.0
    assert states["vermoegen"]["attributes"]["state_class"] == "total"
    assert states["ersparnisse"]["state"] == 6500.0
    assert states["schulden"]["state"] == 3000.0
    assert states["schulden"]["attributes"]["kredite"] == 1
    goal = states["sparziel_erfundene_reise"]
    assert goal["state"] == 4000.0
    assert goal["attributes"]["ziel"] == 8000.0
    assert goal["attributes"]["prozent"] == 50
    assert "state_class" not in states["frei_verfuegbar"]["attributes"]
    assert "ruecklage_jahreskosten" in states
    assert not [path for path, _ in sent if path.startswith("/events/")]


def test_new_transactions_fire_summary_salary_and_large_debit(db, monkeypatch):
    acc = db.insert("accounts", {"name": "Testgiro", "kind": "giro"})
    sent = _capture(monkeypatch)
    services.refresh(db)
    ledger.import_rows(db, acc, [
        _row("2026-11-02", 280000, "Erfundene Firma GmbH", "LOHN GEHALT"),
        _row("2026-11-03", -75000, "Erfundene Werkstatt"),
        _row("2026-11-04", -1299, "Erfundenes Abo"),
    ], "fints")
    ledger.import_rows(db, acc, [_row("2026-11-05", -90000, "Selbst importiert")], "datei")

    services.refresh(db)

    summary = _events(sent, "neue_buchungen")
    assert summary == [{"anzahl": 3, "konten": ["Testgiro"], "summe": 2037.01}]
    salary = _events(sent, "gehalt_eingegangen")
    assert salary == [{"betrag": 2800.0, "konto": "Testgiro", "von": "Erfundene Firma GmbH", "datum": "2026-11-02"}]
    large = _events(sent, "grosse_abbuchung")
    assert large == [{"betrag": 750.0, "konto": "Testgiro", "an": "Erfundene Werkstatt", "datum": "2026-11-03"}]

    services.refresh(db)
    assert len(_events(sent, "neue_buchungen")) == 1
    assert len(_events(sent, "grosse_abbuchung")) == 1


def test_large_debit_threshold_and_switch(db, monkeypatch):
    acc = db.insert("accounts", {"name": "Testgiro", "kind": "giro"})
    sent = _capture(monkeypatch)
    opts = dict(options.DEFAULTS, large_transaction=0)
    monkeypatch.setattr(options, "load", lambda: opts)
    services.refresh(db)
    ledger.import_rows(db, acc, [_row("2026-11-03", -75000, "Erfundene Werkstatt")], "openbanking")
    services.refresh(db)
    assert _events(sent, "neue_buchungen")
    assert not _events(sent, "grosse_abbuchung")

    opts["events"] = False
    ledger.import_rows(db, acc, [_row("2026-11-06", -99000, "Erfundener Händler")], "openbanking")
    services.refresh(db)
    assert len(_events(sent, "neue_buchungen")) == 1


def test_budget_events_fire_once_per_level_and_month(db, monkeypatch):
    acc = db.insert("accounts", {"name": "Testgiro", "kind": "giro"})
    cat = db.one("SELECT id, name FROM categories WHERE kind = 'expense' AND parent_id IS NULL ORDER BY id LIMIT 1")
    db.update("categories", "id", cat["id"], {"budget_cents": 10000})
    today = date.today().isoformat()
    sent = _capture(monkeypatch)

    db.insert("transactions", _tx(acc, today, -8500, cat["id"], "a"))
    services.refresh(db)
    services.refresh(db)
    events = _events(sent, "budget_schwelle")
    assert [e["schwelle"] for e in events] == [80]
    assert events[0]["kategorie"] == cat["name"]
    assert events[0]["prozent"] == 85
    assert events[0]["rest"] == 15.0

    db.insert("transactions", _tx(acc, today, -3000, cat["id"], "b"))
    services.refresh(db)
    services.refresh(db)
    assert [e["schwelle"] for e in _events(sent, "budget_schwelle")] == [80, 100]


def test_budget_jump_over_both_levels_reports_both(db):
    summary = {"budgets": [{"category_id": 7, "name": "Testkategorie", "ratio": 1.2, "budget_cents": 10000,
                            "spent_cents": 12000, "left_cents": -2000}]}
    events = services.budget_events(summary, date(2026, 11, 13))
    assert [(key, data["schwelle"]) for key, _, data in events] == [("ev-budget:2026-11:7:100", 100), ("ev-budget:2026-11:7:80", 80)]


def _tx(acc, day, cents, cat, tag):
    return {"account_id": acc, "booking_date": day, "amount_cents": cents, "counterparty": "Erfundener Laden",
            "purpose": "Test", "category_id": cat, "hash": f"test-{tag}", "source": "manuell"}
