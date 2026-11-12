"""Mitteilung bei neuen Buchungen – nur mit erfundenen Daten."""
from kassensturz import ha, ledger, options, services


def _account(db, name="Testkonto"):
    return db.insert("accounts", {"name": name, "kind": "giro"})


def _row(day, cents, who):
    return {"booking_date": day, "amount_cents": cents, "counterparty": who, "purpose": "Test"}


def test_first_run_only_remembers_the_current_state(db):
    acc = _account(db)
    ledger.import_rows(db, acc, [_row("2026-11-01", -1234, "Testladen")], "fints")
    assert services.new_transactions_notice(db) is None
    assert services.new_transactions_notice(db) is None


def test_reports_only_automatic_sources(db):
    acc = _account(db)
    services.new_transactions_notice(db)
    ledger.import_rows(db, acc, [_row("2026-11-02", -4884, "Erfundener Markt")], "fints")
    ledger.import_rows(db, acc, [_row("2026-11-03", 250000, "Erfundene Firma GmbH")], "ordner")
    ledger.import_rows(db, acc, [_row("2026-11-04", -999, "Selbst importiert")], "datei")

    notice = services.new_transactions_notice(db)

    assert notice["count"] == 2
    assert notice["title"] == "Kassensturz: 2 neue Buchungen"
    lines = notice["message"].split("\n")
    assert lines[0] == "+2.500,00 € Erfundene Firma GmbH (Testkonto)"
    assert lines[1] == "−48,84 € Erfundener Markt (Testkonto)"
    assert "Selbst importiert" not in notice["message"]
    assert services.new_transactions_notice(db) is None


def test_long_batches_are_shortened_and_large_ones_summarised(db):
    acc = _account(db)
    services.new_transactions_notice(db)
    ledger.import_rows(db, acc, [_row(f"2026-10-{d:02d}", -100 - d, f"Laden {d}") for d in range(1, 9)], "openbanking")
    notice = services.new_transactions_notice(db)
    assert notice["title"] == "Kassensturz: 8 neue Buchungen"
    assert notice["message"].split("\n")[-1] == "und 3 weitere"

    ledger.import_rows(db, acc, [_row(f"2026-09-{d:02d}", -200 - d, f"Markt {d}") for d in range(1, 26)], "fints")
    notice = services.new_transactions_notice(db)
    assert notice["message"] == "25 Buchungen auf Testkonto abgerufen."


def test_refresh_sends_one_notification_and_respects_the_option(db, monkeypatch):
    acc = _account(db)
    sent = []
    monkeypatch.setattr(ha, "available", lambda: True)
    monkeypatch.setattr(ha, "_post", lambda path, payload: sent.append((path, payload)) or True)
    monkeypatch.setattr(ha, "push_sensors", lambda summary: 0)

    services.refresh(db)
    ledger.import_rows(db, acc, [_row("2026-11-05", -1599, "Erfundenes Abo")], "fints")
    services.refresh(db)
    tx = [p for _, p in sent if "neue Buchung" in p.get("title", "")]
    assert len(tx) == 1 and "Erfundenes Abo" in tx[0]["message"]

    monkeypatch.setattr(options, "load", lambda: dict(options.DEFAULTS, notify_new_transactions=False))
    ledger.import_rows(db, acc, [_row("2026-11-06", -500, "Noch ein Laden")], "fints")
    services.refresh(db)
    assert len([p for _, p in sent if "neue Buchung" in p.get("title", "")]) == 1
