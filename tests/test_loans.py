"""Kredite mit Tilgungsplan – nur erfundene Zahlen."""
import math
from datetime import date

import pytest

from kassensturz import ledger, loans

TODAY = date(2027, 3, 20)


def kredit(db, rest=10_000_000, on="2027-03-01", rate=3600, payment=100_000, **extra):
    acc = db.insert("accounts", {"name": "KS-Autokredit", "kind": "kredit", "in_forecast": 0, "loan_rate_milli": rate,
                                 "loan_payment_cents": payment, **extra})
    if rest is not None:
        ledger.record_valuation(db, acc, -rest, on)
    return acc


def test_plan_matches_the_annuity_formula(db):
    acc = kredit(db)
    plan = loans.overview(db, acc, today=TODAY)
    # 100.000 € zu 3,6 % mit 1.000 € im Monat: n = -ln(1 - S·i/R) / ln(1 + i), i = 0,3 % je Monat
    expected = math.ceil(-math.log(1 - 100_000 * 0.003 / 1000) / math.log(1.003))
    assert plan["ready"] and plan["covers_interest"] and plan["done"]
    assert (plan["months"], plan["end_date"], plan["today_cents"], plan["months_since_entry"]) == (expected, "2037-03-01", 10_000_000, 0)
    assert plan["first_interest_cents"] == 30_000
    assert plan["total_cents"] == 10_000_000 + plan["interest_cents"] and 1_900_000 < plan["interest_cents"] < 1_950_000
    years = plan["years"]
    assert [y["year"] for y in years][:2] == [2027, 2028] and years[-1]["rest_cents"] == 0 and years[-1]["year"] == 2037
    assert years[0]["paid_cents"] == 9 * 100_000 and years[1]["paid_cents"] == 12 * 100_000
    assert sum(y["paid_cents"] for y in years) == plan["total_cents"]
    assert all(a["rest_cents"] > b["rest_cents"] for a, b in zip(years, years[1:]))


def test_schedule_rows_add_up_and_the_last_payment_is_only_what_is_left():
    plan = loans.schedule(250_000, date(2027, 1, 31), 6000, 100_000)
    rows = plan["rows"]
    assert [r["date"] for r in rows] == ["2027-02-28", "2027-03-31", "2027-04-30"]
    assert rows[0] == {"date": "2027-02-28", "interest_cents": 1250, "principal_cents": 98_750, "paid_cents": 100_000,
                       "rest_cents": 151_250}
    assert rows[-1]["rest_cents"] == 0 and rows[-1]["paid_cents"] < 100_000
    assert sum(r["principal_cents"] for r in rows) == 250_000 and plan["interest_cents"] == sum(r["interest_cents"] for r in rows)
    zero = loans.schedule(300_000, date(2027, 1, 15), 0, 100_000)
    assert (zero["months"], zero["interest_cents"], zero["end_date"]) == (3, 0, "2027-04-15")


def test_entered_balance_is_carried_forward_to_today(db):
    acc = kredit(db, rest=1_000_000, on="2026-12-20", rate=6000, payment=50_000)
    plan = loans.overview(db, acc, today=TODAY)
    # Drei volle Monate seit dem Eintrag: 20.1., 20.2., 20.3.
    rest = 1_000_000
    for _ in range(3):
        rest = rest + (rest * 6000 + 600_000) // 1_200_000 - 50_000
    assert (plan["months_since_entry"], plan["today_cents"], plan["entered_cents"], plan["entered_on"]) == (3, rest, 1_000_000, "2026-12-20")
    assert plan["years"][0]["year"] == 2027 and plan["end_date"] > "2028-10"
    # Ein Tag früher ist der dritte Monat noch nicht voll.
    assert loans.overview(db, acc, today=date(2027, 3, 19))["months_since_entry"] == 2


