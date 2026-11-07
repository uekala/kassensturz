from datetime import date, timedelta

from kassensturz.contracts import deadline_for, detect
from kassensturz.db import now_iso


def _add_account(db):
    return db.insert(
        "accounts",
        {"name": "Girokonto", "kind": "giro", "created": now_iso()},
    )


def _add_monthly_payments(db, account_id, amounts):
    dates = [date.today() - timedelta(days=120 - 30 * i) for i in range(4)]
    for booking_date in dates:
        for amount in amounts:
            db.insert(
                "transactions",
                {
                    "account_id": account_id,
                    "booking_date": booking_date.isoformat(),
                    "amount_cents": -amount,
                    "counterparty": "Beispiel Anbieter",
                    "purpose": "Monatliche Zahlung",
                    "created": now_iso(),
                },
            )


def test_same_day_payments_are_not_summed_into_one_contract(db):
    account_id = _add_account(db)
    _add_monthly_payments(db, account_id, [3000, 7000])

    result = detect(db)

    contracts = db.query(
        "SELECT amount_cents, count, interval FROM contracts ORDER BY amount_cents"
    )
    assert result["found"] == 2
    assert [row["amount_cents"] for row in contracts] == [-7000, -3000]
    assert [row["count"] for row in contracts] == [4, 4]
    assert {row["interval"] for row in contracts} == {"monatlich"}
    assert db.scalar(
        "SELECT COUNT(*) FROM transactions WHERE contract_key IS NOT NULL"
    ) == 8


def test_identical_same_day_payments_count_once_per_due_date(db):
    account_id = _add_account(db)
    _add_monthly_payments(db, account_id, [5000, 5000])

    result = detect(db)

    contract = db.one("SELECT amount_cents, count, interval FROM contracts")
    assert result["found"] == 1
    assert contract == {
        "amount_cents": -5000,
        "count": 4,
        "interval": "monatlich",
    }
    assert db.scalar(
        "SELECT COUNT(*) FROM transactions WHERE contract_key IS NOT NULL"
    ) == 8



def test_cancellation_deadline_is_calculated_from_contract_end_and_notice_period():
    assert deadline_for({"contract_end": "2027-01-31", "notice_months": 1}) == "2026-12-31"


def test_cancellation_deadline_is_missing_without_complete_contract_data():
    assert deadline_for({"contract_end": "2027-01-31", "notice_months": None}) is None
    assert deadline_for({"contract_end": None, "notice_months": 1}) is None
