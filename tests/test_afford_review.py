"""„Kann ich mir das leisten?“ und Monatsabschluss – nur erfundene Daten."""
from datetime import date

from kassensturz import analytics, ledger, services

from test_mobile_write import https_client, paired_headers, reset_mobile_guards


def _fc(free=50000, days=10, daily=3000, low=40000):
    return {"free_cents": free, "days_left": days, "variable_daily_cents": daily, "variable_expected_cents": daily * days,
            "low_point": {"date": "2026-11-27", "cents": low}, "period_end": "2026-11-27", "period_label": "bis zum nächsten Gehalt"}


def test_afford_verdicts():
    assert analytics.afford(_fc(), 10000)["verdict"] == "yes"
    tight = analytics.afford(_fc(), 30000)          # 200 € bleiben, 300 € braucht der Alltag
    assert tight["verdict"] == "tight" and tight["free_after_cents"] == 20000 and tight["per_day_after_cents"] == 2000
    no = analytics.afford(_fc(), 60000)
    assert no["verdict"] == "no" and no["free_after_cents"] == -10000
    # Reicht für den Alltag, aber die Prognose fällt unter die Warnschwelle.
    low = analytics.afford(_fc(free=100000, low=25000), 10000, threshold_cents=20000)
    assert low["verdict"] == "tight" and low["below_threshold"] is True and low["low_point_after"]["cents"] == 15000
    assert analytics.afford(_fc(), -10000)["amount_cents"] == 10000


def test_afford_endpoints_validate_the_amount(client, db, monkeypatch):
    assert client.get("/api/afford?amount_cents=0").status_code == 400
    assert client.get("/api/afford?amount_cents=100000001").status_code == 400
    r = client.get("/api/afford?amount_cents=5000")
    assert r.status_code == 200 and r.json()["verdict"] in ("yes", "tight", "no")

    reset_mobile_guards(monkeypatch)
    with https_client() as mobile:
        headers = paired_headers(mobile)
        assert mobile.get("/api/v1/afford?amount_cents=5000").status_code == 401
        assert mobile.get("/api/v1/afford?amount_cents=0", headers=headers).status_code == 400
        assert mobile.get("/api/v1/afford?amount_cents=abc", headers=headers).status_code in (400, 422)
        ok = mobile.get("/api/v1/afford?amount_cents=5000", headers=headers)
        assert ok.status_code == 200 and ok.json()["amount_cents"] == 5000


def _month(db, acc, month, income, spends):
    rows = [{"booking_date": f"{month}-01", "amount_cents": income, "counterparty": "Erfundene Firma", "purpose": f"Lohn {month}"}]
    for i, (who, cents) in enumerate(spends):
        rows.append({"booking_date": f"{month}-{10 + i:02d}", "amount_cents": -cents, "counterparty": who, "purpose": f"{month} {i}"})
    ledger.import_rows(db, acc, rows, "datei")


def _setup(db):
    acc = db.insert("accounts", {"name": "Testkonto", "kind": "giro"})
    urlaub = db.insert("categories", {"name": "Testurlaub", "kind": "expense"})
    db.execute("INSERT INTO learned_categories(key, sign, label, category_id) VALUES('erfundenes reisebuero', 'out', 'x', ?)", (urlaub,))
    for month in ("2026-07", "2026-08", "2026-09"):
        _month(db, acc, month, 300000, [("Erfundener Laden", 100000), ("Erfundenes Reisebuero", 10000)])
    _month(db, acc, "2026-10", 300000, [("Erfundener Laden", 100000), ("Erfundenes Reisebuero", 90000)])
    return acc


def test_month_review_compares_with_the_three_months_before(db):
    _setup(db)
    review = analytics.month_review(db, "2026-10")
    assert review["label"] == "Oktober 2026" and review["has_data"] is True
    assert (review["income_cents"], review["expense_cents"], review["saved_cents"]) == (300000, 190000, 110000)
    assert review["savings_rate"] == 0.3667
    assert review["usual_expense_cents"] == 110000 and review["expense_change_cents"] == 80000
    assert review["compared_months"] == 3
    assert review["notable"] == ["Testurlaub"]
    assert review["biggest_expense"]["name"] == "Erfundener Laden"

    text = analytics.review_message(review)
    assert "Einnahmen 3.000,00 €, Ausgaben 1.900,00 €." in text
    assert "Sparquote 37 %" in text and "800,00 € mehr als sonst" in text and "Auffällig: Testurlaub." in text


def test_month_review_without_history_or_data(db):
    acc = db.insert("accounts", {"name": "Testkonto", "kind": "giro"})
    empty = analytics.month_review(db, "2026-10")
    assert empty["has_data"] is False and empty["savings_rate"] is None
    _month(db, acc, "2026-10", 100000, [("Erfundener Laden", 150000)])
    review = analytics.month_review(db, "2026-10")
    assert review["expense_change_cents"] is None and review["compared_months"] == 0 and review["notable"] == []
    assert "500,00 € mehr ausgegeben als eingenommen." in analytics.review_message(review)


def test_review_notice_only_in_the_first_week_and_with_data(db):
    assert services.month_review_notice(db, date(2026, 11, 3)) is None
    _setup(db)
    notice = services.month_review_notice(db, date(2026, 11, 3))
    assert notice["key"] == "review:2026-10" and notice["title"] == "Kassensturz: Monatsabschluss Oktober 2026"
    assert services.month_review_notice(db, date(2026, 11, 8)) is None
    assert services.month_review_notice(db, date(2027, 1, 2)) is None  # Dezember ohne Buchungen


def test_stats_carry_the_review(client, db, monkeypatch):
    _setup(db)
    assert client.get("/api/stats?month=2026-10").json()["review"]["saved_cents"] == 110000
    reset_mobile_guards(monkeypatch)
    with https_client() as mobile:
        review = mobile.get("/api/v1/stats?month=2026-10", headers=paired_headers(mobile)).json()["review"]
    assert review == {"label": "Oktober 2026", "has_data": True, "complete": True, "saved_cents": 110000, "savings_rate": 0.3667,
                      "expense_change_cents": 80000, "compared_months": 3, "notable": ["Testurlaub"]}
