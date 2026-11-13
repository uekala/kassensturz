"""Selbsttest des Kontostands – nur erfundene Daten."""
from datetime import date

from kassensturz import ledger, services


def _account(db, name="Testkonto"):
    return db.insert("accounts", {"name": name, "kind": "giro"})


def _add(db, acc, day, cents, who="Erfundener Laden"):
    ledger.import_rows(db, acc, [{"booking_date": day, "amount_cents": cents, "counterparty": who,
                                  "purpose": f"Test {day} {cents}"}], "openbanking")


def test_first_check_only_sets_the_starting_point(db):
    acc = _account(db)
    _add(db, acc, "2026-11-01", -5000)
    assert ledger.check_balance(db, acc, 100000, date(2026, 11, 1)) == 0
    assert ledger.balance_drift(db, acc, date(2026, 11, 20)) is None


def test_matching_transactions_explain_the_change(db):
    acc = _account(db)
    ledger.check_balance(db, acc, 100000, date(2026, 11, 1))
    _add(db, acc, "2026-11-01", -2500)   # am selben Tag nach dem ersten Abruf gebucht
    _add(db, acc, "2026-11-02", 30000)
    assert ledger.check_balance(db, acc, 127500, date(2026, 11, 2)) == 0
    assert ledger.check_balance(db, acc, 127500, date(2026, 11, 3)) == 0
    assert ledger.balance_drift(db, acc, date(2026, 11, 10)) is None


def test_missing_transaction_is_reported_after_three_days(db):
    acc = _account(db)
    ledger.check_balance(db, acc, 100000, date(2026, 11, 1))
    _add(db, acc, "2026-11-02", -1000)
    # Die Bank hat 49,99 € mehr abgezogen, als an Buchungen ankam.
    assert ledger.check_balance(db, acc, 94001, date(2026, 11, 2)) == -4999
    assert ledger.balance_drift(db, acc, date(2026, 11, 4)) is None
    ledger.check_balance(db, acc, 94001, date(2026, 11, 4))
    assert ledger.balance_drift(db, acc, date(2026, 11, 5)) == {"cents": -4999, "since": "2026-11-02"}


def test_pending_transaction_cancels_out_when_it_is_booked(db):
    acc = _account(db)
    ledger.check_balance(db, acc, 100000, date(2026, 11, 1))
    # Vorgemerkt: Der Bankstand ist schon niedriger, die Buchung fehlt noch.
    assert ledger.check_balance(db, acc, 98000, date(2026, 11, 2)) == -2000
    _add(db, acc, "2026-11-03", -2000)
    assert ledger.check_balance(db, acc, 98000, date(2026, 11, 3)) == 2000
    assert ledger.balance_drift(db, acc, date(2026, 11, 30)) is None


def test_drift_raises_an_alert_and_can_be_dismissed(client, db):
    acc = _account(db, "Testgiro")
    ledger.check_balance(db, acc, 100000, date(2026, 1, 1))
    ledger.check_balance(db, acc, 110000, date(2026, 1, 2))

    found = [a for a in services.alerts(db, services.build_summary(db)) if a["key"].startswith("drift:")]
    assert len(found) == 1
    assert found[0]["key"] == f"drift:{acc}:10000"
    assert found[0]["title"] == "Kontostand Testgiro passt nicht"
    assert "100,00 € mehr" in found[0]["text"]

    listed = next(a for a in client.get("/api/accounts").json() if a["id"] == acc)
    assert listed["drift_cents"] == 10000 and listed["drift_since"] == "2026-01-02"

    assert client.post(f"/api/accounts/{acc}/balance-check/reset").status_code == 200
    assert ledger.balance_drift(db, acc) is None
    assert not [a for a in services.alerts(db, services.build_summary(db)) if a["key"].startswith("drift:")]


def test_checks_are_trimmed_and_removed_with_the_account(db):
    acc = _account(db)
    for day in range(1, 29):
        for _ in range(3):
            ledger.check_balance(db, acc, 100000, date(2026, 10, day))
    assert db.scalar("SELECT COUNT(*) FROM balance_checks") == ledger.DRIFT_KEEP
    ledger.delete_account(db, acc)
    assert db.scalar("SELECT COUNT(*) FROM balance_checks") == 0