def test_extra_repayment_shortens_the_term_and_saves_interest(client, db):
    acc = kredit(db, on=date.today().isoformat())
    plain = client.get(f"/api/accounts/{acc}/loan").json()
    extra = client.get(f"/api/accounts/{acc}/loan?extra_cents=1000000").json()
    assert "extra" not in plain and extra["months"] == plain["months"]
    e = extra["extra"]
    assert e["cents"] == 1_000_000 and e["months"] < plain["months"] and e["months_saved"] == plain["months"] - e["months"]
    assert 10 <= e["months_saved"] <= 20 and e["interest_saved_cents"] == plain["interest_cents"] - e["interest_cents"] > 300_000
    assert e["end_date"] < plain["end_date"]
    assert client.get(f"/api/accounts/{acc}/loan?extra_cents=10000001").status_code == 400
    assert client.get(f"/api/accounts/{acc}/loan?extra_cents=-1").status_code == 400
    everything = client.get(f"/api/accounts/{acc}/loan?extra_cents=10000000").json()["extra"]
    assert (everything["months"], everything["interest_cents"]) == (0, 0)


def test_payment_that_does_not_cover_interest_has_no_end(db):
    acc = kredit(db, rest=10_000_000, rate=12_000, payment=90_000)
    plan = loans.overview(db, acc, today=TODAY)
    assert plan["ready"] and plan["covers_interest"] is False and plan["end_date"] is None and plan["years"] == []
    assert plan["first_interest_cents"] == 100_000
    slow = kredit(db, rest=10_000_000, rate=12_000, payment=100_001)
    endless = loans.overview(db, slow, today=TODAY)
    assert endless["covers_interest"] and endless["done"] is False and endless["end_date"] is None and endless["months"] == loans.MAX_MONTHS


def test_missing_details_are_named_and_only_loans_have_a_plan(client, db):
    bare = db.insert("accounts", {"name": "KS-Kredit ohne Angaben", "kind": "kredit"})
    seen = client.get(f"/api/accounts/{bare}/loan").json()
    assert seen["ready"] is False and seen["missing"] == ["rate", "payment", "balance"]
    giro = db.insert("accounts", {"name": "KS-Girokonto", "kind": "giro"})
    assert client.get(f"/api/accounts/{giro}/loan").status_code == 409
    assert client.get("/api/accounts/4711/loan").status_code == 404
    assert loans.overview(db, kredit(db, rest=None), today=TODAY)["missing"] == ["balance"]


def test_terms_are_saved_with_the_account_and_checked(client, db):
    made = client.post("/api/accounts", json={"name": "KS-Baukredit", "kind": "kredit", "loan_rate_milli": 3490,
                                              "loan_payment_cents": 120_000, "matures_on": "2040-01-01"})
    assert made.status_code == 200, made.text
    acc = db.one("SELECT * FROM accounts WHERE name = 'KS-Baukredit'")
    assert (acc["loan_rate_milli"], acc["loan_payment_cents"]) == (3490, 120_000)
    assert client.post(f"/api/accounts/{acc['id']}/balance", json={"balance_cents": 20_000_000}).status_code == 200
    plan = client.get(f"/api/accounts/{acc['id']}/loan").json()
    assert plan["ready"] and plan["today_cents"] == 20_000_000 and plan["end_differs"] is True
    for bad in ({"loan_rate_milli": -1}, {"loan_rate_milli": 30_001}, {"loan_rate_milli": 3.5}, {"loan_rate_milli": True},
                {"loan_payment_cents": -5}, {"loan_payment_cents": "viel"}):
        assert client.patch(f"/api/accounts/{acc['id']}", json=bad).status_code == 400, bad
    assert client.patch(f"/api/accounts/{acc['id']}", json={"loan_rate_milli": 0, "loan_payment_cents": None}).status_code == 200
    acc = db.one("SELECT * FROM accounts WHERE id = ?", (acc["id"],))
    assert (acc["loan_rate_milli"], acc["loan_payment_cents"]) == (0, None)
    assert client.get(f"/api/accounts/{acc['id']}/loan").json()["missing"] == ["payment"]
    assert client.patch(f"/api/accounts/{acc['id']}", json={"loan_rate_milli": ""}).status_code == 200
    assert client.get(f"/api/accounts/{acc['id']}/loan").json()["missing"] == ["rate", "payment"]


@pytest.mark.parametrize("rest,rate,payment", [(1, 0, 1), (999, 29_999, 100), (5_000_000, 1, 1_000_000_000)])
def test_edge_amounts_terminate(rest, rate, payment):
    plan = loans.schedule(rest, date(2027, 1, 1), rate, payment)
    assert plan["done"] and plan["rows"][-1]["rest_cents"] == 0
