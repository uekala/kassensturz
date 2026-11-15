"""Zuordnen im Stapel und Budget-Vorschläge – nur erfundene Daten."""
from datetime import date

from kassensturz import analytics, ledger
from test_mobile_write import https_client, paired_headers, reset_mobile_guards


def _cat(db, key):
    return db.scalar("SELECT id FROM categories WHERE builtin_key = ?", (key,))


def _book(db, acc, rows):
    """rows: (Datum, Cent, Empfänger, Kategorie-Schlüssel oder None)."""
    for day, cents, who, key in rows:
        ledger.import_rows(db, acc, [{"booking_date": day, "amount_cents": cents, "counterparty": who, "purpose": "Test"}], "fints")
        tx = db.scalar("SELECT MAX(id) FROM transactions")
        db.update("transactions", "id", tx, {"category_id": _cat(db, key) if key else None, "is_transfer": 0})


def test_triage_lists_unassigned_largest_first(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    acc = db.insert("accounts", {"name": "Testgiro", "kind": "giro"})
    hidden = db.insert("accounts", {"name": "Altkonto", "kind": "giro", "archived": 1})
    _book(db, acc, [("2026-11-02", -1200, "Erfundener Kiosk", "sonstiges"),
                    ("2026-11-03", -45000, "Erfundene Firma XY", "sonstiges"),
                    ("2026-11-04", -9900, "Erfundener Unbekannt", None),
                    ("2026-11-05", 2500, "Erfundene Erstattung", "sonstige_einnahmen"),
                    ("2026-11-06", -8000, "Erfundener Supermarkt", "lebensmittel")])
    _book(db, hidden, [("2026-11-07", -70000, "Erfundenes Altkonto", "sonstiges")])
    with https_client() as client:
        assert client.get("/api/v1/triage").status_code == 401
        headers = paired_headers(client)
        data = client.get("/api/v1/triage", headers=headers).json()
        assert [i["counterparty"] for i in data["items"]] == [
            "Erfundene Firma XY", "Erfundener Unbekannt", "Erfundene Erstattung", "Erfundener Kiosk"]
        assert data["total"] == 4
        assert data["expense_cents"] == 56100
        assert client.get("/api/v1/triage?limit=1", headers=headers).json()["total"] == 4
        assert len(client.get("/api/v1/triage?limit=1", headers=headers).json()["items"]) == 1
        assert client.get("/api/v1/triage?limit=x", headers=headers).status_code == 400

        first = data["items"][0]["id"]
        done = client.patch(f"/api/v1/transactions/{first}", json={"category_id": _cat(db, "lebensmittel")}, headers=headers)
        assert done.status_code == 200
        assert [i["counterparty"] for i in client.get("/api/v1/triage", headers=headers).json()["items"]][0] == "Erfundener Unbekannt"
        # Die gewöhnliche Liste bleibt nach Datum sortiert.
        assert client.get("/api/v1/transactions", headers=headers).json()["items"][0]["counterparty"] == "Erfundener Supermarkt"


def test_suggestions_average_full_months_and_round_up(db):
    acc = db.insert("accounts", {"name": "Testgiro", "kind": "giro"})
    _book(db, acc, [("2026-08-01", -10000, "Erfundener Start", "lebensmittel"),
                    ("2026-08-15", -32000, "Erfundener Supermarkt", "lebensmittel"),
                    ("2026-09-15", -30000, "Erfundener Supermarkt", "lebensmittel"),
                    ("2026-10-15", -41000, "Erfundener Supermarkt", "lebensmittel"),
                    ("2026-10-20", -900, "Erfundenes Kino", "freizeit"),
                    ("2026-09-20", -60000, "Erfundene Firma XY", "sonstiges"),
                    ("2026-11-10", -99900, "Erfundener Ausreißer", "lebensmittel")])
    data = analytics.budget_suggestions(db, date(2026, 11, 15))
    assert data["months"] == 3
    assert data["items"] == [{"category_id": _cat(db, "lebensmittel"), "name": "Lebensmittel & Drogerie",
                              "average_cents": 37666, "suggested_cents": 38000, "current_cents": None}]

    db.update("categories", "id", _cat(db, "lebensmittel"), {"budget_cents": 5000})
    assert analytics.budget_suggestions(db, date(2026, 11, 15))["items"][0]["current_cents"] == 5000
    db.update("categories", "id", _cat(db, "lebensmittel"), {"budget_cents": 40000})
    assert analytics.budget_suggestions(db, date(2026, 11, 15))["items"] == []


def test_suggestions_skip_a_partial_first_month(db):
    acc = db.insert("accounts", {"name": "Testgiro", "kind": "giro"})
    _book(db, acc, [("2026-09-20", -5000, "Erfundener Supermarkt", "lebensmittel"),
                    ("2026-10-15", -30000, "Erfundener Supermarkt", "lebensmittel")])
    data = analytics.budget_suggestions(db, date(2026, 11, 15))
    assert data["months"] == 1
    assert data["items"][0]["average_cents"] == 30000 and data["items"][0]["suggested_cents"] == 30000
    assert analytics.budget_suggestions(db, date(2026, 10, 20)) == {"months": 0, "items": []}


def test_rounding_steps():
    assert [analytics._round_budget(c) for c in (501, 4999, 5001, 37666, 50001, 123456)] == [1000, 5000, 6000, 38000, 55000, 125000]


def test_suggestions_endpoint(db, monkeypatch):
    reset_mobile_guards(monkeypatch)
    with https_client() as client:
        assert client.get("/api/v1/budgets/suggestions").status_code == 401
        assert client.get("/api/v1/budgets/suggestions", headers=paired_headers(client)).json() == {"months": 0, "items": []}
