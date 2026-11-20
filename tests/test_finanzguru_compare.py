"""Abgleich mit dem Finanzguru-Export vor dem Kündigen. Nur erfundene Daten; ändert nichts."""
from datetime import date

from kassensturz import finanzguru, ledger

TODAY = date(2026, 11, 20)
IBAN = "DE02120300000000202051"


def fg(day, cents, who, balance=None, ref=IBAN, name="Erfundenes Girokonto"):
    return {"ref": ref, "account_name": name, "booking_date": day, "value_date": day, "amount_cents": cents,
            "counterparty": who, "purpose": f"Zweck {who}", "balance_cents": balance, "main": "", "sub": "",
            "transfer": False, "note": None, "id": "", "original": "", "split": "", "parts": [], "rest": None}


def setup(db, automatic=True):
    acc = db.insert("accounts", {"name": "Testgiro", "kind": "giro", "iban": IBAN,
                                 "eb_uid": "erfunden-uid" if automatic else None})
    ledger.import_rows(db, acc, [
        {"booking_date": "2026-11-02", "amount_cents": -1999, "counterparty": "Erfundener Laden", "purpose": "a"},
        {"booking_date": "2026-11-06", "amount_cents": 250000, "counterparty": "Erfundene Firma", "purpose": "b"},
        {"booking_date": "2026-11-12", "amount_cents": -5000, "counterparty": "Erfundenes Kino", "purpose": "c"},
        {"booking_date": "2026-11-18", "amount_cents": -700, "counterparty": "Erfundener Bäcker", "purpose": "d"},
    ], "openbanking")
    return acc


def rows_matching():
    # Finanzguru bucht teils einen Tag später; der Stand läuft mit (vorwärts sortiert)
    return [fg("2026-10-28", -300, "Vorher", 100000), fg("2026-11-03", -1999, "Erfundener Laden", 98001),
            fg("2026-11-06", 250000, "Erfundene Firma", 348001), fg("2026-11-12", -5000, "Erfundenes Kino", 343001),
            fg("2026-11-18", -700, "Erfundener Bäcker", 342301)]


def test_everything_there_means_ready(db):
    acc = setup(db)
    db.execute("UPDATE accounts SET balance_cents = 342301, balance_date = '2026-11-18' WHERE id = ?", (acc,))
    before = db.scalar("SELECT COUNT(*) FROM transactions")
    r = finanzguru.compare(db, {"rows": rows_matching()}, today=TODAY)
    a = r["accounts"][0]
    assert a["target"] == acc and a["automatic"] and a["missing_count"] == 0 and a["extra_count"] == 0
    assert a["window"] == {"from": "2026-11-02", "to": "2026-11-18"}
    assert a["balance"]["finanzguru_cents"] == 342301 and a["balance"]["difference_cents"] == 0
    assert r["ready"] is True and a["problems"] == []
    assert db.scalar("SELECT COUNT(*) FROM transactions") == before


def test_missing_bookings_and_no_own_fetch_are_named(db):
    setup(db, automatic=False)
    rows = rows_matching() + [fg("2026-11-15", -4242, "Nur in Finanzguru")]
    rows += [fg("2026-11-10", -900, "Zweite Karte", ref="DE89370400440532013000", name="Erfundene Kreditkarte")]
    r = finanzguru.compare(db, {"rows": rows}, today=TODAY)
    giro, card = r["accounts"]
    assert r["ready"] is False and r["open"] == 2
    assert giro["missing_count"] == 1 and giro["missing"][0]["amount_cents"] == -4242
    assert any("nicht selbst" in p for p in giro["problems"]) and any("fehlt" in p for p in giro["problems"])
    assert card["target"] is None and "noch nicht" in card["problems"][0]
    skipped = finanzguru.compare(db, {"rows": rows}, {"DE89370400440532013000": "skip"}, today=TODAY)
    assert skipped["open"] == 1 and skipped["accounts"][1]["problems"] == []


def test_hanging_fetch_future_rows_paypal_and_manual_accounts(db, client):
    setup(db)
    db.insert("accounts", {"name": "Mein PayPal", "kind": "paypal", "eb_uid": "erfunden-pp"})
    rows = rows_matching() + [
        # nach der letzten Buchung in Kassensturz, aber schon einige Tage alt: Abruf hängt
        fg("2026-11-25", -1234, "Später Laden"),
        # erwartete Buchung in der Zukunft
        fg("2026-12-24", -9999, "Erwartet"),
        fg("2026-11-20", -500, "Kiosk", ref="person@example.org", name="person@example.org"),
        fg("2026-11-01", -2000, "Bar", ref="ef5e7cc0-e423-4d99-8acb-c56a1b2c3d4e", name="Bargeld"),
    ]
    r = finanzguru.compare(db, {"rows": rows}, today=date(2026, 12, 1))
    giro, paypal, cash = r["accounts"]
    assert r["future"] == 1 and r["count"] == len(rows) - 1
    assert giro["missing_count"] == 1 and giro["missing"][0]["amount_cents"] == -1234
    assert any("nichts Neues" in p for p in giro["problems"])
    assert paypal["account"] == "Mein PayPal"
    assert cash["manual"] and cash["label"] == "" and "von Hand" in cash["problems"][0]
    # frische Buchungen der letzten zwei Tage dürfen noch fehlen; ein ruhiges Konto ist kein Problem
    calm = finanzguru.compare(db, {"rows": rows_matching() + [fg("2026-11-30", -1, "Frisch")]}, today=date(2026, 12, 1))
    assert calm["accounts"][0]["problems"] == [] and calm["ready"]
    assert client.post("/api/import/finanzguru/compare", json={"token": "gibtsnicht"}).status_code == 400


def test_account_kept_by_file_is_no_obstacle_but_gaps_still_count(db):
    card = db.insert("accounts", {"name": "Advanzia Mastercard", "kind": "kreditkarte"})
    ledger.import_rows(db, card, [{"booking_date": "2026-11-03", "amount_cents": -1234, "counterparty": "Laden",
                                   "purpose": "x"}], "datei")
    rows = [fg("2026-11-03", -1234, "Laden", ref="f773a799d2129edc", name="Master-Card")]
    r = finanzguru.compare(db, {"rows": rows}, {"f773a799d2129edc": card}, today=TODAY)
    a = r["accounts"][0]
    assert a["file"] and a["problems"] == [] and r["ready"]
    # nach dem Stichtag der letzten Abrechnung: zählt noch nicht
    later = rows + [fg("2026-11-10", -500, "Später", ref="f773a799d2129edc", name="Master-Card")]
    assert finanzguru.compare(db, {"rows": later}, {"f773a799d2129edc": card}, today=TODAY)["ready"]
    # davor: fehlt
    gap = rows + [fg("2026-11-04", -500, "Fehlt", ref="f773a799d2129edc", name="Master-Card"),
                  fg("2026-11-05", -700, "Auch da", ref="f773a799d2129edc", name="Master-Card")]
    ledger.import_rows(db, card, [{"booking_date": "2026-11-05", "amount_cents": -700, "counterparty": "Auch da",
                                   "purpose": "y"}], "datei")
    assert finanzguru.compare(db, {"rows": gap}, {"f773a799d2129edc": card}, today=TODAY)["accounts"][0]["missing_count"] == 1
