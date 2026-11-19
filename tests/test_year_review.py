"""Jahresrückblick: Summen, Vergleich mit dem Vorjahr bis zum selben Tag, Monate und Kategorien. Nur erfundene Daten."""
from datetime import date

import pytest

from kassensturz import analytics, ledger


def _rows(month, income, spends):
    rows = [{"booking_date": f"{month}-01", "amount_cents": income, "counterparty": "Erfundene Firma", "purpose": f"Lohn {month}"}]
    for i, (who, cents) in enumerate(spends):
        rows.append({"booking_date": f"{month}-{10 + i:02d}", "amount_cents": -cents, "counterparty": who, "purpose": f"{month} {i}"})
    return rows


def _setup(db):
    acc = db.insert("accounts", {"name": "Testkonto", "kind": "giro"})
    urlaub = db.insert("categories", {"name": "Testurlaub", "kind": "expense"})
    db.execute("INSERT INTO learned_categories(key, sign, label, category_id) VALUES('erfundenes reisebuero', 'out', 'x', ?)", (urlaub,))
    rows = []
    for m in range(1, 13):
        rows += _rows(f"2025-{m:02d}", 200000, [("Erfundener Laden", 100000)])
    for m in range(1, 7):
        rows += _rows(f"2026-{m:02d}", 250000, [("Erfundener Laden", 100000)] + ([("Erfundenes Reisebuero", 150000)] if m == 5 else []))
    ledger.import_rows(db, acc, rows, "datei")
    return acc


def test_year_review_of_a_full_year(db):
    _setup(db)
    r = analytics.year_review(db, 2025, today=date(2026, 6, 20))
    assert r["running"] is False and r["has_data"] is True and r["years"] == [2025, 2026]
    assert (r["income_cents"], r["expense_cents"], r["saved_cents"]) == (2400000, 1200000, 1200000)
    assert r["savings_rate"] == 0.5 and r["previous"] is None and r["moved"] == []
    assert len(r["months"]) == 12 and not any(m["future"] for m in r["months"])
    assert r["count"] == 24 and r["categories"][0]["share"] == 1.0


def test_running_year_compares_to_the_same_day_last_year(db):
    _setup(db)
    r = analytics.year_review(db, 2026, today=date(2026, 6, 20))
    assert r["running"] is True and r["until"] == "2026-06-20"
    assert (r["income_cents"], r["expense_cents"]) == (1500000, 750000)
    # Vorjahr nur bis 20.06.2025: sechs Gehälter und sechs Einkäufe
    assert r["previous"] == {"income_cents": 1200000, "expense_cents": 600000, "saved_cents": 600000, "until": "2025-06-20"}
    assert [m["future"] for m in r["months"]].count(True) == 6
    urlaub = next(c for c in r["categories"] if c["name"] == "Testurlaub")
    assert urlaub["cents"] == 150000 and urlaub["previous_cents"] == 0 and urlaub["change_cents"] == 150000
    assert r["moved"][0]["name"] == "Testurlaub"
    assert r["worst_month"]["label"] == "Mai" and r["best_month"]["saldo_cents"] == 150000
    assert r["biggest"][0]["name"] == "Erfundenes Reisebuero"


def test_year_review_limits(db, client):
    assert analytics.year_review(db, 2026, today=date(2026, 6, 20))["has_data"] is False
    with pytest.raises(ValueError):
        analytics.year_review(db, 2027, today=date(2026, 6, 20))
    assert client.get("/api/year?year=1999").status_code == 400
    assert client.get("/api/year").status_code == 200
